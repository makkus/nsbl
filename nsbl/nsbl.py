# -*- coding: utf-8 -*-

import click
import copy
import pprint
import json
import shutil
import subprocess
import sys
import cursor

import os
import yaml
from cookiecutter.main import cookiecutter
from frkl import CHILD_MARKER_NAME, DEFAULT_LEAF_NAME, DEFAULT_LEAFKEY_NAME, KEY_MOVE_MAP_NAME, OTHER_KEYS_NAME, \
    UrlAbbrevProcessor, EnsureUrlProcessor, EnsurePythonObjectProcessor, FrklProcessor, \
    IdProcessor, dict_merge, Frkl, ConfigProcessor, FrklCallback
from jinja2 import Environment, PackageLoader
from six import string_types
from .inventory import NsblInventory
from .exceptions import NsblException
from .defaults import *
from .tasks import NsblTasks, NsblTaskProcessor, NsblDynamicRoleProcessor

try:
    set
except NameError:
    from sets import Set as set

import logging

log = logging.getLogger("nsbl")


# ------------------------------
# util functions
class CursorOff(object):
    def __enter__(self):
        cursor.hide()

    def __exit__(self, *args):
        cursor.show()

def get_pkg_mgr_sudo(mgr):
    """Simple function to determine whether a given package manager needs sudo rights or not.
    """
    if mgr == 'no_install':
        return False
    elif mgr == 'nix':
        return False
    elif mgr == 'conda':
        return False
    elif mgr == 'git':
        return False
    elif mgr == 'homebrew':
        return False
    else:
        return True

def get_git_auto_dest_name(repo, parent_dir="~"):

    temp = "{}{}{}".format(parent_dir, os.path.sep, repo.split("/")[-1])

    if temp.endswith(".git"):
        temp = temp[0:-4]

    return temp

def ensure_git_repo_format(repo, dest=None):

    if isinstance(repo, string_types):
        if dest:
            return {"repo": repo, "dest": dest}
        else:
            return {"repo": repo, "dest": get_git_auto_dest_name(repo)}
    elif isinstance(repo, dict):
        if "repo" not in repo.keys():
            raise NsblException("Repo dictionary needs at least a 'repo' key: {}".format(repo))
        if "dest" not in repo.keys():
            if dest:
                repo["dest"] = dest
            else:
                repo["dest"] = get_git_auto_dest_name(repo["repo"])
        return repo
    else:
        raise NsblException("Repo value needs to be either string or dict format: {}".format(repo))


def get_local_role_desc(role_name, role_repos=[]):

    url = False
    if os.path.exists(role_name):
        url = role_name
    else:
        for repo in role_repos:
            path = os.path.join(os.path.expanduser(repo), role_name)
            if os.path.exists(path):
                url = role_name

    if not url:
        raise NsblException("Can't find local role '{}' (neither as absolute path nor in any of the local role repos)".format(role_name))

    return {"url": url}

def merge_roles(role_obj, role_repos=[]):

    role_dict = {}

    if isinstance(role_obj, dict):
        if "url" in role_obj.keys() or "version" in role_obj.keys():
            raise NsblException("Although dictionaries and lists can be mixed for the {} key, dictionaries need to use role-names as keys, the keyworkds 'url' and 'version' are not allowed. Mostly likely this is a misconfiguration.")
        role_dict.update(role_obj)
    elif isinstance(role_obj, string_types):
        temp = get_local_role_desc(role_obj, role_repos)
        role_dict[role_obj] = temp
    elif isinstance(role_obj, (list, tuple)):
        for role_obj_child in role_obj:
            temp = merge_roles(role_obj_child, role_repos)
            role_dict.update(temp)
    else:
        raise NsblException("Role description needs to be either a list of strings or a dict. Value '{}' is not valid.".format(role_obj))

    return role_dict

def expand_external_role(role_dict, role_repos=[]):

    temp_role_dict = merge_roles(role_dict, role_repos)

    result = {}
    for role_name, role_details in temp_role_dict.items():
        temp_role = {}
        if isinstance(role_details, string_types):
            temp_role["url"] = role_details
        elif isinstance(role_details, dict):
            temp_role["url"] = role_details["url"]
            if "version" in role_details.keys():
                temp_role["version"] = role_details["version"]
        result[role_name] = temp_role

    return result

def get_internal_role_path(role_dict, role_repos=[]):

    if isinstance(role_dict, string_types):
        url = role_dict
    elif isinstance(role_dict, dict):
        url = role_dict["url"]
    else:
        raise NsblException("Type '{}' not supported for role description: {}".format(type(role_dict), role_dict))

    if os.path.exists(url):
        return url

    for repo in role_repos:
        path = os.path.join(os.path.expanduser(repo), url)
        if os.path.exists(path):
            return path

    return False


