# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import logging
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime

import click
from builtins import *
from cookiecutter.main import cookiecutter
from frkl.frkl import (EnsurePythonObjectProcessor, EnsureUrlProcessor, Frkl,
                       FrklCallback, FrklProcessor, UrlAbbrevProcessor, dict_merge)
from jinja2 import Environment, PackageLoader

from .defaults import *
from .exceptions import NsblException
from .inventory import NsblInventory, WrapTasksIntoLocalhostEnvProcessor
from .output import CursorOff, NsblLogCallbackAdapter, NsblPrintCallbackAdapter
from .tasks import NsblCapitalizedBecomeProcessor, NsblDynamicRoleProcessor, NsblTaskProcessor, NsblTasks, add_roles

try:
    set
except NameError:
    from sets import Set as set

log = logging.getLogger("nsbl")


# ------------------------------
# util functions
def can_passwordless_sudo():
    """Checks if the user can use passwordless sudo on this host."""

    if os.geteuid() == 0:
        return True

    FNULL = open(os.devnull, 'w')
    p = subprocess.Popen('sudo -n ls', shell=True, stdout=FNULL, stderr=subprocess.STDOUT, close_fds=True)
    r = p.wait()
    return r == 0



def get_git_auto_dest_name(repo, parent_dir="~"):
    """Extracts the package/repo name out of a git repo and returns the suggested path where the local copy should live

    Args:
      repo (str): the repo url
      parent_dir (str): the parent path to where the local repo will live

    Returns:
      str: the full path to the local repo
    """

    temp = "{}{}{}".format(parent_dir, os.path.sep, repo.split("/")[-1])

    if temp.endswith(".git"):
        temp = temp[0:-4]

    return temp


def ensure_git_repo_format(repo, dest=None, dest_is_parent=False):
    """Makes sure that the repo is in the format nsbl needs for git repos.

    This format is a dictionary with "repo" and "dest" keys. If only a url is provided,
    the repo name will be calculated using 'get_git_auto_dest_name'.

    Args:
      repo (str, dict): the repository
      dest (str): the (optional) local destination of the repo
      dest_is_parent (bool): whether the provided destination is the parent folder (True), or the full path (False)
    Returns:
      dict: full information for this repo
    """

    if isinstance(repo, string_types):
        if dest:
            if dest_is_parent:
                dest_full = get_git_auto_dest_name(repo, dest)
                return {"repo": repo, "dest": dest_full}
            else:
                return {"repo": repo, "dest": dest}
        else:
            return {"repo": repo, "dest": get_git_auto_dest_name(repo)}
    elif isinstance(repo, dict):
        if "repo" not in repo.keys():
            raise NsblException("Repo dictionary needs at least a 'repo' key: {}".format(repo))
        if "dest" not in repo.keys():
            if dest:
                if dest_is_parent:
                    dest_full = get_git_auto_dest_name(repo["repo"], dest)
                    repo["dest"] = dest_full
                else:
                    repo["dest"] = dest
            else:
                repo["dest"] = get_git_auto_dest_name(repo["repo"])
        return repo
    else:
        raise NsblException("Repo value needs to be either string or dict format: {}".format(repo))


def get_local_role_desc(role_name, role_repos=[]):
    """Returns the local path to the role with the provided name.

    If the role_name is a path string, and it exists, that is returned as 'url' key.
    If not, and optional role_repos are provided those repos are searched for a folder with the
    same name. If that exists, that will be the return value.

    Args:
      role_name (str): the role name
      role_repos (list): a list of local role repositories

    Returns:
      dict: a dict with only the 'url' key and calculated value
    """

    url = False
    if os.path.exists(role_name):
        url = role_name
    else:
        for repo in role_repos:
            path = os.path.join(os.path.expanduser(repo), role_name)
            if os.path.exists(path):
                url = role_name

    if not url:
        raise NsblException(
            "Can't find local role '{}' (neither as absolute path nor in any of the local role repos)".format(
                role_name))

    return {"url": url}


def merge_roles(role_obj, role_repos=[]):
    """Merge the provided role object into a single dictionary containing all roles that can be found through it.

    If the role object is a dictionary, it will be used directly, if it is a string, 'get_local_role_desc' will be
    used to assemble the result dict. In case of list, all child items will be added to the result recursively according
    to their type.
    """

    role_dict = {}

    if isinstance(role_obj, dict):
        if "url" in role_obj.keys() or "version" in role_obj.keys():
            raise NsblException(
                "Although dictionaries and lists can be mixed for the {} key, dictionaries need to use role-names as keys, the keyworkds 'url' and 'version' are not allowed. Mostly likely this is a misconfiguration.")
        role_dict.update(role_obj)
    elif isinstance(role_obj, string_types):
        temp = get_local_role_desc(role_obj, role_repos)
        role_dict[role_obj] = temp
    elif isinstance(role_obj, (list, tuple)):
        for role_obj_child in role_obj:
            temp = merge_roles(role_obj_child, role_repos)
            role_dict.update(temp)
    else:
        raise NsblException(
            "Role description needs to be either a list of strings or a dict. Value '{}' is not valid.".format(
                role_obj))

    return role_dict


