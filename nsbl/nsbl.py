# -*- coding: utf-8 -*-

from jinja2 import Environment, PackageLoader
import pprint
import json
import copy
import os
import subprocess
import shutil
import yaml
import sys

from six import string_types
from collections import OrderedDict
from cookiecutter.main import cookiecutter
from frkl import Frkl, dict_merge, DEFAULT_LEAF_DEFAULT_KEY, ConfigProcessor
from frkl import CHILD_MARKER_NAME, DEFAULT_LEAF_NAME, DEFAULT_LEAFKEY_NAME, KEY_MOVE_MAP_NAME, OTHER_KEYS_NAME, START_VALUES_NAME, UrlAbbrevProcessor, EnsureUrlProcessor, EnsurePythonObjectProcessor, FrklProcessor, Jinja2TemplateProcessor, IdProcessor

import logging
log = logging.getLogger("nsbl")

ENVS_KEY = "envs"
ENV_META_KEY = "meta"
ENV_NAME_KEY = "name"
ENV_TYPE_KEY = "type"
ENV_HOSTS_KEY = "hosts"
ENV_GROUPS_KEY = "groups"
VARS_KEY = "vars"

TASKS_META_KEY = "meta"
TASKS_KEY = "tasks"
TASK_NAME_KEY = "name"
TASK_TYPE_KEY = "type"
TASK_PRIORITY_KEY = "priority"
TASK_BECOME_KEY = "become"
TASK_IGNORE_ERRORS_KEY = "ignore_errors"
TASK_ALLOWED_VARS_KEY = "allowed_vars"
TASK_ROLES_KEY = "roles"

TASK_TYPE_TASK = "ansible_task"
TASK_TYPE_ROLE = "ansible_role"

INT_TASK_TYPE = "internal_role"
EXT_TASK_TYPE = "external_role"
DYN_TASK_TYPE = "single_task"
DYN_ROLE_TYPE = "dynamic_role"

ROLE_META_FILENAME = "meta.yml"

NSBL_INVENTORY_BOOTSTRAP_FORMAT = {
    CHILD_MARKER_NAME: ENVS_KEY,
    DEFAULT_LEAF_NAME: ENV_META_KEY,
    DEFAULT_LEAFKEY_NAME: ENV_NAME_KEY,
    OTHER_KEYS_NAME: [VARS_KEY, TASKS_KEY],
    KEY_MOVE_MAP_NAME: VARS_KEY
}
NSBL_INVENTORY_BOOTSTRAP_CHAIN = [
    UrlAbbrevProcessor(), EnsureUrlProcessor(), EnsurePythonObjectProcessor(), FrklProcessor(NSBL_INVENTORY_BOOTSTRAP_FORMAT)
]

DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT = {
    CHILD_MARKER_NAME: TASKS_KEY,
    DEFAULT_LEAF_NAME: TASKS_META_KEY,
    DEFAULT_LEAFKEY_NAME: TASK_NAME_KEY,
    KEY_MOVE_MAP_NAME: VARS_KEY,
    "use_context": True
}
NSBL_TASKS_TEMPLATE_INIT = {
    "use_environment_vars": True,
    "use_context": True
}

ID_NAME = "id"
NSBL_TASKS_ID_INIT = {
    "id_key": TASKS_META_KEY,
    "id_name": ID_NAME
}
# DEFAULT_NSBL_TASKS_BOOTSTRAP_CHAIN = [
    # UrlAbbrevProcessor(), EnsureUrlProcessor(), Jinja2TemplateProcessor(NSBL_TASKS_TEMPLATE_INIT), EnsurePythonObjectProcessor(), FrklProcessor(DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT), IdProcessor(NSBL_TASKS_ID_INIT)
# ]

DEFAULT_NSBL_TASKS_BOOTSTRAP_CHAIN = [
    FrklProcessor(DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT)
]

class NsblException(Exception):

    def __init__(self, message):

        super(NsblException, self).__init__(message)

