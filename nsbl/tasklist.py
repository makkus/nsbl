# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

import copy
import logging
from collections import OrderedDict
from os.path import splitext

import yaml
from ruamel.yaml.comments import CommentedMap
from six import string_types

from frkl import load_object_from_url_or_path, Frkl
from frkl.utils import get_url_parents
from frkl.processors import ConfigProcessor
from frutils import StringYAML, dict_merge, is_url_or_abbrev
from .defaults import *
from .exceptions import NsblException
from .nsbl_context import NsblContext
from .tasklist_utils import get_task_list_format, get_tasklist_file_format


GLOBAL_ENV_ID_COUNTER = 1110
GLOBAL_TASKLIST_ID_COUNTER = 1110


def GLOBAL_TASKLIST_ID():
    global GLOBAL_TASKLIST_ID_COUNTER
    GLOBAL_TASKLIST_ID_COUNTER = GLOBAL_TASKLIST_ID_COUNTER + 1
    return GLOBAL_TASKLIST_ID_COUNTER


def GLOBAL_ENV_ID():
    global GLOBAL_ENV_ID_COUNTER
    GLOBAL_ENV_ID_COUNTER = GLOBAL_ENV_ID_COUNTER + 1
    return GLOBAL_ENV_ID_COUNTER


yaml = StringYAML()
yaml.default_flow_style = False

log = logging.getLogger("nsbl")


def to_nice_yaml(var):
    """util function to convert to yaml in a jinja template"""
    return yaml.dump(var)


def get_import_task_item(task_list_name):
    """Small helper toget the task item for importing a task list."""

    return {
        "task": {
            "name": "import_tasks",
            "desc": "[importing tasks: {}]".format(task_list_name),
            "task-name": task_list_name,
            "task-type": TASK_LIST_TASK_TYPE,
        }
    }


def generate_task_item_from_string(task_name):
    """Small helper to generate a task desc dict from a task name."""

    return {"meta": {"name": task_name}}


class AugmentingTaskProcessor(ConfigProcessor):
    """Processor to augment a basic task list.

    This will augment tasks that have a 'name' property which can be found in the task aliases list with the
    content of this task alias entry. Existing task properties won't be overwritten.

    This will also make sure that the task description has a 'meta/task-name' and 'vars' key/value pair.
    """

    def __init__(self, **init_params):

        super(AugmentingTaskProcessor, self).__init__(**init_params)
        self.nsbl_context = self.init_params.get("context", NsblContext())

    def process_current_config(self):

        new_config = self.current_input_config

        meta_task_name = new_config["task"]["name"]

        md = self.nsbl_context.task_aliases.get(meta_task_name, None)
        if md is not None:
            new_config = dict_merge(md, new_config, copy_dct=True)

        task_name = new_config.get("task", {}).get("task-name", None)
        if not task_name:
            task_name = meta_task_name
            new_config["task"]["task-name"] = task_name

        if "vars" not in new_config.keys():
            new_config["vars"] = {}

        if new_config["task"]["task-name"].isupper():
            new_config["task"]["task-name"] = new_config["task"]["task-name"].lower()
            new_config["task"]["become"] = True

        return new_config


def generate_nsbl_tasks_format(
    task_aliases=None, tasks_format=DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT
):
    """Utility method to populate the KEY_MOVE_MAP key for the tasks """

    if task_aliases is None:
        task_aliases = {}

    result = copy.deepcopy(tasks_format)
    for alias, task_desc in task_aliases.items():

        if DEFAULT_KEY_KEY in task_desc["task"].keys():
            # TODO: check for duplicate keys?
            result[KEY_MOVE_MAP_NAME][task_desc["task"]["name"]] = "vars/{}".format(
                task_desc["task"][DEFAULT_KEY_KEY]
            )

    return result


def augment_and_expand_task_list(task_lists, nsbl_context):
    """Augments a task list with defaults and/or task aliases.

    Args:
        task_list (list): the task list
        task_aliases (list): a list of task alias files
    Returns:
        list: the augmented task list
    """

    init_params = {"context": nsbl_context}

    task_format = generate_nsbl_tasks_format(nsbl_context.task_aliases)
    chain = [FrklProcessor(**task_format), AugmentingTaskProcessor(context=nsbl_context)]
    f = Frkl(task_lists, chain)
    new_list = f.process()

    return new_list