class Nsbl(FrklCallback):

    def __init__(self, init_params=None):
        """Class to receive yaml config files and create an Ansible environment out of them (including inventory and playbooks).
        """

        super(Nsbl, self).__init__(init_params)
        self.inventory = NsblInventory(init_params)
        self.plays = {}

    def validate_init(self):

        self.default_env_type = self.init_params.get('default_env_type', DEFAULT_ENV_TYPE)
        self.role_repos = self.init_params.get('role_repos', [])
        if not self.role_repos:
            self.role_repos = calculate_role_repos([], use_default_roles=True)
        self.task_descs = self.init_params.get('task_descs', [])
        if not self.task_descs:
            self.task_descs = calculate_task_descs(None, self.role_repos)

        return True

    def callback(self, env):

        self.inventory.callback(env)

    def finished(self):

        self.inventory.finished()
        task_format = generate_nsbl_tasks_format(self.task_descs)
        for tasks in self.inventory.tasks:

            meta = tasks[TASKS_META_KEY]
            env_name = meta[ENV_NAME_KEY]
            env_id = meta[ENV_ID_KEY]
            task_config = tasks[TASKS_KEY]

            init_params = {"role_repos": self.role_repos, "task_descs": self.task_descs, "env_name": env_name, "env_id": env_id, TASKS_META_KEY: meta}
            tasks_collector = NsblTasks(init_params)
            self.plays["{}_{}".format(env_name, env_id)] = tasks_collector
            chain = [FrklProcessor(task_format), NsblTaskProcessor(init_params), NsblDynamicRoleProcessor(init_params)]
            # not adding vars here, since we have the inventory to do that...
            # configs = {TASKS_KEY: task_config, TASKS_META_KEY: meta}
            tasks_frkl = Frkl(task_config, chain)

            result = tasks_frkl.process(tasks_collector)

    def result(self):

        return {"inventory": self.inventory, "plays": self.plays}

    def render(self, env_dir, extract_vars=False, force=False, ansible_args="", callback='nsbl_internal'):
        """Creates the ansible environment in the folder provided.

        Args:
          env_dir (str): the folder where the environment should be created
          extract_vars (bool): whether to extract a hostvars and groupvars directory for the inventory (True), or render a dynamic inventory script for the environment (default, False)
          force (bool): overwrite environment if already present at the specified location
          ansible_verbose (str): parameters to give to ansible-playbook (like: "-vvv")
          callback (str): name of the callback to use, default: nsbl_internal
        """

        result = {}
        result['env_dir'] = env_dir
        if os.path.exists(env_dir) and force:
            shutil.rmtree(env_dir)

        inventory_dir = os.path.join(env_dir, "inventory")
        result["inventory_dir"] = inventory_dir

        if extract_vars:
            inv_target = "../inventory/hosts"
        else:
            inv_target = "../inventory/inventory"

        result["extract_vars"] = extract_vars

        playbook_dir = os.path.join(env_dir, "plays")
        result["playbook_dir"] = playbook_dir
        roles_base_dir = os.path.join(env_dir, "roles")
        result["roles_base_dir"] = playbook_dir

        ask_sudo = ""
        all_plays_name = "all_plays.yml"
        result["default_playbook_name"] = all_plays_name

        ansible_playbook_args = ansible_args
        result["ansible_playbook_cli_args"] = ansible_playbook_args
        result["run_playbooks_script"] = os.path.join(env_dir, "run_all_plays.sh")

        cookiecutter_details = {
            "inventory": inv_target,
            "env_dir": env_dir,
            "playbook_dir": playbook_dir,
            "ansible_playbook_args": ansible_playbook_args,
            "library_path": "library",
            "action_plugins_path": "action_plugins",
            "extra_script_commands": "",
            "ask_sudo": ask_sudo,
            "playbook": all_plays_name,
            "callback_plugins": "callback_plugins",
            "callback_plugin_name": callback
        }

        log.debug("Creating build environment from template...")
        log.debug("Using cookiecutter details: {}".format(cookiecutter_details))

        template_path = os.path.join(os.path.dirname(__file__), "external", "cookiecutter-ansible-environment")

        cookiecutter(template_path, extra_context=cookiecutter_details, no_input=True)

        # write inventory
        if extract_vars:
            self.inventory.extract_vars(inventory_dir)
        self.inventory.write_inventory_file_or_script(inventory_dir, extract_vars=extract_vars)

        # write roles
        all_playbooks = []
        ext_roles = False
        for play, tasks in self.plays.items():

            playbook = tasks.render_playbook(playbook_dir)
            all_playbooks.append(playbook)
            tasks.render_roles(roles_base_dir)
            if tasks.ext_roles:
                ext_roles = True

        jinja_env = Environment(loader=PackageLoader('nsbl', 'templates'))
        template = jinja_env.get_template('play.yml')
        output_text = template.render(playbooks=all_playbooks)
        all_plays_file = os.path.join(env_dir, "plays", all_plays_name)
        result["all_plays_file"] = all_plays_file
        with open(all_plays_file, "w") as text_file:
            text_file.write(output_text)

        # copy extra_plugins
        library_path = os.path.join(os.path.dirname(__file__), "external", "extra_plugins", "library")
        action_plugins_path = os.path.join(os.path.dirname(__file__), "external", "extra_plugins", "action_plugins")
        callback_plugins_path = os.path.join(os.path.dirname(__file__), "external", "extra_plugins", "callback_plugins")
        result["library_path"] = library_path
        result["callback_plugins_path"] = callback_plugins_path
        result["action_plugins_path"] = action_plugins_path

        target_dir = playbook_dir
        shutil.copytree(library_path, os.path.join(target_dir, "library"))
        shutil.copytree(action_plugins_path, os.path.join(target_dir, "action_plugins"))
        os.makedirs(os.path.join(target_dir, "callback_plugins"))
        if callback == "nsbl_internal":
            shutil.copy(os.path.join(callback_plugins_path, "nsbl_internal.py"), os.path.join(target_dir, "callback_plugins"))
        elif callback == "nsbl_internal_raw":
            shutil.copy(os.path.join(callback_plugins_path, "nsbl_internal.py"), os.path.join(target_dir, "callback_plugins", "{}.py".format(callback)))

        if ext_roles:
            # download external roles
            log.debug("Downloading and installing external roles...")
            res = subprocess.check_output([os.path.join(env_dir, "extensions", "setup", "role_update.sh")])
            for line in res.splitlines():
                log.debug("Installing role: {}".format(line.encode('utf8')))

        return result