ENV_TYPE_HOST = 'host'
ENV_TYPE_GROUP = 'group'
DEFAULT_ENV_TYPE = ENV_TYPE_GROUP

class RepoRoles(object):

    def __init__(self, folders):

        if isinstance(folders, string_types):
            self.folders = [folders]
        else:
            self.folders = folders
        self.roles = self.read_role_repos()

    def read_role_repos(self):

        result = {}

        for repo in self.folders:
            for basename in [name for name in os.listdir(repo) if os.path.isdir(os.path.join(repo, name))]:

                roles_metadata = os.path.join(repo, basename, ROLE_META_FILENAME)

                dependencies = []
                default_role = None
                roles = {}
                if os.path.exists(roles_metadata):
                    with open(roles_metadata) as f:
                        content = yaml.load(f)

                    if "dependencies" in content.keys():
                        dependencies = content["dependencies"]
                        if isinstance(dependencies, string_types):
                            dependencies = [dependencies]
                    if "default_role" in content.keys():
                        default_role = content["default_role"]

                    if "roles" in content.keys():
                        roles = content["roles"]

                roles_path = os.path.join(repo, basename, "roles")

                if not default_role and os.path.exists(os.path.join(roles_path, basename)):
                    default_role = basename
                elif not default_role:
                    if os.path.exists(os.path.join(roles_path)):
                        child_dirs = [name for name in os.listdir(roles_path) if  os.path.isdir(os.path.join(roles_path, name))]
                        if len(child_dirs) == 1:
                            default_role = child_dirs[0]
                    else:
                        if len(roles) == 1:
                            default_role = list(roles.keys())[0]
                if not default_role:
                    log.error("No default role found for: {}".format(basename))
                    continue

                if basename in result.keys():
                    raise Exception("Multiple roles/tasks with name in role repositories: {}".format(basename))

                result[basename] = {"roles_path": roles_path, "default_role": default_role, "dependencies": dependencies, TASK_ROLES_KEY: roles}

        return result

class Nsbl(object):

    def __init__(self, configs, roles_repos, default_env_type=DEFAULT_ENV_TYPE):

        self.configs = configs
        self.roles_repos = roles_repos
        self.repo_roles = RepoRoles(self.roles_repos)
        self.inventory = NsblInventory(self.configs, self.repo_roles, default_env_type)
        self.tasks = []
        self.tasks = self.inventory.tasks
        self.ansible_roles = {}

    def get_all_roles():
        pass

    def render_environment(self, env_dir):

        parent_dir = os.path.abspath(os.path.join(env_dir, os.pardir))
        link_dir = None

        rel_configs = []
        inventory_dir = os.path.join(env_dir, "inventory")
        for path in self.configs:
            rel_path = os.path.relpath(path, inventory_dir)
            rel_configs.append(rel_path)

        cookiecutter_details = {
            "env_dir": env_dir,
            "nsbl_script_configs": " --config ".join(rel_configs),
            "nsbl_roles": self.ansible_roles,
            "nsbl_callback_plugins": "",
            "nsbl_callback_plugin_name": ""
            }

        log.debug("Creating build environment from template...")
        log.debug("Using cookiecutter details: {}".format(cookiecutter_details))

        template_path = os.path.join(os.path.dirname(__file__), "external", "cookiecutter-ansible-environment")
        cookiecutter(template_path, extra_context=cookiecutter_details, no_input=True)

        # add 'internal' roles
        ext_roles = False
        for idx, task in enumerate(self.tasks):

            if task.ext_roles:
                ext_roles = True

            for role in task.roles:
                role.prepare_role(env_dir)

            content = self.render_playbook(task)
            playbook_name = "play_{}_{}.yml".format(idx, task.task_env)

            playbook_file = os.path.join(env_dir, "plays", playbook_name)

            with open(playbook_file, "w") as text_file:
                text_file.write(content)

        if ext_roles:
            # download external roles
            log.info("Downloading and installing external roles...")
            res = subprocess.check_output([os.path.join(env_dir, "extensions", "setup", "role_update.sh")])
            for line in res.splitlines():
                log.debug("Installing role: {}".format(line.encode('utf8')))



    def render_playbook(self, task):

        jinja_env = Environment(loader=PackageLoader('nsbl', 'templates'))
        template = jinja_env.get_template('playbook.yml')

        output_text = template.render(groups=task.task_env, roles=task.roles, meta=task.meta_vars)

        return output_text