def fill_task_type(
    task_item,
    tasklist_parent,
    nsbl_context,
    tasklist_id,
    env_id,
    internal_roles,
    external_roles,
    internal_tasklist_files,
    modules_used,
):
    """Utility method to guess the type of a task and fill in all necessary properties.

    Args:
        task_item (dict): the task item
        tasklist_parent (str): the primary parent dir/url to use when importing/includeing tasklists. other search dirs can be specified in nsbl_context
        nsbl_context (NsblContext): the context for this Ansible environment
        tasklist_id (int): the tasklist id for this tasklist in the current environment
        env_id (int): the id for this Ansible environment
        internal_roles (set): the set to which to add new internal roles
        external_roles (set): the set to which to add new external roles
        internal_tasklist_files (dict): the dict to which to add new internal (local) task files
        modules_used (set): the list to which to add modules used
    Returns:
        str: the task type
    """

    task_name = task_item["task"]["task-name"]
    task_type = task_item["task"].get("task-type", None)

    if task_type == ROLE_TASK_TYPE or (
        task_type is None
        and (
            (
                "." in task_name
                and not (
                    task_name.startswith("include_") or task_name.startswith("import_")
                )
            )
            or task_name.startswith("include_role::")
            or task_name.startswith("import_role::")
        )
    ):

        if task_name.startswith("include_role::") or task_name.startswith(
            "import_role::"
        ):
            include_type, _, task_name = task_name.partition("::")
            task_item["task"]["task-name"] = task_name
            task_item["task"]["include-type"] = include_type
        role_available = task_name in nsbl_context.available_roles
        if not role_available:
            if not nsbl_context.allow_external_roles:
                raise NsblException(
                    "Role '{}' not available and exernal roles not allowed".format(
                        task_name
                    )
                )
            else:
                task_item["task"]["role-type"] = "external"
                external_roles.add(task_name)
        else:
            task_item["task"]["role-type"] = "internal"
            internal_roles.add(task_name)

        task_item["task"]["task-type"] = ROLE_TASK_TYPE
        if "include-type" not in task_item["task"].keys():
            task_item["task"]["include-type"] = "import_role"

        log.debug("role task-item: {}".format(task_item))

    elif task_type == TASK_LIST_TASK_TYPE or (
        task_type is None
        and (
            task_name.startswith("include_tasks::")
            or task_name.startswith("import_tasks::")
        )
    ):

        if task_name.startswith("include_") or task_name.startswith("import_"):
            include_type, _, task_name = task_name.partition("::")
            task_item["task"]["task-name"] = task_name
            task_item["task"]["include-type"] = include_type

        task_item["task"]["task-type"] = TASK_LIST_TASK_TYPE
        if "include-type" not in task_item["task"].keys():
            task_item["task"]["include-type"] = "import_tasks"

        task_list_file = task_item["task"]["task-name"]

        # TODO: this all could be improved with the tasklist_search path
        # currently it's not really easily possible to mix/match local & remote paths
        file_path = None
        content = None
        if is_url_or_abbrev(task_list_file) or (
            not os.path.isabs(task_list_file) and is_url_or_abbrev(tasklist_parent)
        ):
            if nsbl_context.allow_external_tasklists:
                raise NsblException(
                    "Remote task lists not allowed for this environment."
                )
            if is_url_or_abbrev(task_list_file):
                url = task_list_file
            elif not os.path.isabs(task_list_file):
                url = os.path.join(tasklist_parent, task_list_file)
            else:
                url = task_list_file
            log.info("- downloading remote tasklist: {}".format(url))
            content = load_object_from_url_or_path(url)
            if not content:
                raise NsblException("Empty remote tasklist: {}".format(task_list_file))
            file_path = task_list_file
        else:
            if os.path.isabs(task_list_file):
                if not os.path.exists(task_list_file):
                    raise NsblException(
                        "Can't import tasklist file '{}': does not exist".format(
                            task_list_file
                        )
                    )
                else:
                    if os.path.isdir(task_list_file):
                        raise NsblException(
                            "Can't import tasklist '{}: not a file".format(
                                task_list_file
                            )
                        )

                file_path = task_list_file
            else:
                log.debug(
                    "trying to find tasklist file '{}' in tasklist repos".format(
                        task_list_file
                    )
                )
                search_paths = []
                if tasklist_parent:
                    search_paths.append(tasklist_parent)
                search_paths.extend(nsbl_context.tasklist_search_paths)

                if not search_paths:
                    raise NsblException(
                        "No tasklist search paths provided, can't import tasklist '{}'".format(
                            task_list_file
                        )
                    )
                for p in search_paths:
                    abs_path = os.path.join(p, task_list_file)
                    log.debug("  - trying path: {}".format(abs_path))
                    if not os.path.exists(abs_path):
                        log.debug("     -> does not exist")
                        continue
                    if os.path.isdir(os.path.realpath(abs_path)):
                        log.debug("     -> not a file")
                        log.warn(
                            "Can't import tasklist '{}: not a file. Ignoring...".format(
                                task_list_file
                            )
                        )
                        continue

                    log.debug("      -> exists, processing...")
                    file_path = abs_path
                    break

        if file_path is None and content is None:
            raise NsblException(
                "Could not find included/imported tasklist '{}' in paths: {}".format(
                    task_list_file, search_paths
                )
            )

        if not content:
            tf_format, content = get_tasklist_file_format(file_path)
        else:
            tf_format = get_task_list_format(content)

        log.debug("Tasklist '{}' format: {}".format(file_path, tf_format))

        if tf_format not in ["unknown", "freckles", "ansible"]:
            raise NsblException(
                "Invalid tasklist format for '{}': {}".format(file_path, tf_format)
            )
        else:
            task_item["task"]["tasklist_format"] = tf_format

        file_name, extension = splitext(os.path.basename(file_path))

        unique_file_name = "{}_env_{}_tasklist_{}{}".format(
            file_name, env_id, tasklist_id, extension
        )
        var_name = "_{}_env_{}_tasklist_{}".format(file_name, env_id, tasklist_id)

        internal_tasklist_files[file_path] = {
            "var_name": var_name,
            "target_name": unique_file_name,
            "type": ADD_TYPE_TASK_LIST,
            "tasklist_format": tf_format,
        }
        internal_tasklist_files[file_path]["tasklist_content"] = content

        task_item["task"]["tasklist_var"] = var_name
        task_item["task"]["tasklist_target"] = unique_file_name

        log.debug("tasklist task-item: {}".format(task_item))
    else:
        task_item["task"]["task-type"] = MODULE_TASK_TYPE
        log.debug("module task-item: {}".format(task_item))
        modules_used.add(task_name)