class NsblOld(object):
    def __init__(self, configs, task_descs=None, role_repos=None, default_env_type=DEFAULT_ENV_TYPE):
        """Wrapper class to create an Ansible environment.

        Args:
          configs (list): the configuration(s) describing the inventory and tasks
          tasks_descs (list): list of dicts of task descriptions to use, if none, default ones will be used
          role_repos (list): list of (populated) role_repos to use, if none, default ones will be used
          default_env_type (str): the default type for an environment if not provided in the config (either ENV_TYPE_HOST or ENV_TYPE_GROUP)
        """

        self.configs = configs

        if role_repos:
            self.role_repos = role_repos
        else:
            self.role_repos = calculate_role_repos([], use_default_roles=True)

        if task_descs:
            self.task_descs = task_descs
        else:
            self.task_descs = calculate_task_descs(None, self.role_repos)

        self.inventory = NsblInventory(self.configs, default_env_type)
        self.inv_obj = Frkl(configs, NSBL_INVENTORY_BOOTSTRAP_CHAIN)
        self.inv_obj.process(self.inventory)

        inv_tasks = self.inventory.tasks

        self.tasks = NsblTasks(self.task_descs, self.role_repos)

    def render_environment(self, env_dir, extract_vars=False, force=False, ansible_verbose="", callback=None):
        """Creates the ansible environment in the folder provided.

        Args:
          env_dir (str): the folder where the environment should be created
          extract_vars (bool): whether to extract a hostvars and groupvars directory for the inventory (True), or render a dynamic inventory script for the environment (default, False)
          force (bool): overwrite environment if already present at the specified location
          ansible_verbose (str): parameters to give to ansible-playbook (like: "-vvv")
          callback (str): name of the callback to use, default: nsbl_internal
        """

        result = {}
        result['env_dir'] = env_dir
        if os.path.exists(env_dir) and force:
            shutil.rmtree(env_dir)

        all_ext_roles = {}
        all_int_roles = {}
        #TODO: check for duplicate and different roles
        for tasks in self.tasks:
            meta_roles = tasks.meta_roles
            for role_name, role_dict in meta_roles.items():
                role_path = get_internal_role_path(role_dict, self.role_repos)
                if role_path:
                    all_int_roles[role_name] = role_path
                else:
                    all_ext_roles[role_name] = role_dict
            for t in tasks.tasks:
                task_name = t[TASKS_META_KEY][TASK_NAME_KEY]
                local_role = get_internal_role_path(task_name, self.role_repos)
                if local_role:
                    all_int_roles[task_name] = local_role
                roles = t.get(TASKS_META_KEY, {}).get(TASK_ROLES_KEY, {})
                for role_name, role_dict in roles.items():
                    role_path = get_internal_role_path(role_dict, self.role_repos)
                    if role_path:
                        all_int_roles[role_name] = role_path
                    else:
                        all_ext_roles[role_name] = role_dict

        inventory_dir = os.path.join(env_dir, "inventory")
        result["inventory_dir"] = inventory_dir

        if extract_vars:
            inv_target = "../inventory/hosts"
        else:
            inv_target = "../inventory/inventory"

        result["extract_vars"] = extract_vars

        playbook_dir = os.path.join(env_dir, "plays")
        result["playbook_dir"] = playbook_dir

        ask_sudo = ""
        all_plays_name = "all_plays.yml"
        result["default_playbook_name"] = all_plays_name

        ansible_playbook_args = ansible_verbose
        result["ansible_playbook_args"] = ansible_playbook_args
        result["run_playbooks_script"] = os.path.join(env_dir, "run_all_plays.sh")
        inventory_dir = os.path.join(env_dir, "inventory")
        result["inventory_dir"] = inventory_dir

        if extract_vars:
            inv_target = "../inventory/hosts"
        else:
            inv_target = "../inventory/inventory"

        result["extract_vars"] = extract_vars

        playbook_dir = os.path.join(env_dir, "plays")
        result["playbook_dir"] = playbook_dir

        ask_sudo = ""
        all_plays_name = "all_plays.yml"
        result["default_playbook_name"] = all_plays_name

        ansible_playbook_args = ansible_verbose
        result["ansible_playbook_args"] = ansible_playbook_args
        result["run_playbooks_script"] = os.path.join(env_dir, "run_all_plays.sh")

        cookiecutter_details = {
            "inventory": inv_target,
            "env_dir": env_dir,
            "playbook_dir": playbook_dir,
            "ansible_playbook_args": ansible_playbook_args,
            "library_path": "library",
            "action_plugins_path": "action_plugins",
            "extra_script_commands": "",
            "ask_sudo": ask_sudo,
            "playbook": all_plays_name,
            "nsbl_roles": all_ext_roles,
            "callback_plugins": "callback_plugins",
            "callback_plugin_name": callback
        }

        log.debug("Creating build environment from template...")
        log.debug("Using cookiecutter details: {}".format(cookiecutter_details))

        template_path = os.path.join(os.path.dirname(__file__), "external", "cookiecutter-ansible-environment")

        cookiecutter(template_path, extra_context=cookiecutter_details, no_input=True)

        if extract_vars:
            self.inventory.extract_vars(inventory_dir)

        self.inventory.write_inventory_file_or_script(inventory_dir, extract_vars=extract_vars)

        # copy extra_plugins
        library_path = os.path.join(os.path.dirname(__file__), "external", "extra_plugins", "library")
        action_plugins_path = os.path.join(os.path.dirname(__file__), "external", "extra_plugins", "action_plugins")
        callback_plugins_path = os.path.join(os.path.dirname(__file__), "external", "extra_plugins", "callback_plugins")
        result["library_path"] = library_path
        result["callback_plugins_path"] = callback_plugins_path
        result["action_plugins_path"] = action_plugins_path

        target_dir = os.path.join(env_dir, "plays")

        shutil.copytree(library_path, os.path.join(target_dir, "library"))
        shutil.copytree(action_plugins_path, os.path.join(target_dir, "action_plugins"))
        os.makedirs(os.path.join(target_dir, "callback_plugins"))
        if callback == "nsbl_internal":
            shutil.copy(os.path.join(callback_plugins_path, "nsbl_internal.py"), os.path.join(target_dir, "callback_plugins"))
        elif callback == "nsbl_internal_raw":
            shutil.copy(os.path.join(callback_plugins_path, "nsbl_internal.py"), os.path.join(target_dir, "callback_plugins", "{}.py".format(callback)))

        # copy internal roles
        for role_name, role in all_int_roles.items():
            target = os.path.join(env_dir, "roles", "internal", role_name)
            shutil.copytree(role, target)

        all_dyn_roles = {}
        for tasks in self.tasks:
            for task in tasks.tasks:
                if task[TASKS_META_KEY][TASK_TYPE_KEY] == DYN_ROLE_TYPE:
                    all_dyn_roles[task[TASKS_META_KEY][TASK_NAME_KEY]] = task[TASKS_META_KEY][TASK_DYN_ROLE_DETAILS]

        # create dynamic roles
        for role_name, role_tasks in all_dyn_roles.items():
            role_local_path = os.path.join(os.path.dirname(__file__), "external", "ansible-role-template")
            # cookiecutter doesn't like input lists, so converting to dict
            tasks = {}

            for task in role_tasks:
                task_name = task[TASKS_META_KEY][DYN_TASK_ID_KEY]
                tasks[task_name] = task
                if VARS_KEY not in task.keys():
                    task[VARS_KEY] = {}
                if VAR_KEYS_KEY not in task[TASKS_META_KEY].keys() or task[TASKS_META_KEY][VAR_KEYS_KEY] == '*':
                    task[TASKS_META_KEY][VAR_KEYS_KEY] = list(task.get(VARS_KEY, {}).keys())
                else:
                    for key in task.get(VARS_KEY, {}).keys():
                        task[TASKS_META_KEY][VAR_KEYS_KEY].append(key)

                # make var_keys items unique
                task[TASKS_META_KEY][VAR_KEYS_KEY] = list(set(task[TASKS_META_KEY][VAR_KEYS_KEY]))
                if WITH_ITEMS_KEY in task[TASKS_META_KEY].keys():
                    with_items_key = task[TASKS_META_KEY][WITH_ITEMS_KEY]

                    # if with_items_key not in task[VARS_KEY]:
                        # raise NsblException("Can't iterate over variable '{}' using with_items because key does not exist in: {}".format(task[TASK_NAME_KEY][VARS_KEY]))

                    # task[TASKS_META_KEY][VARS_KEY] = "item"

            role_dict = {
                "role_name": role_name,
                "tasks": tasks,
                "dependencies": ""
            }

            current_dir = os.getcwd()
            int_roles_base_dir = os.path.join(env_dir, "roles", "dynamic")
            os.chdir(int_roles_base_dir)

            cookiecutter(role_local_path, extra_context=role_dict, no_input=True)
            os.chdir(current_dir)

        if all_ext_roles:
            # download external roles
            log.debug("Downloading and installing external roles...")
            res = subprocess.check_output([os.path.join(env_dir, "extensions", "setup", "role_update.sh")])
            for line in res.splitlines():
                log.debug("Installing role: {}".format(line.encode('utf8')))

        playbooks = []
        for idx, task in enumerate(self.tasks):
            jinja_env = Environment(loader=PackageLoader('nsbl', 'templates'))
            template = jinja_env.get_template('playbook.yml')
            output_text = template.render(groups=task.env_name, tasks=task.tasks, env=task.env)

            playbook_name = "play_{}_{}.yml".format(idx, task.env_name)
            playbooks.append(playbook_name)
            playbook_file = os.path.join(env_dir, "plays", playbook_name)

            with open(playbook_file, "w") as text_file:
                text_file.write(output_text)

        template = jinja_env.get_template('play.yml')
        output_text = template.render(playbooks=playbooks)
        all_plays_file = os.path.join(env_dir, "plays", all_plays_name)

        with open(all_plays_file, "w") as text_file:
            text_file.write(output_text)

        result['lookup_dict'] = self.get_lookup_dict()
        return result

    def get_task(self, env_id, task_id, dyn_role_task_id=None):

        for task in self.tasks:
            if task.env_id != env_id:
                continue

            for int_tasks in task.tasks:

                if int_tasks[TASKS_META_KEY][TASK_ID_KEY] != task_id:
                    continue

                if dyn_role_task_id != None:
                    for t in  int_tasks[TASKS_META_KEY][TASK_DYN_ROLE_DETAILS]:
                        if t[TASKS_META_KEY][DYN_TASK_ID_KEY] == dyn_role_task_id:
                            return t
                else:
                    return int_tasks

        return None

    def get_lookup_dict(self):

        result = {}
        for task in self.tasks:

            id = task.env_id
            #id = task.env_name
            tasks_lookup_dict = task.get_lookup_dict()

            result[id] = tasks_lookup_dict

        return result


