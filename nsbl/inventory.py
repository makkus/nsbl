# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import yaml
from builtins import *
from frkl.frkl import (ConfigProcessor,
                       EnsurePythonObjectProcessor, EnsureUrlProcessor, Frkl,
                       FrklCallback, FrklProcessor, UrlAbbrevProcessor)
from jinja2 import Environment, PackageLoader

from .defaults import *
from .exceptions import NsblException


class NsblInventory(FrklCallback):
    def create(config, default_env_type=DEFAULT_ENV_TYPE,
               pre_chain=[UrlAbbrevProcessor(), EnsureUrlProcessor(), EnsurePythonObjectProcessor()]):
        """Convenience method to create a NsblInventory object out of the configs and a few optional parameters.

        Args:
          config (list): list of config items
          default_env_type (str): the type a environment is if it is not explicitely specified, either ENV_TYPE_HOST or ENV_TYPE_GROUP
          pre_chain (list): the chain of ConfigProcessors to plug in front of the one that is used internally, needs to return a python list
        Returns:
          NsblInventory: the inventory object, already 'processed'
        """

        chain = pre_chain + [FrklProcessor(NSBL_INVENTORY_BOOTSTRAP_FORMAT)]
        inv_frkl = Frkl(config, chain)

        init_params = {"default_env_type": default_env_type}
        inventory = NsblInventory(init_params)

        inv_frkl.process(inventory)

        return inventory

    create = staticmethod(create)

    def __init__(self, init_params=None):
        """Class to be used to create a dynamic ansible inventory from (elastic) yaml config files.

        The only init_params key that is supported is:

        default_env_type (str): the type a environment is if it is not explicitely specified, either ENV_TYPE_HOST or ENV_TYPE_GROUP
        Args:
          init_params (dict): the dict to initialize this object
        """
        super(NsblInventory, self).__init__(init_params)
        self.groups = {}
        self.hosts = {}
        self.tasks = []
        self.current_env_id = 0

    def validate_init(self):

        self.default_env_type = self.init_params.get('default_env_type', DEFAULT_ENV_TYPE)
        return True

    def result(self):
        return self.list()

    def extract_vars(self, inventory_dir):
        """Writes a folder structure with 'group_vars' and 'host_vars' folders into the target directory.

        Args:
          inventory_dir (str): the directory the inventory should be written to
        """

        for group, group_vars in self.groups.items():
            vars = group_vars.get(VARS_KEY, {})
            if not vars:
                continue
            group_dir = os.path.join(inventory_dir, "group_vars", group)
            var_file = os.path.join(group_dir, "{}.yml".format(group))
            content = yaml.safe_dump(vars, default_flow_style=False, encoding='utf-8', allow_unicode=True).decode(
                'utf-8')

            os.makedirs(group_dir)
            with open(var_file, "w") as text_file:
                text_file.write(content)

        for host, host_vars in self.hosts.items():
            vars = host_vars.get(VARS_KEY, {})
            if not vars:
                continue
            host_dir = os.path.join(inventory_dir, "host_vars", host)
            var_file = os.path.join(host_dir, "{}.yml".format(host))
            content = yaml.safe_dump(vars, default_flow_style=False, encoding='utf-8', allow_unicode=True).decode(
                'utf-8')

            os.makedirs(host_dir)
            with open(var_file, "w") as text_file:
                text_file.write(content)

    def get_inventory_config_string(self):
        """Returns a string that can be used to write an ansible hosts file, including hosts, groups and child-groups."""

        jinja_env = Environment(loader=PackageLoader('nsbl', 'templates'))
        template = jinja_env.get_template('hosts')
        output_text = template.render(groups=self.groups, hosts=self.hosts)

        return output_text

    def write_inventory_file_or_script(self, inventory_dir, extract_vars=False, relative_paths=True):
        """Writes an ansible hosts file or dynamic inventory script into the provided directory.

        Writing a dynamic inventory script is not implemented yet.

        Args:
          inventory_dir (str): the target directory
          extract_vars (bool): whether to extract all vars (True, default) or write a dynamic inventory script
          relative_paths (bool): only important for when writing dynamic inventory scripts, makes the paths in the script relative to the ansible environment root so its easily copy-able
        """

        if extract_vars:
            inventory_string = self.get_inventory_config_string()
            inventory_name = "hosts"
            inventory_file = os.path.join(inventory_dir, inventory_name)

            with open(inventory_file, "w") as text_file:
                text_file.write(inventory_string)

        else:
            raise Exception("Dynamic inventory script creation not implemented yet.")
            # else:
            # # write dynamic inventory script
            # jinja_env = Environment(loader=PackageLoader('nsbl', 'templates'))
            # if relative_paths:
            #     template = jinja_env.get_template('inventory_relative')
            # else:
            #     template = jinja_env.get_template('inventory_absolute')

            # if relative_paths:
            #     for path in self.configs:
            #         rel_path = os.path.relpath(path, inventory_dir)
            #         rel_configs.append(rel_path)

            #     script_configs = " --config ".join(rel_configs)
            # else:
            #     abs_configs = []
            #     for path in self.configs:
            #         abs_path = os.path.abspath(path)
            #         abs_configs.append(abs_path)
            #     script_configs = " --config".join(abs_configs)


            # output_text = template.render(role_repo_paths=roles_repos_string, nsbl_script_configs=script_configs)

            # inventory_string = self.get_inventory_config_string()
            # inventory_target_name = "inventory"

            # inventory_file = os.path.join(inventory_dir, inventory_target_name)

            # with open(inventory_file, "w") as text_file:
            #     text_file.write(output_text)

            # st = os.stat(inventory_file)
            # os.chmod(inventory_file, 0o775)
            # pass

    def add_group(self, group_name, group_vars):
        """Add a group to the dynamic inventory.

        Args:
          group_name (str): the name of the group
          group_vars (dict): the variables for this group
        """

        if group_name in self.groups.keys():
            raise NsblException("Group '{}' defined twice".format(group_name))

        self.groups[group_name] = {}
        self.groups[group_name]["vars"] = group_vars
        self.groups[group_name]["hosts"] = []
        self.groups[group_name]["children"] = []

    def add_host(self, host_name, host_vars):
        """Add a host to the dynamic inventory.

        Args:
          host_name (str): the name of the host
          host_vars (dict): the variables for this host
        """

        if host_name not in self.hosts.keys():
            self.hosts[host_name] = {VARS_KEY: {}}

        if not host_vars:
            return

        intersection = set(self.hosts[host_name].get(VARS_KEY, {}).keys()).intersection(host_vars.keys())

        if intersection:
            raise NsblException(
                "Adding host more than once with intersecting keys, this is not possible because it's not clear which vars should take precedence. Intersection: {}".format(
                    intersection))

        self.hosts[host_name][VARS_KEY].update(host_vars)

    def add_group_to_group(self, child, group):
        """Adds a group as a subgroup of another group.

        Args:
          child (str): the name of the sub-group
          group (str): the name of the parent group
        """

        if group not in self.groups[group]["children"]:
            self.groups[group]["children"].append(child)

    def add_host_to_group(self, host, group):
        """Adds a host to a group.

        Args:
          host (str): the name of the host
          group (str): the name of the parent group
        """

        if host not in self.groups[group]["hosts"]:
            self.groups[group]["hosts"].append(host)

        self.add_host(host, None)

    def callback(self, env):
        """Adds a new environment, and sorts it into the appropriate internal variable."""

        if ENV_META_KEY not in env.keys():
            raise NsblException(
                "Environment does not have metadata (missing '{}') key: {})".format(ENV_META_KEY, env))
        env_type = env[ENV_META_KEY].get(ENV_TYPE_KEY, False)
        if not env_type:
            if ENV_HOSTS_KEY in env[ENV_META_KEY].keys():
                env_type = ENV_TYPE_GROUP
            elif ENV_GROUPS_KEY in env[ENV_META_KEY].keys():
                env_type = ENV_TYPE_HOST
            else:
                env_type = self.default_env_type

        env_name = env[ENV_META_KEY].get(ENV_NAME_KEY, False)
        if not env_name:
            raise NsblException(
                "Environment metadata needs to contain a name (either host- or group-name): {}".format(
                    env[ENV_META_KEY]))

        if env_type == ENV_TYPE_HOST:

            self.add_host(env_name, env.get(VARS_KEY, {}))

            if ENV_HOSTS_KEY in env.get(ENV_META_KEY, {}).keys():
                raise NsblException(
                    "An environment of type {} can't contain the {} key".format(ENV_TYPE_HOST, ENV_HOSTS_KEY))

            for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
                self.add_host_to_group(env_name, group)

        elif env_type == ENV_TYPE_GROUP:

            self.add_group(env_name, env.get(VARS_KEY, {}))

            for host in env[ENV_META_KEY].get(ENV_HOSTS_KEY, []):
                self.add_host_to_group(host, env_name)

            for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
                self.add_group_to_group(group, env_name)

        else:
            raise NsblException("Environment type needs to be either 'host' or 'group': {}".format(env_type))

        if TASKS_KEY in env.keys():
            current_meta = copy.deepcopy(env[ENV_META_KEY])
            current_meta[ENV_ID_KEY] = self.current_env_id
            env_name = env[ENV_META_KEY].get(ENV_NAME_KEY, False)
            if not env_name:
                raise NsblException(
                    "Environment metadata needs to contain a name (either host- or group-name): {}".format(
                        env[ENV_META_KEY]))
            current_meta[ENV_NAME_KEY] = env_name
            self.tasks.append(
                {TASKS_META_KEY: current_meta, TASKS_KEY: env[TASKS_KEY], VARS_KEY: env.get(VARS_KEY, {})})
            self.current_env_id += 1

    def finished(self):
        if "localhost" in self.hosts.keys() and "ansible_connection" not in self.hosts["localhost"].get(VARS_KEY,
                                                                                                        {}).keys():
            self.hosts["localhost"][VARS_KEY]["ansible_connection"] = "local"

        if "localhost" in self.hosts.keys() and "ansible_python_interpreter" not in self.hosts["localhost"].get(VARS_KEY,
                                                                                                        {}).keys():

            if not os.path.exists("/usr/bin/python"):
                self.hosts["localhost"][VARS_KEY]["ansible_python_interpreter"] = sys.executable


    def list(self):
        """Lists all groups in the format that is required for ansible dynamic inventories.

        More info: https://docs.ansible.com/ansible/intro_dynamic_inventory.html, http://docs.ansible.com/ansible/dev_guide/developing_inventory.html

        Returns:
        dict: a dict containing all information about all hosts/groups
        """

        result = copy.copy(self.groups)
        result["_meta"] = {"hostvars": self.hosts}

        # return json.dumps(result, sort_keys=4, indent=4)
        return result

    def host(self, host):
        """Returns the inventory information for the specified host, in the format required for ansible dynamic inventories.

        Args:
          host (str): the name of the host
        Returns:
        dict: all inventory information for this host
        """

        host_vars = self.hosts.get(host, {}).get(VARS_KEY, {})
        return host_vars

    def get_vars(self, env_name):
        """Returns all variables for the environment with the specified name.

        First tries whether the name matches a group, then tries hosts.

        Args:
          env_name (str): the name of the group or host
        Returns:
          dict: the variables for the environment
        """

        if env_name in self.groups.keys():
            return self.groups[env_name].get(VARS_KEY, {})
        elif env_name in self.hosts.keys():
            return self.hosts[env_name].get(VARS_KEY, {})
        else:
            raise NsblException("Neither group or host with name '{}' exists".format(env_name))