def calculate_task_types(task_list, tasklist_parent, nsbl_context, tasklist_id, env_id):
    """Parses the task list and auto-assigns task-types if necessary.

    Args:
        task_list (list): the list of tasks
        tasklist_parent (str): the primary parent dir/url to use when importing/includeing tasklists. other search dirs can be specified in nsbl_context
        nsbl_context (NsblContext): the nsbl context object for this run
        tasklist_id (int): the tasklist id for this tasklist in the current environment
        env_id (int): the id for this Ansible environment
    Returns:
        tuple: tuple in the form of (internal_role_names(list), external_role_names(list), modules_used(list))
    """

    typed_list = []

    internal_roles = set()
    external_roles = set()
    modules_used = set()
    internal_tasklist_files = {}

    for task in task_list:

        fill_task_type(
            task,
            tasklist_parent,
            nsbl_context,
            tasklist_id,
            env_id,
            internal_roles,
            external_roles,
            internal_tasklist_files,
            modules_used,
        )
        task_type = task["task"]["task-type"]
        task_name = task["task"]["task-name"]

        task_roles = task["task"].get("task-roles", [])
        for tr in task_roles:
            if tr not in nsbl_context.available_roles.keys():
                if nsbl_context.allow_external_roles:
                    external_roles.add(tr)
                else:
                    raise NsblException(
                        "Role '{}' not available in local role repos ({}), and external roles download not allowed.".format(
                            task_name, nsbl_context.role_repo_paths
                        )
                    )
            else:
                internal_roles.add(task_name)

    return (
        list(internal_roles),
        list(external_roles),
        internal_tasklist_files,
        list(modules_used),
    )