class NsblRunner(object):

    def __init__(self, nsbl):

        self.nsbl = nsbl

    def run(self, target, extract_vars, force=True, ansible_verbose="", callback=None):

        if callback == None:
            callback = "nsbl_internal"

        parameters = self.nsbl.render_environment(target, extract_vars=extract_vars, force=force, ansible_verbose=ansible_verbose, callback=callback)
        lookup_dict = parameters['lookup_dict']

        run_env = os.environ.copy()
        run_env['NSBL_ENVIRONMENT'] = "true"
        script = parameters['run_playbooks_script']
        proc = subprocess.Popen(script, stdout=subprocess.PIPE, stderr=sys.stdout.fileno(), stdin=subprocess.PIPE, shell=True, env=run_env)

        if callback == "nsbl_internal":
            callback_adapter = NsblLogCallbackAdapter(lookup_dict)
        else:
            callback_adapter = NsblPrintCallbackAdapter()

        with CursorOff():
            click.echo("")
            for line in iter(proc.stdout.readline, ''):
                # try:
                    callback_adapter.add_log_message(line)
                # except Exception as e:
                    # proc.kill()
                    # print("Current line:")
                    # print("")
                    # print(line)
                    # print("")
                    # raise e

            callback_adapter.finish_up()

            click.echo("")
        return


class NsblPrintCallbackAdapter(object):

    def add_log_message(self, line):

        click.echo(line, nl=False)

    def finish_up(self):

        pass