# def expand_external_role(role_dict, role_repos=[]):
#     """Ensures the provided input is a dict, and if not converts it in an approriate way.

#     Args:
#       role_dict (str, dict): the input role description
#       role_repos (list): the available local role repos
#     Returns:
#       dict: the fully expanded role description(s)
#     """

#     temp_role_dict = merge_roles(role_dict, role_repos)

#     result = {}
#     for role_name, role_details in temp_role_dict.items():
#         temp_role = {}
#         if isinstance(role_details, string_types):
#             temp_role["url"] = role_details
#         elif isinstance(role_details, dict):
#             temp_role["url"] = role_details["url"]
#             if "version" in role_details.keys():
#                 temp_role["version"] = role_details["version"]
#         result[role_name] = temp_role

#     return result


# def get_internal_role_path(role_dict, role_repos=[]):
#     """Parses the input and returns the local path to the specified role, or False if not found.

#     Args:
#       role_dict (str, dict): the role url or description dict
#       role_repos (list): the available local role repos
#     Returns:
#       str, bool: the path to the local role, or False if not found
#     """

#     if isinstance(role_dict, string_types):
#         url = role_dict
#     elif isinstance(role_dict, dict):
#         url = role_dict["url"]
#     else:
#         raise NsblException("Type '{}' not supported for role description: {}".format(type(role_dict), role_dict))

#     if os.path.exists(url):
#         return url

#     for repo in role_repos:
#         path = os.path.join(os.path.expanduser(repo), url)
#         if os.path.exists(path):
#             return path

#     return False