class NsblInventory(object):

    def __init__(self, configs, repo_roles={}, default_env_type=DEFAULT_ENV_TYPE):

        self.frkl_obj = Frkl(configs, NSBL_INVENTORY_BOOTSTRAP_CHAIN)
        self.config = self.frkl_obj.process()
        self.default_env_type = default_env_type
        self.repo_roles = repo_roles
        self.groups = {}
        self.hosts = {}
        self.tasks = []

        self.assemble_groups()

    def add_group(self, group_name, group_vars):

        if group_name in self.groups.keys():
            raise NsblException("Group '{}' defined twice".format(group_name))

        self.groups[group_name] = {}
        self.groups[group_name]["vars"] = group_vars
        self.groups[group_name]["hosts"] = []
        self.groups[group_name]["children"] = []

    def add_host(self, host_name, host_vars):

        if host_name in self.hosts.keys():
            raise NsblException("Host '{}' defined twice".format(host_name))

        self.hosts[host_name] = host_vars
        if host_name == "localhost" and "ansible_connection" not in host_vars.keys():
            self.hosts[host_name]["ansible_connection"] = "local"

    def add_group_to_group(self, child, group):

        if group not in self.groups[group]["children"]:
            self.groups[group]["children"].append(child)

    def add_host_to_group(self, host, group):

        if host not in self.groups[group]["hosts"]:
            self.groups[group]["hosts"].append(host)

    def assemble_groups(self):

        for env in self.config:
            if ENV_META_KEY not in env.keys():
                raise NsblException("Environment does not have metadata (missing '{}') key: {})".format(ENV_META_KEY, env))
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
                raise NsblException("Environment metadata needs to contain a name (either host- or group-name): {}".format(env[ENV_META_KEY]))

            if env_type == ENV_TYPE_HOST:
                self.add_host(env_name, env[VARS_KEY])

                if ENV_HOSTS_KEY in env[ENV_META_KEY].keys():
                    raise NsblException("An environment of type {} can't contain the {} key".format(ENV_TYPE_HOST, ENV_HOSTS_KEY))

                for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
                    self.add_host_to_group(env_name, group)

            elif env_type == ENV_TYPE_GROUP:

                self.add_group(env_name, env.get(VARS_KEY, {}))

                for host in env[ENV_META_KEY].get(ENV_HOSTS_KEY, []):
                    self.add_host_to_group(host, env_name)
                    if host == "localhost" and "ansible_connection" not in env.get(VARS_KEY, {}).keys():
                        self.add_host("localhost", {})

                for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
                    self.add_group_to_group(group, env_name)

            else:
                raise NsblException("Environment type needs to be either 'host' or 'group': {}".format(env_type))

            if TASKS_KEY in env.keys():
                self.tasks.append(NsblTaskList(env, self.repo_roles, env_name))


    def list(self):

        result = copy.copy(self.groups)
        result["_meta"] = {"hostvars": self.hosts}

        return json.dumps(result, sort_keys=4, indent=4)

    def host(self, host):

        host_vars = self.hosts.get(host, {})
        return json.dumps(host_vars, sort_keys=4, indent=4)

    def get_vars(self, env_name):

        if env_name in self.groups.keys():
            return self.groups[env_name]
        elif env_name in self.hosts.keys():
            return self.hosts[env_name]
        else:
            raise NsblException("Neither group or host with name '{}' exists".format(env_name))