class NsblLogCallbackAdapter(object):

    def __init__(self, lookup_dict, display_sub_tasks=True):

        self.lookup_dict = lookup_dict
        self.display_sub_tasks = display_sub_tasks
        self.current_env_id = None
        self.current_task_id = None
        self.current_dyn_task_id = None
        self.current_task_is_dyn_role = False
        self.current_task = None

        self.new_line = False
        self.task_has_items = False
        self.task_has_nsbl_items = False
        self.current_ansible_task_name = None
        self.saved_item = None
        self.last_action = None
        self.msgs = []

    def add_log_message(self, line):


        # try:
            # details = json.loads(line.encode(sys.stdout.encoding, errors='replace'))
        # except:
            # print("Error: Could not interprete log line:")
            # print("")
            # print(line)
            # print("")
            # return

        details = json.loads(line)

        category = details["category"]

        task_changed = False

        env_id = details.get(ENV_ID_KEY, None)
        task_id = details.get(TASK_ID_KEY, None)

        if env_id == None or task_id == None:
            env_id = self.current_env_id
            task_id = self.current_task_id

        if env_id != self.current_env_id:
            task_changed = True

        if task_id != self.current_task_id:
            task_changed = True

        dyn_task_id = details.get(DYN_TASK_ID_KEY, None)
        if dyn_task_id != None and self.current_dyn_task_id != dyn_task_id:
            task_changed = True

        if task_changed:
            if self.current_env_id != None:
                self.process_task_changed()

            self.current_env_id = env_id
            self.current_task_id = task_id
            self.current_dyn_task_id = dyn_task_id
            self.task_has_items = False
            self.task_has_nsbl_items = False
            self.saved_item = None
            self.msgs = []
            self.stderrs = []

            if self.current_dyn_task_id == None:
                self.current_task = self.lookup_dict[self.current_env_id][self.current_task_id]
                self.current_task_is_dyn_role = False
            else:
                self.current_task = self.lookup_dict[self.current_env_id][self.current_task_id][self.current_dyn_task_id]
                self.current_task_is_dyn_role = True

            output = " * {}...".format(self.current_task[TASK_DESC_KEY])
            click.echo(output)
            self.new_line = True

            self.failed = False
            self.skipped = True
            self.changed = False

        if not self.current_task:
            log.debug("No current task when processing: {}".format(line))
            return

        task_desc = self.current_task[TASK_DESC_KEY]
        task_name = self.current_task[TASK_NAME_KEY]

        msg = details.get('msg', None)
        stderr = details.get('stderr_lines', [])
        item = details.get('item', None)
        status = details.get('status', None)
        skipped = details.get('skipped', None)
        ignore_errors = details.get('ignore_errors', False)
        action = details.get('action', self.last_action)
        ansible_task_name = details.get('name', None)
        event = {"category": category, "task_name": task_name, "task_desc":task_desc, "status": status, "item": item, "msg": msg, "skipped": skipped, "ignore_errors": ignore_errors, "ansible_task_name": ansible_task_name, "action": action}

        if skipped != None and not skipped:
            self.skipped = False
        if category == "failed" and not ignore_errors:
            self.failed = True

        if msg:
            msg = msg.encode(sys.stdout.encoding, errors='replace').strip()
        if msg:
            self.msgs.append(msg)

        if stderr:
            for s in stderr:
                s = s.encode(sys.stdout.encoding, errors='replace').strip()
                self.stderrs.append(s)

        if status and status == "changed":
            self.changed = True

        sub_task_changed = self.current_ansible_task_name != ansible_task_name

        if sub_task_changed and self.saved_item and not self.task_has_items and not self.task_has_nsbl_items:
            if not self.saved_item["action"] in NSBLIZED_TASKS:
                self.display_result(self.saved_item)
            elif self.saved_item["category"] == "skipped" and not self.new_line:
                self.display_result(self.saved_item)

        if sub_task_changed:
            self.task_has_items = False
            self.saved_item = None
            self.task_has_nsbl_items = False
            self.last_action = None

        current_task_is_nsblized = action in NSBLIZED_TASKS


        if category.startswith("nsbl") and current_task_is_nsblized:
            self.saved_item = None
            if category == "nsbl_item_started":
                if not self.new_line:
                    click.echo("")
                output = "       - {} => ".format(item)
                click.echo(output, nl=False)
                self.new_line = False
            else:
                self.display_nsbl_item(event)
        elif category.startswith("item") and not current_task_is_nsblized:
            self.saved_item = None
            self.task_has_items = True
            self.display_item(event)
        elif category == "task_start":
            if self.current_task_is_dyn_role:
                return
            elif ansible_task_name.startswith("nsbl_finished"):
                return

            if not self.new_line:
                click.echo("")
            if ansible_task_name.startswith("nsbl_started="):
                name = ansible_task_name[13:]
            else:
                name = ansible_task_name
            output = "    - {} => ".format(name)
            click.echo(output, nl=False)
            self.new_line = False
        elif category in ["ok", "failed", "skipped"]:

            if not self.task_has_items and not self.task_has_nsbl_items and sub_task_changed and not current_task_is_nsblized:
                self.display_result(event)
            else:
                self.saved_item = event
        else:
            pass
            # print("NO CATEGORY: {}".format(category))

        self.current_ansible_task_name = ansible_task_name
        self.last_action = action

    def pretty_print_item(self, item):

        if isinstance(item, string_types):
            try:
                item = json.loads(item)
            except Exception as e:
                return item

        if isinstance(item, dict):
            if item.get("name", None):
                return item["name"]
            elif item.get("repo", None):
                return item["repo"]
            elif item.get("vars", {}).get("name", None):
                return item["vars"]["name"]
            elif item.get("vars", {}).get("repo", None):
                return item["vars"]["name"]

        return item

    def display_nsbl_item(self, ev):

        item = self.pretty_print_item(ev["item"])
        if ev["category"] == "nsbl_item_ok":
            skipped = ev["skipped"]
            if skipped:
                msg = "skipped"
            else:
                if ev["status"] == "changed":
                    msg = "changed"
                else:
                    msg = "no change"
            output = "ok ({})".format(msg)
            self.new_line = True
            click.echo(output)
        elif ev["category"] == "nsbl_item_failed":
            msg = ev.get('msg', None)
            if not msg:
                if ev.get("ignore_errors", False):
                    msg = "(but errors ignored)"
                else:
                    msg = "(no error details)"
                    output = "failed: {}".format(msg)

            output = "failed: {}".format(msg)
            click.echo(output)
            self.new_line = True

    def display_item(self, ev):

        item = self.pretty_print_item(ev["item"])
        if not self.new_line:
            click.echo("")

        if ev["category"] == "item_ok":
            skipped = ev["skipped"]
            if skipped:
                msg = "skipped"
            else:
                if ev["status"] == "changed":
                    msg = "changed"
                else:
                    msg = "no change"
            output = "      - {} => ok ({})".format(item, msg)
            click.echo(output)
            self.new_line = True
        elif ev["category"] == "item_failed":
            msg = ev.get('msg', None)
            if not msg:
                if ev.get("ignore_errors", False):
                    msg = "(but errors ignored)"
                else:
                    msg = "(no error details)"
                    output = "failed: {}".format(msg)
            output = "      - {} => failed: {}".format(item, msg)
            click.echo(output)
            self.new_line = True
        elif ev["category"] == "item_skipped":
            output = "      - {} => skipped".format(item)
            click.echo(output)
            self.new_line = True

    def display_result(self, ev):

        if ev["ansible_task_name"].startswith("nsbl_started="):
            return
        if ev["ansible_task_name"].startswith("nsbl_finished="):
            output = "no task information available"
            click.echo(output)
            self.new_line = True
        else:
            if ev["category"] == "ok":
                skipped = ev["skipped"]
                if skipped:
                    msg = "skipped"
                else:
                    if ev["status"] == "changed":
                        msg = "changed"
                    else:
                        msg = "no change"
                output = "ok ({})".format(msg)
                click.echo(output)
                self.new_line = True
            elif ev["category"] == "failed":
                if ev["msg"]:
                    output = "failed: {}".format(ev["msg"])
                else:
                    if ev.get("ignore_errors", False):
                        msg = "(but errors ignored)"
                    else:
                        msg = "(no error details)"
                    output = "failed: {}".format(msg)
                click.echo(output)
                self.new_line = True
            elif ev["category"] == "skipped":
                output = "skipped"
                click.echo(output)
                self.new_line = True

    def process_task_changed(self):

        msg = ["n/a"]
        if not self.new_line:
            click.echo("")
        if self.failed:
            output = []
            if self.msgs:
                if len(self.msgs) < 2:
                    output.append("   => failed: {}".format("".join(self.msgs)))
                else:
                    output.append("   => failed:")
                    output.append("      messages in this task:")
                    for m in self.msgs:
                        output.append("        -> {}".format(m))
            else:
                output.append("   => failed")

            if self.stderrs:
                output.append("      stderr:")
                for e in self.stderrs:
                    output.append("        -> {}".format(e))

            output = "\n".join(output)

        elif self.changed:
            output = "   => ok (changed)"
        else:
            output = "   => ok (no change)"

        click.echo(output)
        click.echo("")
        self.new_line = True

    def finish_up(self):

        self.process_task_changed()