class Nsbl(FrklCallback):
    def create(config, role_repos=[], task_descs=[], include_parent_meta=False, include_parent_vars=False,
               default_env_type=DEFAULT_ENV_TYPE,
               pre_chain=[UrlAbbrevProcessor(), EnsureUrlProcessor(), EnsurePythonObjectProcessor()],
               wrap_into_localhost_env=False, additional_roles=[]):
        """"Utility method to create a Nsbl object out of the configuration and some metadata about how to process that configuration.

        Args:
          config (list): a list of configuration items
          role_repos (list): a list of all locally available role repos
          task_descs (list): a list of additional task descriptions, those can be used to augment the ones that come with role repositories
          include_parent_meta (bool): whether to include parent meta dict into tasks (not used at the moment)
          include_parent_var (bool): whether to include parent var dict into tasks (not used at the moment)
          default_env_type (str): the type a environment is if it is not explicitely specified, either ENV_TYPE_HOST or ENV_TYPE_GROUP
          pre_chain (list): the chain of ConfigProcessors to plug in front of the one that is used internally, needs to return a python list
          wrap_into_localhost_env (bool): whether to wrap the input configuration into a localhost environment for convenience
          additional_roles (list): a list of additional roles that should always be added to the ansible environment
        Returns:
          Nsbl: the Nsbl object, already 'processed'
        """

        init_params = {"task_descs": task_descs, "role_repos": role_repos, "include_parent_meta": include_parent_meta,
                       "include_parent_vars": include_parent_vars, "default_env_type": default_env_type,
                       "additional_roles": additional_roles}
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
        """Class to receive config items and create an Ansible environment out of them (including inventory and playbooks).

        The init_params to this processor understands these keys:

        'default_env_type' (str): either ENV_TYPE_HOST or ENV_TYPE_GROUP (default), indicates what type environments are that don't have this specified explicitely
        'tasks-descs' (list): a list of additional task descriptions, those can be used to augment the ones that come with role repositories
        'role_repos' (list): a list of all locally available role repos

        More documentation: XXX

        Args:
          init_params (dict): dict to initialize this ConfigProcessor
        """

        super(Nsbl, self).__init__(init_params)
        self.inventory = NsblInventory(init_params)
        self.plays = {}
        self.use_become = False

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

        self.additional_roles = self.init_params.get("additional_roles", [])

        return True

    def callback(self, env):

        self.inventory.callback(env)

    def finished(self):

        self.inventory.finished()
        # this creates the task-description dictionary which is used to enable easier to use commands, and overlays of parameters
        task_format = generate_nsbl_tasks_format(self.task_descs)
        # we have several task lists, each with its own environment associated
        for tasks in self.inventory.tasks:

            meta = tasks[TASKS_META_KEY]
            env_name = meta[ENV_NAME_KEY]
            env_id = meta[ENV_ID_KEY]

            task_config = tasks[TASKS_KEY]
            init_params = {"role_repos": self.role_repos, "task_descs": self.task_descs, "env_name": env_name,
                           "env_id": env_id, TASKS_META_KEY: meta}
            tasks_collector = NsblTasks(init_params)
            add_roles(tasks_collector.all_ansible_roles, self.additional_roles, self.role_repos)

            self.plays["{}_{}".format(env_name, env_id)] = tasks_collector
            # we already have python objects as config items here, so no other ConfigProcessors necessary
            chain = [FrklProcessor(task_format), NsblTaskProcessor(init_params), NsblCapitalizedBecomeProcessor(),
                     NsblDynamicRoleProcessor(init_params)]

            # chain = [FrklProcessor(task_format)]
            # not adding vars here, since we have the inventory to do that...
            # configs = task_config
            # if self.include_parent_meta:
            # configs = {TASKS_KEY: task_config}
            # configs[TASKS_META_KEY] = meta
            # if self.include_parent_vars:
            # configs = {TASKS_KEY: task_config}
            # configs[VARS_KEY] = tasks.get(VARS_KEY, {})

            # wrapping the tasks in a list so the 'base-vars' don't get inherited
            tasks_frkl = Frkl([task_config], chain)

            result = tasks_frkl.process(tasks_collector)
            if tasks_collector.use_become:
                self.use_become = True

    def result(self):
        """Returns a dict with 'inventory' and all 'plays' for this ansible environment."""

        return {"inventory": self.inventory, "plays": self.plays}

    def render(self, env_dir, extra_plugins=None, extract_vars=True, force=False, ask_become_pass="yes",
               ansible_args="", callback='default', force_update_roles=False, add_timestamp_to_env=False,
               add_symlink_to_env=False):
        """Creates the ansible environment in the folder provided.

        Args:
          env_dir (str): the folder where the environment should be created
          extra_plugins (str): a path to a repository of extra ansible plugins, if necessary
          extract_vars (bool): whether to extract a hostvars and groupvars directory for the inventory (True), or render a dynamic inventory script for the environment (default, True) -- Not supported at the moment
          force (bool): overwrite environment if already present at the specified location, use with caution because this might delete an important folder if you get the 'target' dir wrong
          ask_become_pass (str): whether to include the '--ask-become-pass' arg to the ansible-playbook call, options: 'auto', 'true', 'false'
          ansible_verbose (str): parameters to give to ansible-playbook (like: "-vvv")
          callback (str): name of the callback to use, default: nsbl_internal
          force_update_roles (bool): whether to overwrite external roles that were already downloaded
          add_timestamp_to_env (bool): whether to add a timestamp to the env_dir -- useful for when this is called from other programs (e.g. freckles)
          add_symlink_to_env (bool): whether to add a symlink to the current env from a fixed location (useful to archive all runs/logs)
        """

        if isinstance(ask_become_pass, bool):
            ask_become_pass = str(ask_become_pass)

        if not isinstance(ask_become_pass, string_types) or ask_become_pass.lower() not in ["true", "false", "auto"]:
            raise NsblException("Can't parse 'ask_become_pass' var: '{}'".format(ask_become_pass))

        if ask_become_pass == "auto":
            ask_become_pass = self.use_become
        else:
            ask_become_pass = ask_become_pass.lower() in (['true', 'yes'])

        env_dir = os.path.expanduser(env_dir)
        if add_timestamp_to_env:
            start_date = datetime.now()
            date_string = start_date.strftime('%y%m%d_%H_%M_%S')
            dirname, basename = os.path.split(env_dir)
            env_dir = os.path.join(dirname, "{}_{}".format(basename, date_string))

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

        # ask_sudo = "--ask-become-pass"

        if ask_become_pass:
            if can_passwordless_sudo():
                ask_sudo = ""
            else:
                ask_sudo = "--ask-become-pass"
        else:
            ask_sudo = ""

        all_plays_name = "all_plays.yml"
        result["default_playbook_name"] = all_plays_name

        ansible_playbook_args = ansible_args
        result["ansible_playbook_cli_args"] = ansible_playbook_args
        result["run_playbooks_script"] = os.path.join(env_dir, "run_all_plays.sh")

        try:
            import ara
            ara_base = os.path.dirname(ara.__file__)
        except:
            ara_base = None
            pass

        if ara_base:
            callback_plugins_list = "callback_plugins:{}/plugins/callbacks".format(ara_base)
            action_plugins_list = "action_plugins:{}/plugins/actions".format(ara_base)
            library_plugins_list = "library:{}/plugins/modules".format(ara_base)
        else:
            callback_plugins_list = "callback_plugins"
            action_plugins_list = "action_plugins"
            library_plugins_list = "library"

        cookiecutter_details = {
            "inventory": inv_target,
            "env_dir": env_dir,
            "playbook_dir": playbook_dir,
            "ansible_playbook_args": ansible_playbook_args,
            "library_path": library_plugins_list,
            "action_plugins_path": action_plugins_list,
            "extra_script_commands": "",
            "ask_sudo": ask_sudo,
            "playbook": all_plays_name,
            "callback_plugins": callback_plugins_list,
            "callback_plugin_name": callback,
            "callback_whitelist": "default_to_file"
        }

        log.debug("Creating build environment from template...")
        log.debug("Using cookiecutter details: {}".format(cookiecutter_details))

        template_path = os.path.join(os.path.dirname(__file__), "external", "cookiecutter-ansible-environment")

        cookiecutter(template_path, extra_context=cookiecutter_details, no_input=True)

        if add_symlink_to_env:
            link_path = os.path.expanduser(add_symlink_to_env)
            if os.path.exists(link_path) and force:
                os.unlink(link_path)
            link_parent = os.path.abspath(os.path.join(link_path, os.pardir))
            try:
                os.makedirs(link_parent)
            except:
                pass
            os.symlink(env_dir, link_path)

        # write inventory
        if extract_vars:
            self.inventory.extract_vars(inventory_dir)
        self.inventory.write_inventory_file_or_script(inventory_dir, extract_vars=extract_vars)

        # write roles
        all_playbooks = []
        ext_roles = False
        roles_to_copy = {}
        task_details = []
        for play, tasks in self.plays.items():

            task_details.append(str(tasks))
            playbook = tasks.render_playbook(playbook_dir)
            all_playbooks.append(playbook)
            tasks.render_roles(roles_base_dir)
            if tasks.roles_to_copy:
                dict_merge(roles_to_copy, tasks.roles_to_copy, copy_dct=False)
            if tasks.ext_roles:
                ext_roles = True

        result["task_details"] = task_details

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
        if extra_plugins:
            dirs = [o for o in os.listdir(extra_plugins) if os.path.isdir(os.path.join(extra_plugins, o))]
            for d in dirs:
                shutil.copytree(os.path.join(extra_plugins, d), os.path.join(target_dir, d))

        if ext_roles:
            # download external roles
            click.echo("\nDownloading external roles...")
            role_requirement_file = os.path.join(env_dir, "roles", "roles_requirements.yml")

            if not os.path.exists(ANSIBLE_ROLE_CACHE_DIR):
                os.makedirs(ANSIBLE_ROLE_CACHE_DIR)

            command = ["ansible-galaxy", "install", "-r", role_requirement_file, "-p", ANSIBLE_ROLE_CACHE_DIR]
            if force_update_roles:
                command.append("--force")
            log.debug("Downloading and installing external roles...")
            my_env = os.environ.copy()
            my_env["PATH"] = "{}:{}:{}".format(os.path.expanduser("~/.local/bin"),
                                               os.path.expanduser("~/.local/inaugurate/bin"), my_env["PATH"])

            res = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                                   env=my_env)
            for line in iter(res.stdout.readline, ""):
                if "already installed" not in line and "--force to change" not in line:
                    # log.debug("Installing role: {}".format(line.encode('utf8')))
                    click.echo("  {}".format(line.encode('utf8')), nl=False)

        if roles_to_copy.get("internal", {}):
            for src, target in roles_to_copy["internal"].items():
                log.debug("Coping internal role: {} -> {}".format(src, target))
                shutil.copytree(src, target)
        if roles_to_copy.get("external", {}):
            for src, target in roles_to_copy["external"].items():
                log.debug("Coping external role: {} -> {}".format(src, target))
                shutil.copytree(src, target)

        return result

    def get_lookup_dict(self):

        result = {}
        for play, tasks in self.plays.items():
            id = tasks.env_id
            tasks_lookup_dict = tasks.get_lookup_dict()
            temp = {TASKS_KEY: tasks_lookup_dict, ENV_NAME_KEY: tasks.env_name, ENV_ID_KEY: tasks.env_id,
                    "play_name": play}

            result[id] = temp

        return result