def ensure_task_list_format(task_list, ansible_task_file, env_id, task_list_id):
    """Make sure the task list is in 'freckles' format, if not, convert and add additional task file.

    Args:
        task_list (list): the task list
        ansible_task_file (str): the path to the external task file to be created (if necessary), if None a temporary one will be created
        env_id: the id of the environment (used to calculate the variable name)
        task_list_id: the id of the task_list inside the environment (used to calculate the variable name)
    Returns:
        tuple: tuple in the form of (final_task_list, external_files_dict)
    """

    task_list_format = get_task_list_format(task_list)

    if task_list_format == "ansible":
        file_name = os.path.basename(ansible_task_file)
        task_list_new = [get_import_task_item(file_name)]
        with open(ansible_task_file, "w") as f:
            yaml.dump(task_list, f)
        return (
            task_list_new,
            {
                ansible_task_file: {
                    "type": ADD_TYPE_TASK_LIST,
                    "file_name": "task_list_{}_{}.yml".format(env_id, task_list_id),
                    "var_name": "task_list_{}_{}".format(env_id, task_list_id),
                }
            },
        )
    else:
        return (task_list, None)


def create_tasklist(
    url,
    tasklist_parent=None,
    role_repo_paths=None,
    task_alias_files=None,
    allow_external_roies=False,
    allow_external_tasklists=False,
    tasklist_search_paths=None,
    tasklist_id=None,
    env_id=None,
    tasklist_vars=None,
    run_metadata=None,
):

    context = NsblContext(
        role_repo_paths=role_repo_paths,
        task_alias_paths=task_alias_files,
        allow_external_roles=allow_external_roies,
        allow_external_tasklists=allow_external_tasklists,
        tasklist_search_paths=tasklist_search_paths,
    )
    tl = create(
        url,
        tasklist_parent,
        nsbl_context=context,
        tasklist_id=tasklist_id,
        env_id=env_id,
        tasklist_vars=tasklist_vars,
        run_metadata=run_metadata,
    )
    return tl


def create(
    url,
    tasklist_parent=None,
    nsbl_context=None,
    tasklist_id=None,
    env_id=None,
    tasklist_vars=None,
    run_metadata=None,
):

    if not isinstance(url, string_types):
        raise NsblException(
            "Only single files supported for creating a task list: {}".format(url)
        )

    url = [url]  # we always want a list of lists as input for the Nsbl object

    task_lists = load_object_from_url_or_path(url)
    tl = TaskList(
        task_lists,
        tasklist_parent=tasklist_parent,
        nsbl_context=nsbl_context,
        tasklist_id=tasklist_id,
        env_id=env_id,
        tasklist_vars=tasklist_vars,
        run_metadata=run_metadata,
    )

    return tl

def create_tasklist_meta():

    meta = {
        "tasklist_parent": "parent dir",
        "tasklist_id": "tasklist id",
        "env_id": "environment id",
    }