# class NsblInventory(object):

#     def __init__(self, configs, int_task_descs=[], role_repos=[], default_env_type=DEFAULT_ENV_TYPE):
#         """Class to be used to create a dynamic ansible inventory from (elastic) yaml config files.

#         Args:
#           configs (list): list of paths to inventory config (elastic) yaml files
#           int_task_descs (list): descriptions of internal tasks (used to 'expand' task name keywords)
#           default_env_type (str): the default type for an environment if not provided in the config (either ENV_TYPE_HOST or ENV_TYPE_GROUP)
#         """

#         self.configs = configs
#         self.frkl_obj = Frkl(configs, NSBL_INVENTORY_BOOTSTRAP_CHAIN)
#         self.config = self.frkl_obj.process()
#         self.default_env_type = default_env_type
#         self.int_task_deskcs = int_task_descs
#         self.role_repos = role_repos
#         self.groups = {}
#         self.hosts = {}
#         self.tasks = []

#         self.assemble_groups()

#     def extract_vars(self, inventory_dir):

#         for group, group_vars in self.groups.items():
#             vars = group_vars.get(VARS_KEY, {})
#             if not vars:
#                 continue
#             group_dir = os.path.join(inventory_dir, "group_vars", group)
#             var_file = os.path.join(group_dir, "{}.yml".format(group))
#             content = yaml.dump(vars, default_flow_style=False)

#             os.makedirs(group_dir)
#             with open(var_file, "w") as text_file:
#                 text_file.write(content)

#         for host, host_vars in self.hosts.items():
#             vars = host_vars.get(VARS_KEY, {})
#             if not vars:
#                 continue
#             host_dir = os.path.join(inventory_dir, "host_vars", host)
#             var_file = os.path.join(host_dir, "{}.yml".format(host))
#             content = yaml.dump(vars, default_flow_style=False)

#             os.makedirs(host_dir)
#             with open(var_file, "w") as text_file:
#                 text_file.write(content)

#     def get_inventory_config_string(self):

#         jinja_env = Environment(loader=PackageLoader('nsbl', 'templates'))
#         template = jinja_env.get_template('hosts')
#         output_text = template.render(groups=self.groups, hosts=self.hosts)

#         return output_text

#     def write_inventory_file_or_script(self, inventory_dir, extract_vars=False, relative_paths=True):

#         if extract_vars:
#             inventory_string = self.get_inventory_config_string()
#             inventory_name = "hosts"
#             inventory_file = os.path.join(inventory_dir, inventory_name)

#             with open(inventory_file, "w") as text_file:
#                 text_file.write(inventory_string)

#         else:
#             # write dynamic inventory script
#             jinja_env = Environment(loader=PackageLoader('nsbl', 'templates'))
#             if relative_paths:
#                 template = jinja_env.get_template('inventory_relative')
#             else:
#                 template = jinja_env.get_template('inventory_absolute')

#             roles_repos_string = ""
#             if self.roles_repo_folders:
#                 if relative_paths:
#                     roles_repos_string = " --repo ".join(
#                         [os.path.relpath(name, inventory_dir) for name in self.roles_repo_folders])

#                     rel_configs = []

#                     for path in self.configs:
#                         rel_path = os.path.relpath(path, inventory_dir)
#                         rel_configs.append(rel_path)

#                     script_configs = " --config ".join(rel_configs)
#                 else:
#                     roles_repos_string = " --repo ".join([os.path.abspath(name) for name in self.roles_repos])

#                     abs_configs = []
#                     for path in self.configs:
#                         abs_path = os.path.abspath(path)
#                         abs_configs.append(abs_path)
#                     script_configs = " --config".join(abs_configs)

#             output_text = template.render(role_repo_paths=roles_repos_string, nsbl_script_configs=script_configs)

#             inventory_string = self.get_inventory_config_string()
#             inventory_target_name = "inventory"

#             inventory_file = os.path.join(inventory_dir, inventory_target_name)

#             with open(inventory_file, "w") as text_file:
#                 text_file.write(output_text)

#             st = os.stat(inventory_file)
#             os.chmod(inventory_file, 0o775)

#     def add_group(self, group_name, group_vars):
#         """Add a group to the dynamic inventory.

#         Args:
#           group_name (str): the name of the group
#           group_vars (dict): the variables for this group
#         """

#         if group_name in self.groups.keys():
#             raise NsblException("Group '{}' defined twice".format(group_name))

#         self.groups[group_name] = {}
#         self.groups[group_name]["vars"] = group_vars
#         self.groups[group_name]["hosts"] = []
#         self.groups[group_name]["children"] = []

#     def add_host(self, host_name, host_vars):
#         """Add a host to the dynamic inventory.

#         Args:
#           host_name (str): the name of the host
#           host_vars (dict): the variables for this host
#         """

#         if host_name not in self.hosts.keys():
#             self.hosts[host_name] = {VARS_KEY: {}}

#         if not host_vars:
#             return

#         intersection = set(self.hosts[host_name].get(VARS_KEY, {}).keys()).intersection(host_vars.keys())

#         if intersection:
#             raise NsblException(
#                 "Adding host more than once with intersecting keys, this is not possible because it's not clear which vars should take precedence. Intersection: {}".format(
#                     intersection))

#         self.hosts[host_name][VARS_KEY].update(host_vars)

#     def add_group_to_group(self, child, group):
#         """Adds a group as a subgroup of another group.

#         Args:
#           child (str): the name of the sub-group
#           group (str): the name of the parent group
#         """

#         if group not in self.groups[group]["children"]:
#             self.groups[group]["children"].append(child)

#     def add_host_to_group(self, host, group):
#         """Adds a host to a group.