class NsblRunner(object):
    def __init__(self, nsbl):
        """Class to kick off rendering and running the ansible environment in question.

        Args:
          nsbl (Nsbl): the Nsbl object holding the (processed) configuration
        """

        self.nsbl = nsbl

    def run(self, target, force=True, ansible_verbose="", ask_become_pass="true", extra_plugins=None, callback=None,
            add_timestamp_to_env=False, add_symlink_to_env=False, no_run=False, display_sub_tasks=True,
            display_skipped_tasks=True, display_ignore_tasks=[], pre_run_callback=None):
        """Starts the ansible run, executing all generated playbooks.

        By default the 'nsbl_internal' ansible callback is used, which outputs easier to read outputs/results. You can, however,
        also use the callbacks that come with ansible, like 'default', 'skippy', etc.

        Args:
          target (str): the target directory where the ansible environment should be rendered
          force (bool): whether to overwrite potentially existing files at the target (most likely an old rendered ansible environment)
          ansible_verbose (str): verbosity arguments to ansible-playbook command
          ask_become_pass (str): whether the ansible-playbook call should use 'ask-become-pass' or not (possible values: 'true', 'false', 'auto' -- auto tries to do the right thing but might fail)
          callback (str): the callback to use for the ansible run. default is 'default'
          add_timestamp_to_env (bool): whether to append a timestamp to the run directory (default: False)
          add_symlink_to_env (str): whether to add a symlink to the run directory (will be deleted if exists already and force is specified) - default: False, otherwise path to symlink
          no_run (bool): whether to only render the environment, but not run it
          display_sub_tasks (bool): whether to display subtasks in the output (not applicable for all callbacks)
          display_skipped_tasks (bool): whether to display skipped tasks in the output (not applicable for all callbacks)
          extra_plugins (str): a repository of extra ansible plugins to use
          display_ignore_tasks (list): a list of strings that indicate task titles that should be ignored when displaying the task log (using the default nsbl output plugin -- this is ignored with other output callbacks)
          pre_run_callback (function): a callback to execute after the environment is rendered, but before the run is kicked off

        Return:
          dict: the parameters of the run
        """
        if callback == None:
            callback = "default"

        if callback == "nsbl_internal":
            lookup_dict = self.nsbl.get_lookup_dict()
            callback_adapter = NsblLogCallbackAdapter(lookup_dict, display_sub_tasks=display_sub_tasks,
                                                      display_skipped_tasks=display_skipped_tasks,
                                                      display_ignore_tasks=display_ignore_tasks)
        else:
            callback_adapter = NsblPrintCallbackAdapter()

        try:


            parameters = self.nsbl.render(target, extract_vars=True, force=force, ansible_args=ansible_verbose,
                                          ask_become_pass=ask_become_pass, extra_plugins=extra_plugins,
                                          callback=callback, add_timestamp_to_env=add_timestamp_to_env,
                                          add_symlink_to_env=add_symlink_to_env)

            env_dir = parameters["env_dir"]
            if pre_run_callback:
                pre_run_callback(env_dir)

            if no_run:
                log.debug("Not running environment due to 'no_run' flag set.")
                return parameters

            run_env = os.environ.copy()
            if callback.startswith("nsbl_internal"):
                run_env['NSBL_ENVIRONMENT'] = "true"

            def preexec_function():
                # Ignore the SIGINT signal by setting the handler to the standard
                # signal handler SIG_IGN.
                signal.signal(signal.SIGINT, signal.SIG_IGN)

            script = parameters['run_playbooks_script']
            # proc = subprocess.Popen(script, stdout=subprocess.PIPE, stderr=sys.stdout.fileno(), stdin=subprocess.PIPE, shell=True, env=run_env, preexec_fn=os.setsid)
            proc = subprocess.Popen(script, stdout=subprocess.PIPE, stderr=sys.stdout.fileno(), stdin=subprocess.PIPE,
                                    shell=True, env=run_env, preexec_fn=preexec_function)

            with CursorOff():
                click.echo("")
                for line in iter(proc.stdout.readline, ''):
                    callback_adapter.add_log_message(line)

                callback_adapter.finish_up()

            while proc.poll() is None:
                # Process hasn't exited yet, let's wait some
                time.sleep(0.5)

            # Get return code from process
            return_code = proc.returncode

            parameters["return_code"] = return_code

        except KeyboardInterrupt:
            # proc.terminate()
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            # proc.send_signal(signal.SIGINT)
            callback_adapter.add_error_message("\n\nKeyboard interrupt received. Exiting...\n")
            pass

        return parameters