class TaskList(object):
    """Class to hold a list of tasks.

    Args:
        tasklist (list): a list of task items
        tasklist_parent (str): the primary parent dir/url to use when importing/includeing tasklists. other search dirs can be specified in nsbl_context
        nsbl_context (NsblContext): the context for this list
        tasklist_id (int): the task list id for this task list
        env_id (int): the id of the environment for this task list
        allow_external_roles (bool): whether to allow external roles to be downloaded from Ansible galaxy if not found in one of the local role repos
        tasklist_vars (dict): 'global' vars for this task list, those can be used in the task list using the '{{ var_name }}' template format
        run_metadata (dict): freestyle additional metadata, not used currently
    """

    def __init__(
        self,
        tasklist,
        tasklist_parent=None,
        nsbl_context=None,
        tasklist_id=None,
        env_id=None,
        tasklist_vars=None,
        run_metadata=None,
    ):

        self.tasklist_parent = tasklist_parent
        self.additional_files = {}

        # runtime metadata
        if run_metadata is None:
            run_metadata = {}

        if tasklist_id is None:
            tasklist_id = GLOBAL_TASKLIST_ID()
        self.tasklist_id = tasklist_id

        if env_id is None:
            env_id = GLOBAL_ENV_ID()
        self.env_id = env_id

        if tasklist_vars is None:
            tasklist_vars = {}
        self.global_vars = tasklist_vars
        # in the future, could also support 'set_fact'
        self.global_vars_rendered_as_vars_dict = True

        if nsbl_context is None:
            nsbl_context = NsblContext()

        self.nsbl_context = nsbl_context

        self.tasklist_raw = tasklist
        self.tasklist = augment_and_expand_task_list([tasklist], self.nsbl_context)
        # be aware, only first level modules are listed here (for now)
        self.internal_role_names, self.external_role_names, self.tasklist_files, self.modules_used = calculate_task_types(
            self.tasklist,
            self.tasklist_parent,
            self.nsbl_context,
            self.tasklist_id,
            self.env_id,
        )

        # parsing other tasklists
        self.children = []
        counter = 0
        for tasklist_path, details in self.tasklist_files.items():

            tl_id = ((self.tasklist_id + 1) * 100) + counter

            parent = get_url_parents(tasklist_path, return_list=True)

            if len(parent) != 1:
                raise NsblException(
                    "Can't calculate single parent for url '{}'. This is a bug, please open an issue on Github."
                )

            if details["tasklist_format"] == "ansible":
                continue
            elif details["tasklist_format"] == "unknown":
                try:
                    tl = TaskList(
                        details["tasklist_content"],
                        tasklist_parent=parent[0],
                        nsbl_context=nsbl_context,
                        tasklist_id=tl_id,
                        env_id=self.env_id,
                    )
                    details["tasklist_format"] == "freckles"
                except (Exception) as e:
                    details["tasklist_format"] == "ansible"
                    continue
            else:
                tl = TaskList(
                    details["tasklist_content"],
                    tasklist_parent=parent[0],
                    nsbl_context=nsbl_context,
                    tasklist_id=tl_id,
                    env_id=self.env_id,
                )

            self.children.append(tl)
            dict_merge(self.additional_files, tl.additional_files, copy_dct=False)
            for child in tl.children:
                self.children.append(child)
                dict_merge(
                    self.additional_files, child.additional_files, copy_dct=False
                )

            details["tasklist_rendered"] = tl.render_ansible_tasklist_dict()
            # print(details["tasklist_rendered"])
            counter = counter + 1

        # adding tasklists to additional files
        dict_merge(self.additional_files, self.tasklist_files, copy_dct=False)

        # adding roles to additional files
        for role in self.internal_role_names:

            role_path = self.nsbl_context.available_roles.get(role)
            self.additional_files[role_path] = {
                "type": ADD_TYPE_ROLE,
                "target_name": role,
            }

    def render_ansible_tasklist_dict(self):
        """Renders the playbook into a file."""

        result = []

        for t in self.tasklist:

            task = copy.deepcopy(t)
            log.debug("Task item: {}".format(task))
            name = task["task"].pop("name")
            task_name = task["task"].pop("task-name")
            task_type = task["task"].pop("task-type")
            desc = task["task"].pop("desc", None)
            # legacy
            task_desc = task["task"].pop("task-desc", None)
            if desc is None:
                desc = task_desc
            if desc is None:
                desc = name

            vars = CommentedMap()
            for key, value in task.pop("vars").items():
                vars[key] = value

            task_item = CommentedMap()
            task_item["name"] = desc

            if task_type == MODULE_TASK_TYPE:
                task_item[task_name] = vars
            elif task_type == TASK_LIST_TASK_TYPE:
                task_key = task["task"]["include-type"]
                task_item[task_key] = "{{{{ {} }}}}".format(
                    task["task"]["tasklist_var"]
                )
                task_item["vars"] = vars
            elif task_type == ROLE_TASK_TYPE:
                task_key = task["task"]["include-type"]
                task_item[task_key] = task_name
                task_item["vars"] = vars

            # add the remaining key/value pairs
            unknown_keys = []
            for key, value in task["task"].items():
                if key in ANSIBLE_TASK_KEYWORDS:
                    task_item[key] = value
                else:
                    unknown_keys.append(key)
            result.append(task_item)

        return result