#         Args:
#           host (str): the name of the host
#           group (str): the name of the parent group
#         """

#         if host not in self.groups[group]["hosts"]:
#             self.groups[group]["hosts"].append(host)

#         self.add_host(host, None)

#     def assemble_groups(self):
#         """Kicks of the processing of the config files."""

#         env_id = 0
#         for env in self.config:
#             if ENV_META_KEY not in env.keys():
#                 raise NsblException(
#                     "Environment does not have metadata (missing '{}') key: {})".format(ENV_META_KEY, env))
#             env_type = env[ENV_META_KEY].get(ENV_TYPE_KEY, False)
#             if not env_type:
#                 if ENV_HOSTS_KEY in env[ENV_META_KEY].keys():
#                     env_type = ENV_TYPE_GROUP
#                 elif ENV_GROUPS_KEY in env[ENV_META_KEY].keys():
#                     env_type = ENV_TYPE_HOST
#                 else:
#                     env_type = self.default_env_type

#             env_name = env[ENV_META_KEY].get(ENV_NAME_KEY, False)
#             if not env_name:
#                 raise NsblException(
#                     "Environment metadata needs to contain a name (either host- or group-name): {}".format(
#                         env[ENV_META_KEY]))

#             if env_type == ENV_TYPE_HOST:

#                 self.add_host(env_name, env.get(VARS_KEY, {}))

#                 if ENV_HOSTS_KEY in env.get(ENV_META_KEY, {}).keys():
#                     raise NsblException(
#                         "An environment of type {} can't contain the {} key".format(ENV_TYPE_HOST, ENV_HOSTS_KEY))

#                 for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
#                     self.add_host_to_group(env_name, group)

#             elif env_type == ENV_TYPE_GROUP:

#                 self.add_group(env_name, env.get(VARS_KEY, {}))

#                 for host in env[ENV_META_KEY].get(ENV_HOSTS_KEY, []):
#                     self.add_host_to_group(host, env_name)

#                 for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
#                     self.add_group_to_group(group, env_name)

#             else:
#                 raise NsblException("Environment type needs to be either 'host' or 'group': {}".format(env_type))

#             if TASKS_KEY in env.keys():
#                 self.tasks.append(NsblTasks(env, env_id, self.int_task_deskcs, self.role_repos, env_name))
#                 env_id += 1

#         if "localhost" in self.hosts.keys() and "ansible_connection" not in self.hosts["localhost"].get(VARS_KEY,
#                                                                                                         {}).keys():
#             self.hosts["localhost"][VARS_KEY]["ansible_connection"] = "local"


#     def list(self):
#         """Lists all groups in the format that is required for ansible dynamic inventories.

#         More info: https://docs.ansible.com/ansible/intro_dynamic_inventory.html, http://docs.ansible.com/ansible/dev_guide/developing_inventory.html

#         Returns:
#         dict: a dict containing all information about all hosts/groups
#         """

#         result = copy.copy(self.groups)
#         result["_meta"] = {"hostvars": self.hosts}

#         return json.dumps(result, sort_keys=4, indent=4)

#     def host(self, host):
#         """Returns the inventory information for the specified host, in the format required for ansible dynamic inventories.

#         Args:
#           host (str): the name of the host
#         Returns:
#         dict: all inventory information for this host
#         """

#         host_vars = self.hosts.get(host, {}).get(VARS_KEY, {})
#         return json.dumps(host_vars, sort_keys=4, indent=4)

#     def get_vars(self, env_name):
#         """Returns all variables for the environment with the specified name.

#         First tries whether the name matches a group, then tries hosts.

#         Args:
#           env_name (str): the name of the group or host
#         Returns:
#           dict: the variables for the environment
#         """

#         if env_name in self.groups.keys():
#             return self.groups[env_name].get(VARS_KEY, {})
#         elif env_name in self.hosts.keys():
#             return self.hosts[env_name].get(VARS_KEY, {})
#         else:
#             raise NsblException("Neither group or host with name '{}' exists".format(env_name))

# class NsblTaskProcessor(ConfigProcessor):
#     """Processor to take a list of (unfrklized) tasks, and frklizes (expands) the data.

#     In particular, this extracts roles and tags them with their types.
#     """

#     def validate_init(self):

#         self.task_name_key = [TASKS_META_KEY, TASK_META_NAME_KEY]
#         self.meta_roles = self.init_params['meta_roles']
#         self.task_descs = self.init_params.get('task_descs', [])
#         self.role_repos = self.init_params.get('role_repos', [])
#         return True

#     def process_current_config(self):

#         new_config = self.current_input_config
#         meta_task_name = new_config[TASKS_META_KEY][TASK_META_NAME_KEY]

#         for task_desc in self.task_descs:
#             task_desc_name = task_desc.get(TASKS_META_KEY, {}).get(TASK_META_NAME_KEY, None)

#             if not task_desc_name == meta_task_name:
#                 continue

#             new_config = dict_merge(task_desc, new_config, copy_dct=True)

#         task_name = new_config.get(TASKS_META_KEY, {}).get(TASK_NAME_KEY, None)
#         if not task_name:
#             task_name = meta_task_name

#         task_type = new_config.get(TASKS_META_KEY, {}).get(TASK_TYPE_KEY, None)
#         roles = new_config.get(TASKS_META_KEY, {}).get(TASK_ROLES_KEY, {})
#         task_roles = expand_external_role(roles, self.role_repos)

#         int_role_path = get_internal_role_path(task_name, self.role_repos)
#         if task_type == EXT_TASK_TYPE:
#             if task_name not in roles.keys and task_name not in self.meta_roles.keys() and not int_role_path:
#                     raise NsblException("Task name '{}' not found among role names, but task type is '{}'. This is invalid.".format(task_name, task_type))

#         else:
#             if task_name in task_roles.keys() or task_name in self.meta_roles.keys() or int_role_path:
#                 task_type = EXT_TASK_TYPE
#             else:
#                 task_type = DYN_TASK_TYPE

#             new_config[TASKS_META_KEY][TASK_TYPE_KEY] = task_type

#         new_config[TASKS_META_KEY][TASK_NAME_KEY] = task_name
#         new_config[TASKS_META_KEY][TASK_ROLES_KEY] = task_roles


#         with_items_key = new_config[TASKS_META_KEY].get(WITH_ITEMS_KEY, None)
#         if with_items_key:
#             new_config[TASKS_META_KEY][TASK_WITH_ITEMS_KEY] = with_items_key

