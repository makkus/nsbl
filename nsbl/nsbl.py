# -*- coding: utf-8 -*-

from jinja2 import Environment, PackageLoader
import pprint
import json
import copy
import os
import subprocess

from six import string_types
from collections import OrderedDict
from cookiecutter.main import cookiecutter
from frkl import Frkl, dict_merge, DEFAULT_LEAF_DEFAULT_KEY
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
DEFAULT_NSBL_TASKS_BOOTSTRAP_CHAIN = [
    UrlAbbrevProcessor(), EnsureUrlProcessor(), Jinja2TemplateProcessor(NSBL_TASKS_TEMPLATE_INIT), EnsurePythonObjectProcessor(), FrklProcessor(DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT), IdProcessor(NSBL_TASKS_ID_INIT)
]

def create_tasks_bootstrap_chain(init_vars={}):

    nsbl_tasks_bootstrap_format = {
        CHILD_MARKER_NAME: TASKS_KEY,
        DEFAULT_LEAF_NAME: TASKS_META_KEY,
        DEFAULT_LEAFKEY_NAME: TASK_NAME_KEY,
        KEY_MOVE_MAP_NAME: VARS_KEY,
        "use_context": True,
        START_VALUES_NAME: init_vars
    }

    nsbl_tasks_bootstrap_chain = [
        FrklProcessor(nsbl_tasks_bootstrap_format), IdProcessor(NSBL_TASKS_ID_INIT)
    ]

    return nsbl_tasks_bootstrap_chain

class NsblException(Exception):

    def __init__(self, message):

        super(NsblException, self).__init__(message)

ENV_TYPE_HOST = 'host'
ENV_TYPE_GROUP = 'group'
DEFAULT_ENV_TYPE = ENV_TYPE_GROUP

class Nsbl(object):

    def __init__(self, configs, default_env_type=DEFAULT_ENV_TYPE):

        self.configs = configs
        self.inventory = NsblInventory(self.configs, default_env_type)
        self.tasks = []
        self.ansible_roles = {}

        for task_env, tasks, in self.inventory.tasks.items():

            # init_vars = self.inventory.get_vars(task_env)
            nsbl_task = NsblTasks(task_env, {}, tasks)
            self.tasks.append(nsbl_task)

            task_roles = nsbl_task.ansible_roles
            for role_name, role_desc in task_roles.items():

                if role_name in self.ansible_roles.keys() and not self.ansible_roles[role_name] == role_desc:
                    raise NsblException("Role with name {} specified twice, with different values: '{}' - '{}'".format(role_name, role_desc, self.ansible_roles[role_name]))
                self.ansible_roles[role_name] = role_desc


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

        output_text = template.render(groups=task.task_env, roles=task.roles)

        return output_text

class NsblInventory(object):

    def __init__(self, configs, default_env_type=DEFAULT_ENV_TYPE):

        self.frkl_obj = Frkl(configs, NSBL_INVENTORY_BOOTSTRAP_CHAIN)
        self.config = self.frkl_obj.process()
        self.default_env_type = default_env_type
        self.groups = {}
        self.hosts = {}
        self.tasks = OrderedDict()

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
                self.tasks[env_name] = env[TASKS_KEY]


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

class NsblRole(object):

    def __repr__(self):

        return str(self.get_role_desc())

    def get_role_desc(self):

        return {"role_name": self.role_name, "vars": self.vars, "become": self.become}

class NsblExtRole(NsblRole):

    def __init__(self, tasks):

        self.role_name = tasks[TASKS_META_KEY][TASK_NAME_KEY]
        self.vars = tasks[VARS_KEY]
        self.become = tasks[TASKS_META_KEY].get(TASK_BECOME_KEY, False)

    def prepare_role(self, env_dir):

        pass


class NsblIntRole(NsblRole):

    def __init__(self, tasks):

        self.role_name = tasks[TASKS_META_KEY][TASK_NAME_KEY]
        self.become = tasks[TASKS_META_KEY].get(TASK_BECOME_KEY, False)
        self.vars = tasks[VARS_KEY]

    def prepare_role(self, env_dir):

        print("preparing int role")

    def get_role_desc(self):

        return { "role": self.role_name, "become": self.become, "vars": self.vars }