class NsblTaskProcessor(ConfigProcessor):

    def validate_init(self):

        self.meta_roles = self.init_params['env'].get(TASKS_META_KEY, {}).get(TASK_ROLES_KEY, {})
        self.repo_roles = self.init_params['repo_roles']

        return True

    def process_current_config(self):

        new_config = self.current_input_config

        roles = new_config.get(TASKS_META_KEY, {}).get(TASK_ROLES_KEY, {})

        task_name = new_config[TASKS_META_KEY][TASK_NAME_KEY]

        if task_name in self.repo_roles.roles.keys():
            task_type = INT_TASK_TYPE
            task_roles = self.repo_roles.roles[task_name]

        elif task_name in roles.keys() or task_name in self.meta_roles.keys():
            task_type = EXT_TASK_TYPE
            task_roles = self.expand_external_role(roles)
        else:
            task_type = DYN_TASK_TYPE
            task_roles = {}

        new_config[TASKS_META_KEY][TASK_TYPE_KEY] = task_type
        new_config[TASKS_META_KEY][TASK_ROLES_KEY] = task_roles
        return new_config

    def expand_external_role(self, role_dict):

        result = {}
        for role_name, role_details in role_dict.items():
            temp_role = {}
            if isinstance(role_details, string_types):
                temp_role["url"] = role_details
            elif isinstance(role_details, dict):
                temp_role["url"] = role_details["url"]
                if "version" in role_details.keys():
                    temp_role["version"] = role_details["version"]
            result[role_name] = temp_role

        return result


class NsblDynamicRoleProcessor(ConfigProcessor):

    def validate_init(self):
        self.id_role = 0
        self.current_tasks = []
        return True

    def handles_last_call(self):

        return True

    def create_role_dict(self, tasks):

        dyn_role = {
            TASKS_META_KEY: {
                TASK_NAME_KEY: "dyn_role_{}".format(self.id_role),
                TASK_ROLES_KEY: copy.deepcopy(self.current_tasks),
                TASK_TYPE_KEY: DYN_ROLE_TYPE
            },
            VARS_KEY: {}
        }

        return dyn_role

    def process_current_config(self):

        if not self.last_call:

            new_config = self.current_input_config

            if new_config[TASKS_META_KEY][TASK_TYPE_KEY] == DYN_TASK_TYPE:
                self.current_tasks.append(new_config)
                yield None
            else:
                if len(self.current_tasks) > 0:
                    dyn_role = self.create_role_dict(self.current_tasks)
                    self.id_role = self.id_role+1
                    self.current_tasks = []

                    yield dyn_role

                yield new_config
        else:
            if len(self.current_tasks) > 0:
                yield self.create_role_dict(self.current_tasks)
            else:
                yield None


class NsblTaskList(object):

    def __init__(self, env, repo_roles, env_name="localhost"):

        self.env = env
        self.env_name = env_name
        self.repo_roles = repo_roles

        nsbl_task_processor = NsblTaskProcessor({'env': self.env, 'repo_roles': self.repo_roles})

        nsbl_dynrole_processor = NsblDynamicRoleProcessor()
        id_processor = IdProcessor(NSBL_TASKS_ID_INIT)

        # otherwise each tasks inherits from the ones before
        temp_tasks = [[name] for name in self.env[TASKS_KEY]]
        frkl_obj = Frkl(temp_tasks, DEFAULT_NSBL_TASKS_BOOTSTRAP_CHAIN + [nsbl_task_processor, nsbl_dynrole_processor, id_processor])
        # frkl_obj = Frkl(temp_tasks, DEFAULT_NSBL_TASKS_BOOTSTRAP_CHAIN + [nsbl_task_processor])
        self.tasks = frkl_obj.process()
        self.ext_roles = {}
        self.int_roles = []
        self.dyn_roles = {}

        self.process_tasks()

        for task, roles in self.ext_roles.items():
            print("-------------------")
            pprint.pprint(task)
            pprint.pprint(roles)
            print("---")
        sys.exit(0)

    def add_ext_roles(self, new_roles):

        for role_name, role in new_roles.items():
            if role_name in self.ext_roles.keys():
                if role != self.ext_roles["role_name"]:
                    raise Exception("Role '{}' added multiple times, with different urls/versions: {} - {}".format(role_name, role, self.ext_roles[role_name]))
            else:
                self.ext_roles[role_name] = role

    def add_int_role(self, role):

        role_path = role["roles_path"]


    def process_tasks(self):

        for task in self.tasks:

            task_type = task[TASKS_META_KEY][TASK_TYPE_KEY]
            if task_type == INT_TASK_TYPE:
                new_ext_roles = task[TASKS_META_KEY][TASK_ROLES_KEY][TASK_ROLES_KEY]
                self.add_ext_roles(new_ext_roles)
                self.add_int_role(task[TASKS_META_KEY][TASK_ROLES_KEY])
            elif task_type == DYN_ROLE_TYPE:
                pass
            elif task_type == EXT_TASK_TYPE:
                new_roles = task[TASKS_META_KEY][TASK_ROLES_KEY]
                self.add_ext_roles(new_roles)

            else:
                raise Exception("Task type '{}' not known.".format(task_type))



