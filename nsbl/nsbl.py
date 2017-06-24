# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import copy
import json
import logging
import os
import pprint
import shutil
import subprocess
import sys
from builtins import *

import click
from cookiecutter.main import cookiecutter
from future.builtins.disabled import *
from jinja2 import Environment, PackageLoader
from six import string_types

import yaml
from frkl.frkl import (CHILD_MARKER_NAME, DEFAULT_LEAF_NAME,
                       DEFAULT_LEAFKEY_NAME, KEY_MOVE_MAP_NAME,
                       OTHER_KEYS_NAME, ConfigProcessor,
                       EnsurePythonObjectProcessor, EnsureUrlProcessor, Frkl,
                       FrklCallback, FrklProcessor, IdProcessor,
                       UrlAbbrevProcessor, dict_merge)

from .defaults import *
from .exceptions import NsblException
from .inventory import NsblInventory, WrapTasksIntoLocalhostEnvProcessor
from .output import CursorOff, NsblLogCallbackAdapter, NsblPrintCallbackAdapter
from .tasks import NsblDynamicRoleProcessor, NsblTaskProcessor, NsblTasks

try:
    set
except NameError:
    from sets import Set as set


log = logging.getLogger("nsbl")


# ------------------------------
# util functions
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

    def create(config, role_repos=[], task_descs=[], include_parent_meta=False, include_parent_vars=False, default_env_type=DEFAULT_ENV_TYPE, pre_chain=[UrlAbbrevProcessor(), EnsureUrlProcessor(), EnsurePythonObjectProcessor()], wrap_into_localhost_env=False):

        init_params = {"task_descs": task_descs, "role_repos": role_repos, "include_parent_meta": include_parent_meta, "include_parent_vars": include_parent_vars, "default_env_type": default_env_type}
        nsbl = Nsbl(init_params)

        if not wrap_into_localhost_env:
            chain = pre_chain + [FrklProcessor(NSBL_INVENTORY_BOOTSTRAP_FORMAT)]
        else:
            wrap_processor = WrapTasksIntoLocalhostEnvProcessor({})
            chain = pre_chain + [wrap_processor, FrklProcessor(NSBL_INVENTORY_BOOTSTRAP_FORMAT)]
        inv_frkl = Frkl(config, chain)
        temp = inv_frkl.process(nsbl)

        return nsbl
    create = staticmethod(create)

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

        self.include_parent_meta = self.init_params.get("include_parent_meta", False)
        self.include_parent_vars = self.init_params.get("include_parent_vars", False)

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
            #chain = [FrklProcessor(task_format)]
            # not adding vars here, since we have the inventory to do that...
            # configs = task_config
            # if self.include_parent_meta:
                # configs = {TASKS_KEY: task_config}
                # configs[TASKS_META_KEY] = meta
            # if self.include_parent_vars:
                # configs = {TASKS_KEY: task_config}
                # configs[VARS_KEY] = tasks.get(VARS_KEY, {})

            tasks_frkl = Frkl(task_config, chain)

            result = tasks_frkl.process(tasks_collector)
            #result = tasks_frkl.process()

    def result(self):

        return {"inventory": self.inventory, "plays": self.plays}

    def render(self, env_dir, extract_vars=True, force=False, ansible_args="", callback='nsbl_internal', add_timestamp_to_env=False, add_symlink_to_env=False):
        """Creates the ansible environment in the folder provided.

        Args:
          env_dir (str): the folder where the environment should be created
          extract_vars (bool): whether to extract a hostvars and groupvars directory for the inventory (True), or render a dynamic inventory script for the environment (default, True) -- Not supported at the moment
          force (bool): overwrite environment if already present at the specified location
          ansible_verbose (str): parameters to give to ansible-playbook (like: "-vvv")
          callback (str): name of the callback to use, default: nsbl_internal
          add_timestamp_to_env (bool): whether to add a timestamp to the env_dir -- useful for when this is called from other programs (e.g. freckles)
          add_symlink_to_env (bool): whether to add a symlink to the current env from a fixed location (useful to archive all runs/logs)
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

    def get_lookup_dict(self):

        result = {}
        for play, tasks in self.plays.items():

            id = tasks.env_id
            tasks_lookup_dict = tasks.get_lookup_dict()
            temp = {TASKS_KEY: tasks_lookup_dict, ENV_NAME_KEY: tasks.env_name, ENV_ID_KEY: tasks.env_id, "play_name": play}

            result[id] = temp

        return result


class NsblRunner(object):

    def __init__(self, nsbl):

        self.nsbl = nsbl

    def run(self, target, force=True, ansible_verbose="", callback=None):

        if callback == None:
            callback = "nsbl_internal"

        parameters = self.nsbl.render(target, True, force, ansible_args="", callback=callback)


        run_env = os.environ.copy()
        if callback.startswith("nsbl_internal"):
            run_env['NSBL_ENVIRONMENT'] = "true"

        script = parameters['run_playbooks_script']
        proc = subprocess.Popen(script, stdout=subprocess.PIPE, stderr=sys.stdout.fileno(), stdin=subprocess.PIPE, shell=True, env=run_env)

        if callback == "nsbl_internal":
            lookup_dict = self.nsbl.get_lookup_dict()
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

        return
