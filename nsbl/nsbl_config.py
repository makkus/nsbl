from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import logging
import shutil
import subprocess
from datetime import datetime

import click
from cookiecutter.main import cookiecutter
from jinja2 import Environment, PackageLoader
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from frkl import load_from_url_or_path
from frutils import can_passwordless_sudo, dict_merge
from .defaults import *
from .exceptions import NsblException
from .inventory import NsblInventory
from .nsbl_context import NsblContext
from .tasklist import TaskList

try:
    set
except NameError:
    from sets import Set as set

log = logging.getLogger("nsbl")

yaml = YAML()
yaml.default_flow_style = False

def create_config(urls, nsbl_context=None, default_env_type=DEFAULT_ENV_TYPE, additional_files=None, allow_external_roles=False):

    if nsbl_context is None:
        nsbl_context = NsblContext()
    if additional_files is None:
        additional_files = {}

    if isinstance(urls, string_types):
        urls = [urls]  # we always want a list of lists as input for the NsblConfig object
    config_dicts = load_from_url_or_path(urls)

    config = NsblConfig(config_dicts, nsbl_context, default_env_type, additional_files, allow_external_roles)

    return config

# def expand_nsbl_config(configs):
#     """Expands the nsbl configuration.
#
#     Args:
#         configs (list): a list of configuration items
#     """
#
#     chain = [FrklProcessor(NSBL_INVENTORY_BOOTSTRAP_FORMAT)]
#     f = Frkl(configs, chain)
#     result = f.process()
#
#     return result

DEFAULT_ASK_BECOME = True