# class NsblDynRole(NsblRole):

#     def __init__(self, tasks, role_name, meta_vars={}, default_priority=10000, default_ignore_errors=True):

#         self.role_name = role_name
#         self.become = None
#         self.tasks = {}
#         self.meta_vars = meta_vars
#         self.vars = {}

#         for idx, task in enumerate(tasks):

#             task_id = task[TASKS_META_KEY][ID_NAME]

#             self.task_roles = task[TASKS_META_KEY].get(TASK_ROLES_KEY, {})

#             task_become = task[TASKS_META_KEY].get(TASK_BECOME_KEY, None)
#             task_ignore_errors = task[TASKS_META_KEY].get(TASK_IGNORE_ERRORS_KEY, default_ignore_errors)
#             task_module = task[TASKS_META_KEY][TASK_NAME_KEY]
#             task_vars = task.get(VARS_KEY, {})

#             if DEFAULT_LEAF_DEFAULT_KEY in task_vars.keys() and 'free_form' not in task_vars.keys():
#                 task_vars['free_form'] = task_vars.pop(DEFAULT_LEAF_DEFAULT_KEY)

#             self.vars["task_{}".format(task_id)] = task_vars

#             if TASK_ALLOWED_VARS_KEY in task[TASKS_META_KEY].keys():
#                 task_allowed_vars = task[TASKS_META_KEY][TASK_ALLOWED_VARS_KEY]
#             else:
#                 task_allowed_vars = list(task[TASKS_META_KEY].get(VARS_KEY, {}).keys())

#             free_form = "free_form" in task_vars.keys()
#             if free_form and 'free_form' in task_allowed_vars:
#                 task_allowed_vars.remove('free_form')
#             if task[TASKS_META_KEY].get(TASK_PRIORITY_KEY, False):
#                 priority = task[TASKS_META_KEY][TASK_PRIORITY_KEY]
#             else:
#                 priority = default_priority + (idx * 10)

#             key = "{:04d}_{:04d} -> {}".format(priority, task_id, task_module)

#             self.tasks[key] = {"vars": task_vars, "module": task_module, "free_form": free_form, "priority": priority, "id": task_id, "ignore_errors": task_ignore_errors, "allowed_vars": task_allowed_vars}
#             if task_become is not None:
#                 self.tasks[key]["become"] = task_become

#         self.signature = []
#         for task_name in sorted(self.tasks):
#             self.signature.append(self.tasks[task_name]["module"])

#     def get_required_roles(self):

#         return {self.role_name: {"type": "dynamic", "tasks": self.tasks}}

#     # def prepare_role(self, env_dir):

#     #     role_local_path = os.path.join(os.path.dirname(__file__), "external", "ansible-role-template")
#     #     role_dict = {
#     #         "role_name": self.role_name,
#     #         "tasks": self.tasks,
#     #     }

#     #     current_dir = os.getcwd()
#     #     int_roles_base_dir = os.path.join(env_dir, "roles", "dynamic")
#     #     os.chdir(int_roles_base_dir)
#     #     cookiecutter(role_local_path, extra_context=role_dict, no_input=True)
#     #     os.chdir(current_dir)