class NsblDynRole(NsblRole):

    def __init__(self, tasks, role_name, base_vars={}, default_priority=10000, default_become=False, default_ignore_errors=True):

        self.role_name = role_name
        self.become = False
        self.tasks = {}
        self.vars = {}

        for idx, task in enumerate(tasks):

            # if task[TASKS_META_KEY].get(TASK_BECOME_KEY, False):
                # self.become = True

            task_id = task[TASKS_META_KEY][ID_NAME]

            self.task_roles = task[TASKS_META_KEY].get(TASK_ROLES_KEY, {})

            task_become = task[TASKS_META_KEY].get(TASK_BECOME_KEY, default_become)
            task_ignore_errors = task[TASKS_META_KEY].get(TASK_IGNORE_ERRORS_KEY, default_ignore_errors)
            task_module = task[TASKS_META_KEY][TASK_NAME_KEY]
            task_vars = task.get(VARS_KEY, {})

            if DEFAULT_LEAF_DEFAULT_KEY in task_vars.keys() and 'free_form' not in task_vars.keys():
                task_vars['free_form'] = task_vars.pop(DEFAULT_LEAF_DEFAULT_KEY)

            self.vars["task_{}".format(task_id)] = task_vars

            if TASK_ALLOWED_VARS_KEY in task[TASKS_META_KEY].keys():
                task_allowed_vars = task[TASKS_META_KEY][TASK_ALLOWED_VARS_KEY]
            else:
                task_allowed_vars = list(task[TASKS_META_KEY].get(VARS_KEY, {}).keys())

            free_form = "free_form" in task_vars.keys()
            if free_form and 'free_form' in task_allowed_vars:
                task_allowed_vars.remove('free_form')
            if task[TASKS_META_KEY].get(TASK_PRIORITY_KEY, False):
                priority = task[TASKS_META_KEY][TASK_PRIORITY_KEY]
            else:
                priority = default_priority + (idx * 10)

            key = "{:04d}_{:04d} -> {}".format(priority, task_id, task_module)

            self.tasks[key] = {"vars": task_vars, "module": task_module, "free_form": free_form, "priority": priority, "id": task_id, "become": task_become, "ignore_errors": task_ignore_errors, "allowed_vars": task_allowed_vars}

        self.signature = []
        for task_name in sorted(self.tasks):
            self.signature.append(self.tasks[task_name]["module"])

    def prepare_role(self, env_dir):

        role_local_path = os.path.join(os.path.dirname(__file__), "external", "ansible-role-template")
        role_dict = {
            "role_name": self.role_name,
            "tasks": self.tasks,
        }

        current_dir = os.getcwd()
        int_roles_base_dir = os.path.join(env_dir, "roles", "dynamic")
        os.chdir(int_roles_base_dir)
        cookiecutter(role_local_path, extra_context=role_dict, no_input=True)
        os.chdir(current_dir)


class NsblTasks(object):

    def __init__(self, task_env, init_vars={}, *configs):

        self.task_env = task_env
        self.configs = configs
        bootstrap_chain = create_tasks_bootstrap_chain(init_vars)
        self.frkl_obj = Frkl(configs, bootstrap_chain)
        self.tasks = self.frkl_obj.process()
        self.ansible_roles = {}
        self.roles = []
        self.ext_roles = False

        self.process()

    def __repr__(self):

        return "NsblTasks(env='{}', roles='{}')".format(self.task_env, self.roles)


    def process(self):

        current_tasks = []

        dyn_role_nr = 1

        # gather all ansible roles
        for task in self.tasks:

            task_roles = task[TASKS_META_KEY].get(TASK_ROLES_KEY, {})
            for role_name in task_roles.keys():
                if role_name in self.ansible_roles.keys() and task_roles[role_name] != self.ansible_roles[role_name]:
                    raise NsblException("Role with name '{}' specified twice, with different values: {} - {}".format(role_name, task_roles[role_name], self.ansible_roles[role_name]))

                role = task_roles[role_name]
                if isinstance(role, string_types):
                    role = {"url": role}
                elif not isinstance(role, dict) or "url" not in role.keys():
                    raise NsblException("Role value needs to be string or dict with 'url' and possibly 'version' key: {}".format(role))

                self.ansible_roles[role_name] = role

        #TODO: check for 'internal' role repos

        for task in self.tasks:

            task_name = task[TASKS_META_KEY][TASK_NAME_KEY]

            if TASK_TYPE_KEY not in task[TASKS_META_KEY].keys():
                if task_name in self.ansible_roles.keys():
                    task[TASKS_META_KEY][TASK_TYPE_KEY] = TASK_TYPE_ROLE
                else:
                    task[TASKS_META_KEY][TASK_TYPE_KEY] = TASK_TYPE_TASK

            if task[TASKS_META_KEY][TASK_TYPE_KEY] == TASK_TYPE_TASK:
                current_tasks.append(task)
            elif len(current_tasks) > 0:
                new_role = self.create_dyn_role(current_tasks, "dyn_role_{}".format(dyn_role_nr))
                self.roles.append(new_role)
                dyn_role_nr = dyn_role_nr + 1
                current_tasks = []
                self.roles.append(self.create_role(task))
            else:
                self.roles.append(self.create_role(task))

        if len(current_tasks) > 0:
            new_role = self.create_dyn_role(current_tasks, "dyn_role_{}".format(dyn_role_nr))
            current_tasks = []
            self.roles.append(new_role)



    def create_dyn_role(self, tasks, role_name):

        role = NsblDynRole(tasks, role_name)
        return role

    def create_role(self, task):

        ansible_role = self.ansible_roles[task[TASKS_META_KEY][TASK_NAME_KEY]]

        if ansible_role['url'].startswith("nsbl:"):
            role = NsblIntRole(task)
        else:
            role = NsblExtRole(task)
            self.ext_roles = True

        return role