class NsblConfig(object):
    """Holds and parses configuration to generate Ansible task lists and inventories.

    Args:
        config (list): a list of configuration items
        nsbl_context (NsblContext): the context for this environment
        default_env_type (str): the type a environment is if it is not explicitely specified, either ENV_TYPE_HOST or ENV_TYPE_GROUP
        additional_files (dict): a dict of additional files to copy into the Ansible environment
        allow_external_roles (bool): whether to allow the downloading of external roles
    """

    def __init__(self, config, nsbl_context=None, default_env_type=DEFAULT_ENV_TYPE, additional_files=None, allow_external_roles=False):

        self.plays = CommentedMap()
        self.config = config
        if nsbl_context is None:
            nsbl_context = NsblContext()
        self.nsbl_context = nsbl_context
        self.default_env_type = default_env_type
        self.additional_files = additional_files
        self.allow_external_roles = allow_external_roles

        if additional_files is None:
            additional_files = {}
        self.additional_files = additional_files

        #self.config = expand_nsbl_config(self.config_raw)
        self.inventory = NsblInventory.create(self.config, default_env_type=self.default_env_type, pre_chain=[])
        for tasks in self.inventory.tasks:

            task_list_meta = tasks["meta"]
            env_name = task_list_meta["name"]
            env_id = task_list_meta["_env_id"]

            task_list_vars = tasks.get("vars", {})

            task_list = tasks["tasks"]

            run_metadata = {}

            tl = TaskList(task_list, nsbl_context=self.nsbl_context, additional_files=None, env_name=env_name, env_id=env_id, allow_external_roles=allow_external_roles, task_list_vars=task_list_vars, run_metadata=run_metadata)
            self.plays["{}_{}".format(env_name, env_id)] = {"task_list": tl, "meta": task_list_meta}


    def render(
        self,
        env_dir,
        global_vars=None,
        extract_vars=True,
        force=False,
        ask_become_pass=None,
        password=None,
        secure_vars=None,
        ansible_args="",
        callback="default",
        force_update_roles=False,
        add_timestamp_to_env=False,
        add_symlink_to_env=False,
        extra_paths="",
    ):
        """Creates the ansible environment in the folder provided.

        Args:
          env_dir (str): the folder where the environment should be created
          global_vars (dict): vars to be rendered as global on top of a playbook
          extract_vars (bool): whether to extract a hostvars and groupvars directory for the inventory (True), or render a dynamic inventory script for the environment (default, True) -- Not supported at the moment
          force (bool): overwrite environment if already present at the specified location, use with caution because this might delete an important folder if you get the 'target' dir wrong
          ask_become_pass (bool): whether to include the '--ask-become-pass' arg to the ansible-playbook call
          password (str): if provided, it will be used instead of asking for a password
          secure_vars (dict): vars to keep in a vault (not implemented yet)
          ansible_args (str): parameters to give to ansible-playbook (like: "-vvv")
          callback (str): name of the callback to use, default: nsbl_internal
          force_update_roles (bool): whether to overwrite external roles that were already downloaded
          add_timestamp_to_env (bool): whether to add a timestamp to the env_dir -- useful for when this is called from other programs (e.g. freckles)
          add_symlink_to_env (bool): whether to add a symlink to the current env from a fixed location (useful to archive all runs/logs)
          extra_paths (str): a colon-separated string of extra paths to be exported before the ansible playbook run
        """

        if ask_become_pass is None:
            ask_become_pass = DEFAULT_ASK_BECOME

        if not isinstance(ask_become_pass, bool):
            raise Exception("'ask_become_pass' needs to be boolean value")

        env_dir = os.path.expanduser(env_dir)
        if add_timestamp_to_env:
            start_date = datetime.now()
            date_string = start_date.strftime("%y%m%d_%H_%M_%S")
            dirname, basename = os.path.split(env_dir)
            env_dir = os.path.join(dirname, "{}_{}".format(basename, date_string))

        if global_vars is None:
            global_vars = {}

        result = {}
        result["env_dir"] = env_dir

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

        if password is None:
            if ask_become_pass:
                if can_passwordless_sudo():
                    ask_sudo = ""
                else:
                    ask_sudo = "--ask-become-pass"
            else:
                ask_sudo = ""
        else:
            ask_sudo = "--ask-become-pass"

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
            callback_plugins_list = "callback_plugins:{}/plugins/callbacks".format(
                ara_base
            )
            action_plugins_list = "action_plugins:{}/plugins/actions".format(ara_base)
            library_plugins_list = "library:{}/plugins/modules".format(ara_base)
        else:
            callback_plugins_list = "callback_plugins"
            action_plugins_list = "action_plugins"
            library_plugins_list = "library"

        cookiecutter_details = {
            "inventory": inv_target,
            "env_dir": env_dir,
            "extra_paths": extra_paths,
            "playbook_dir": playbook_dir,
            "ansible_playbook_args": ansible_playbook_args,
            "library_path": library_plugins_list,
            "action_plugins_path": action_plugins_list,
            "extra_script_commands": "",
            "ask_sudo": ask_sudo,
            "playbook": all_plays_name,
            "callback_plugins": callback_plugins_list,
            "callback_plugin_name": callback,
            "callback_whitelist": "default_to_file",
        }

        log.debug("Creating build environment from template...")
        log.debug("Using cookiecutter details: {}".format(cookiecutter_details))

        template_path = os.path.join(
            os.path.dirname(__file__), "external", "cookiecutter-ansible-environment"
        )

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

        self.inventory.write_inventory_file_or_script(
            inventory_dir, extract_vars=extract_vars
        )

        # write roles
        all_playbooks = []
        all_playbook_names = []
        ext_roles = []
        task_details = []

        for play, task_list_details in self.plays.items():

            #td = copy.deepcopy(task_list_details)
            tasks = task_list_details["task_list"]
            id = tasks.env_id
            name = tasks.env_name
            playbook_name = "play_{}_{}.yml".format(name, id)
            playbook_file = os.path.join(playbook_dir, playbook_name)

            playbook_vars = {}
            dict_merge(playbook_vars, global_vars, copy_dct=False)
            dict_merge(playbook_vars, tasks.global_vars, copy_dct=False)
            playbook_vars["_env_id"] = id
            playbook_vars["_env_name"] = name

            task_list = tasks.render_ansible_tasklist()

            playbook_dict = CommentedMap()
            playbook_dict["hosts"] = name
            playbook_dict["vars"] = playbook_vars
            playbook_dict["tasks"] = task_list

            #td["playbook"] = playbook_dict
            all_playbooks.append({"name": playbook_name, "dict": playbook_dict, "file": playbook_file})
            all_playbook_names.append(playbook_name)

            dict_merge(self.additional_files, tasks.additional_files, copy_dct=False)

            if tasks.external_role_names:
                for n in tasks.external_role_names:
                    if n not in ext_roles:
                        ext_roles.append(n)

        # copy external files
        external_files_vars = {}

        action_plugins_target = os.path.join("plays", "action_plugins")
        callback_plugins_target = os.path.join("plays", "callback_plugins")
        filter_plugins_target = os.path.join("plays", "filter_plugins")
        library_plugins_target = os.path.join("plays", "library")
        roles_target = os.path.join("roles", "internal")
        task_lists_target = "task_lists"

        for path, details in self.additional_files:

            file_type = details["type"]
            playbook_var_name = details["var_name"]
            file_name = details["file_name"]

            if file_type == ADD_TYPE_TASK_LIST:
                target = os.path.join(env_dir, task_lists_target, file_name)
                playbook_var_value = os.path.join("{{ playbook_dir }}", "..", task_lists_target, file_name)
                copy_source_type = "file"
            elif file_type == ADD_TYPE_ROLE:
                target = os.path.join(env_dir, roles_target, file_name)
                playbook_var_value = None
                copy_source_type = "dir"
            elif file_type == ADD_TYPE_ACTION:
                target = os.path.join(env_dir, action_plugins_target, file_name)
                playbook_var_value = None
                copy_source_type = "file"
            elif file_type == ADD_TYPE_CALLBACK:
                target = os.path.join(env_dir, callback_plugins_target, file_name)
                playbook_var_value = None
                copy_source_type = "file"
            elif file_type == ADD_TYPE_FILTER:
                target = os.path.join(env_dir, filter_plugins_target, file_name)
                playbook_var_value = None
                copy_source_type = "file"
            elif file_type == ADD_TYPE_LIBRARY:
                target = os.path.join(env_dir, library_plugins_target, file_name)
                playbook_var_value = None
                copy_source_type = "file"
            else:
                raise NsblException("Invalid external file type: {}".format(file_type))

            log.debug("Copying {} '{}': {}".format(file_type, file_name, target))
            target_parent = os.path.basename(target)
            if not os.path.exists(target_parent):
                os.makedirs(target_parent)
            if not os.path.isdir(os.path.realpath(target_parent)):
                raise NsblException("Can't copy files to '{}': not a directory".format(target_parent))

            if copy_source_type == "file":
                shutil.copyfile(path, target)
            else:
                shutil.copytree(path, target)

            if playbook_var_value:
                if playbook_var_name in external_files_vars.keys():
                    raise NsblException("Duplicate key for external files: {}".format(playbook_var_name))
                log.debug("Setting variable '{}' to: {}".format(playbook_var_name, playbook_var_value))
                external_files_vars[playbook_var_name] = playbook_var_value

        # render all playbooks
        for playbook in all_playbooks:

            playbook_file = playbook["file"]
            playbook_dict = playbook["dict"]

            # adding external files vars
            dict_merge(playbook_dict.setdefault("vars", {}), external_files_vars, copy_dct=False)

            with open(playbook_file, 'w') as pf:
                yaml.dump([playbook_dict], pf)


        result["task_details"] = task_details
        result["additional_files"] = self.additional_files

        jinja_env = Environment(loader=PackageLoader("nsbl", "templates"))
        template = jinja_env.get_template("play.yml")
        output_text = template.render(playbooks=all_playbook_names)

        all_plays_file = os.path.join(env_dir, "plays", all_plays_name)
        result["all_plays_file"] = all_plays_file
        with open(all_plays_file, "w") as text_file:
            text_file.write(output_text)

        if ext_roles:
            if not self.allow_external_roles:
                raise Exception(
                    "Downloading of external roles not allowed, check your configuration."
                )

            ext_roles_target = os.path.join(env_dir, "roles", "external")
            # render roles_requirements.yml
            jinja_env = Environment(loader=PackageLoader("nsbl", "templates"))
            roles_requirements_file = os.path.join(ext_roles_target, "roles_requirements.yml")

            if not os.path.exists(ext_roles_target):
                os.makedirs(ext_roles_target)

            roles_to_copy = {}
            for role in ext_roles:
                role_src = os.path.join(ANSIBLE_ROLE_CACHE_DIR, role)
                target = os.path.join(ext_roles_target, role)
                roles_to_copy[role_src] = target

                template = jinja_env.get_template("external_role.yml")
                output_text = template.render(role={"src": role, "name": role})
                with open(roles_requirements_file, "a") as myfile:
                    myfile.write(output_text)

            # download external roles
            click.echo("\nDownloading external roles...")
            role_requirement_file = os.path.join(
                env_dir, "roles", "external", "roles_requirements.yml"
            )

            if not os.path.exists(ANSIBLE_ROLE_CACHE_DIR):
                os.makedirs(ANSIBLE_ROLE_CACHE_DIR)

            command = [
                "ansible-galaxy",
                "install",
                "-r",
                role_requirement_file,
                "-p",
                ANSIBLE_ROLE_CACHE_DIR,
            ]
            if force_update_roles:
                command.append("--force")
            log.debug("Downloading and installing external roles...")
            my_env = os.environ.copy()
            my_env["PATH"] = "{}:{}:{}".format(
                os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/.local/share/inaugurate/bin"),
                my_env["PATH"],
            )

            res = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                env=my_env,
            )
            for line in iter(res.stdout.readline, ""):
                if "already installed" not in line and "--force to change" not in line and "unspecified" not in line:
                    # log.debug("Installing role: {}".format(line.encode('utf8')))
                    click.echo("  {}".format(line.encode("utf8")), nl=False)

            if roles_to_copy:
                if len(ext_roles) == 1:
                    click.echo("Copying role from Ansible cache: {}".format(ext_roles[0]))
                else:
                    click.echo("Copying roles from Ansible cache:")
                    for r in ext_roles:
                        click.echo("  - {}".format(r))
                for src, target in roles_to_copy.items():
                    log.debug("Coping external role: {} -> {}".format(src, target))
                    shutil.copytree(src, target)

        return result