#         #TODO: use 'with_items' instead of this
#         split_key = new_config[TASKS_META_KEY].get(SPLIT_KEY_KEY, None)
#         if split_key:
#             splitting = True
#         else:
#             splitting = False

#         if splitting:
#             if split_key and isinstance(split_key, string_types):
#                 split_key = split_key.split("/")

#             split_value = new_config
#             for split_token in split_key:
#                 if not isinstance(split_value, dict):
#                     raise NsblException("Can't split config value using split key '{}': {}".format(split_key, new_config))
#                 split_value = split_value.get(split_token, None)
#                 if not split_value:
#                     break

#             if split_value and isinstance(split_value, (list, tuple)):

#                 for item in split_value:
#                     item_new_config = copy.deepcopy(new_config)
#                     temp = item_new_config
#                     for token in split_key[:-1]:
#                         temp = temp[token]

#                     temp[split_key[-1]] = item

#                     yield item_new_config

#             else:
#                 yield new_config
#         else:
#             yield new_config


# class NsblDynamicRoleProcessor(ConfigProcessor):
#     """Processor to extract and pre-process single tasks to merge them into one or several roles later on."""

#     def validate_init(self):
#         self.id_role = 0
#         self.current_tasks = []
#         self.env_name = self.init_params["env_name"]
#         return True

#     def handles_last_call(self):

#         return True

#     def create_role_dict(self, tasks):

#         task_vars = {}
#         role_name = ["dyn_role"]
#         roles = {}

#         for idx, t in enumerate(tasks):
#             task_id = "_dyn_task_{}".format(idx)
#             role_name.append(t[TASKS_META_KEY][TASK_META_NAME_KEY])
#             t[TASKS_META_KEY][DYN_TASK_ID_KEY] = task_id
#             roles.update(t[TASKS_META_KEY].get(TASK_ROLES_KEY, {}))
#             for key, value in t.get(VARS_KEY, {}).items():
#                 task_vars["{}_{}".format(task_id, key)] = value

#         dyn_role = {
#             TASKS_META_KEY: {
#                 TASK_META_NAME_KEY: " ".join(role_name),
#                 TASK_NAME_KEY: "env_{}_dyn_role_{}".format(self.env_name, self.id_role),
#                 TASK_DYN_ROLE_DETAILS: copy.deepcopy(self.current_tasks),
#                 TASK_TYPE_KEY: DYN_ROLE_TYPE,
#                 TASK_ROLES_KEY: roles
#             },
#             VARS_KEY: task_vars}

#         return dyn_role

#     def process_current_config(self):


#         if not self.last_call:
#             new_config = self.current_input_config

#             if new_config[TASKS_META_KEY][TASK_TYPE_KEY] == DYN_TASK_TYPE:
#                 self.current_tasks.append(new_config)
#                 yield None
#             else:
#                 if len(self.current_tasks) > 0:
#                     dyn_role = self.create_role_dict(self.current_tasks)
#                     self.id_role = self.id_role + 1
#                     self.current_tasks = []
#                     yield dyn_role

#                 yield new_config
#         else:
#             if len(self.current_tasks) > 0:
#                 yield self.create_role_dict(self.current_tasks)
#             else:
#                 yield None


# class NsblTasks(object):

#     def __init__(self, env, env_id, int_task_descs=[], role_repos=[], env_name="localhost"):

#         self.env = env
#         self.env_id = env_id
#         self.env_name = env_name
#         self.role_repos = role_repos
#         self.meta_roles = expand_external_role(env.get(TASKS_META_KEY, {}).get(TASK_ROLES_KEY, {}), self.role_repos)
#         self.int_task_descs = int_task_descs

#         # creating the expanded list of tasks
#         nsbl_task_processor = NsblTaskProcessor({'env': self.env, 'task_descs': self.int_task_descs, 'meta_roles': self.meta_roles, 'role_repos': self.role_repos})

#         # create the dynamic roles
#         nsbl_dynrole_processor = NsblDynamicRoleProcessor({"env_name": self.env_name})

#         # id_processor = IdProcessor(NSBL_TASKS_ID_INIT)

#         # otherwise each tasks inherits from the ones before
#         temp_tasks = [[name] for name in self.env[TASKS_KEY]]

#         frkl_format = generate_nsbl_tasks_format(int_task_descs)
#         frkl_obj = Frkl(temp_tasks, [
#             FrklProcessor(frkl_format),
#             nsbl_task_processor, nsbl_dynrole_processor])


#         self.tasks = frkl_obj.process()
#         for idx, task in enumerate(self.tasks):
#             task_id = idx
#             task[TASKS_META_KEY][TASK_ID_KEY] = task_id
#             task[TASKS_META_KEY][ENV_ID_KEY] = self.env_id

#     def get_lookup_dict(self):

#         result = {}
#         for task in self.tasks:
#             id = task[TASKS_META_KEY][TASK_ID_KEY]
#             task_type = task[TASKS_META_KEY][TASK_TYPE_KEY]
#             if task_type != DYN_ROLE_TYPE:
#                 temp = {}
#                 temp[TASK_NAME_KEY] = task[TASKS_META_KEY][TASK_NAME_KEY]
#                 temp[TASK_DESC_KEY] = task[TASKS_META_KEY].get(TASK_DESC_KEY, "applying role: '{}'".format(task[TASKS_META_KEY][TASK_NAME_KEY]))
#                 temp[VARS_KEY] = task.get(VARS_KEY, {})
#                 result[id] = temp
#             else:
#                 result[id] = {}
#                 for t in task[TASKS_META_KEY][TASK_DYN_ROLE_DETAILS]:
#                     temp = {}
#                     temp[TASK_NAME_KEY] = t[TASKS_META_KEY][TASK_NAME_KEY]
#                     temp[TASK_DESC_KEY] = t[TASKS_META_KEY].get(TASK_DESC_KEY, t[TASKS_META_KEY][TASK_NAME_KEY])
#                     temp[VARS_KEY] = t.get(VARS_KEY, {})
#                     result[id][t[TASKS_META_KEY][DYN_TASK_ID_KEY]] = temp

#         return result

#     def __repr__(self):

#         return "NsblTasks(env_id='{}', env_name='{}')".format(self.env_id, self.env_name)

#     def get_dict(self):

#         temp = {}
#         temp["env_name"] = self.env_name
#         temp["tasks"] = self.tasks
#         # temp["env"] = self.env

#         return temp