class WrapTasksIntoLocalhostEnvProcessor(ConfigProcessor):
    """Wraps a list of tasks into a localhost environment.

    Convenience processor to not have to do this manually, keeps configuration files minimal and sweet.
    """

    def __init__(self, init_params=None):
        super(WrapTasksIntoLocalhostEnvProcessor, self).__init__(init_params)

        self.task_configs = []

    def validate_init(self):

        self.task_vars = self.init_params.get(VARS_KEY, {})

        return True

    def handles_last_call(self):

        return True

    def process_current_config(self):

        config = self.current_input_config

        if not self.last_call:
            self.task_configs.append(config)
        else:
            return {"localhost": {TASKS_KEY: self.task_configs, TASKS_META_KEY: {ENV_TYPE_KEY: ENV_TYPE_HOST},
                                  VARS_KEY: self.task_vars}}

class WrapTasksIntoHostsProcessor(ConfigProcessor):
    """Wraps a list of tasks into a localhost environment.

    Convenience processor to not have to do this manually, keeps configuration files minimal and sweet.
    """

    def __init__(self, init_params=None):
        super(WrapTasksIntoLocalhostEnvProcessor, self).__init__(init_params)

        self.task_configs = []

    def validate_init(self):

        self.task_vars = self.init_params.get(VARS_KEY, {})
        self.hosts = self.init_params.get(ENV_HOSTS_KEY, {})

        return True

    def handles_last_call(self):

        return True

    def process_current_config(self):

        config = self.current_input_config

        if not self.last_call:
            self.task_configs.append(config)
        else:
            return {"localhost": {TASKS_KEY: self.task_configs, TASKS_META_KEY: {ENV_TYPE_KEY: ENV_TYPE_HOST},
                                  VARS_KEY: self.task_vars}}
