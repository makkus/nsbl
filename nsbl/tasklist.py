# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

import copy
import logging
from collections import OrderedDict

import yaml
from ruamel.yaml.comments import CommentedMap
from six import string_types

from frkl import load_from_url_or_path, Frkl
from frkl.processors import ConfigProcessor
from frutils import StringYAML, dict_merge
from .defaults import *
from .exceptions import NsblException
from .nsbl_context import NsblContext
from .tasklist_utils import get_task_list_format


GLOBAL_ENV_ID_COUNTER = 999999


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
        "meta": {
            "name": "import_tasks",
            "desc": "[importing tasks: {}]".format(task_list_name),
            "type": "ansible-module",
        },
        "vars": {"freeform": task_list_name},
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

    def __init__(self, init_params=None):

        self.nsbl_context = None
        super(AugmentingTaskProcessor, self).__init__(init_params)

    def validate_init(self):

        self.nsbl_context = self.init_params.get("context", NsblContext())
        return True

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

        return new_config


def generate_nsbl_tasks_format(
    task_aliases=None, tasks_format=DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT
):
    """Utility method to populate the KEY_MOVE_MAP key for the tasks """

    if task_aliases is None:
        task_aliases = {}

    result = copy.deepcopy(tasks_format)
    for alias, task_desc in task_aliases.items():
        import pprint

        pprint.pprint(task_desc)
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
    chain = [FrklProcessor(task_format), AugmentingTaskProcessor(init_params)]
    f = Frkl(task_lists, chain)
    new_list = f.process()

    for task in new_list:
        name = task["task"]["task-name"]

        if name.isupper():
            task["task"]["task-name"] = name.lower()
            task["task"]["become"] = True

    return new_list


def guess_task_type(task_item, available_roles):
    """Utility method to guess the type of a task.

    Args:
        task_item (dict): the task item
        available_roles (dict): available roles dictionary
    Returns:
        str: the task type
    """

    task_name = task_item["task"]["task-name"]

    if "." in task_name:
        return ROLE_TASK_TYPE
    else:
        return MODULE_TASK_TYPE


def calculate_task_types(
    task_list, nsbl_context, allow_external_roles=False, relative_base_path=None
):
    """Parses the task list and auto-assigns task-types if necessary.

    Args:
        nsbl_context (NsblContext): the nsbl context object for this run
        allow_external_roles (bool): whether to allow (and auto-download) external ansible roles
        relative_base_path (str): if a task item contains an import for a relative task list, this base path is used
    Returns:
        tuple: tuple in the form of (internal_role_names(list), external_role_names(list), modules_used(list))
    """

    if relative_base_path is None:
        relative_base_path = DEFAULT_TASK_LIST_BASE_PATH

    available_roles = nsbl_context.available_roles

    typed_list = []

    internal_roles = set()
    external_roles = set()
    modules_used = set()

    for task in task_list:
        task_type = task["task"].get("task-type", None)

        if task_type is None:
            task_type = guess_task_type(task, available_roles)
            task["task"]["task-type"] = task_type

        if task_type not in [
            ROLE_TASK_TYPE,
            MODULE_TASK_TYPE,
            ANSIBLE_TASK_LIST_TASK_TYPE,
        ]:
            raise NsblException("Unknown task type: {}".format(task_type))

        task_name = task["task"]["task-name"]
        if task_type == ROLE_TASK_TYPE:
            if task_name not in available_roles.keys():
                if allow_external_roles:
                    external_roles.add(task_name)
                else:
                    raise NsblException(
                        "Role '{}' not available in local role repos ({}), and external roles download not allowed.".format(
                            task_name, nsbl_context.role_repo_paths
                        )
                    )

            else:
                internal_roles.add(task_name)
        elif task_type == MODULE_TASK_TYPE:
            modules_used.add(task_name)
        elif task_type == ANSIBLE_TASK_LIST_TASK_TYPE:
            if task_name != "import_tasks" and task_name != "include_tasks":
                raise NsblException(
                    "'task-name' value for the {} task type needs to be either 'import_tasks' or 'include_tasks': {}".format(
                        ANSIBLE_TASK_LIST_TASK_TYPE
                    ),
                    task,
                )
            free_form = task.get("vars", {}).get("free_form", None)
            if free_form is None:
                raise NsblException(
                    "task item of type {} needs the 'free_form' variable key: {}".format(
                        ANSIBLE_TASK_LIST_TASK_TYPE
                    ),
                    task,
                )

        else:
            raise NsblException("Invalid task type: {}".format(task_type))

        task_roles = task["task"].get("task-roles", [])
        for tr in task_roles:
            if tr not in available_roles.keys():
                if allow_external_roles:
                    external_roles.add(tr)
                else:
                    raise NsblException(
                        "Role '{}' not available in local role repos ({}), and external roles download not allowed.".format(
                            task_name, nsbl_context.role_repo_paths
                        )
                    )
            else:
                internal_roles.add(task_name)

    return (list(internal_roles), list(external_roles), list(modules_used))


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


class TaskItem(object):
    """Class for a single task item.

    Args:
        task_desc (dict): a string or dict to describe the task
    """

    def __init__(self, task_desc):

        log.debug("Parsing task description: {}".format(task_desc))
        self.task_desc_orig = copy.deepcopy(task_desc)
        self.generic_desc = None
        self.ansible_desc = None

        if isinstance(task_desc, string_types):
            log.debug(
                "task item '{}' is string, determining this is a 'freckles' task item".format(
                    task_desc
                )
            )
            self.generic_desc = task_desc
        elif not isinstance(task_desc, (dict, CommentedMap, OrderedDict)):
            raise Exception("not a valid task item type: {}".format(task_desc))

        else:
            keys = set(task_desc.keys())
            if "task" in keys:
                log.debug(
                    "task item contains 'task' key, this means this is a 'freckles' task item"
                )
                self.generic_desc = task_desc
            elif len(keys) == 1:
                pass


def create_task_list(
    urls,
    role_repo_paths=None,
    task_alias_files=None,
    additional_files=None,
    env_name=None,
    env_id=None,
    allow_external_roies=False,
    task_list_vars=None,
    run_metadata=None,
):

    if not isinstance(urls, string_types):
        raise NsblException(
            "Only single files supported for creating a task list: {}".format(urls)
        )

    urls = [urls]  # we always want a list of lists as input for the Nsbl object
    task_lists = load_from_url_or_path(urls)
    tl = TaskList(
        task_lists,
        role_repo_paths=role_repo_paths,
        task_alias_files=task_alias_files,
        additional_files=additional_files,
        env_name=env_name,
        env_id=env_id,
        allow_external_roles=allow_external_roies,
        task_list_vars=task_list_vars,
        run_metadata=run_metadata,
    )

    return tl


class TaskList(object):
    """Class to hold a list of tasks.

    Args:
        task_list (list): a list of task items
        relative_base_path (str): if relative task-list imports are used, this is the base path for them
        role_repo_paths (list): a list of local folders that contain trusted Ansible roles
        task_alias_files (list): a list of paths to task-alias files
        additional_files (dict): additional files for this task list (e.g. task lists)
        env_name (str): the name of the environment for this task list
        env_id (int): the id of the environment for this task list
        allow_external_roles (bool): whether to allow external roles to be downloaded from Ansible galaxy if not found in one of the local role repos
        task_list_vars (dict): 'global' vars for this task list, those can be used in the task list using the '{{ var_name }}' template format
        run_metadata (dict): freestyle additional metadata, not used currently
    """

    def __init__(
        self,
        task_list,
        relative_base_path=None,
        nsbl_context=None,
        additional_files=None,
        env_name=None,
        env_id=None,
        allow_external_roles=False,
        task_list_vars=None,
        run_metadata=None,
    ):

        if relative_base_path is None:
            relative_base_path = DEFAULT_TASK_LIST_BASE_PATH
        self.relative_base_path = relative_base_path

        if additional_files is None:
            additional_files = {}

        self.additional_files = additional_files

        # runtime metadata
        if run_metadata is None:
            run_metadata = {}

        if env_name is None:
            env_name = "localhost"
        self.env_name = env_name
        self.allow_external_roles = allow_external_roles

        if env_id is None:
            env_id = GLOBAL_ENV_ID()
        self.env_id = env_id
        if task_list_vars is None:
            task_list_vars = {}
        self.global_vars = task_list_vars

        if nsbl_context is None:
            nsbl_context = NsblContext()

        self.nsbl_context = nsbl_context

        # TODO: validate task list?
        self.task_list_raw = task_list
        self.task_list = augment_and_expand_task_list([task_list], self.nsbl_context)
        # be aware, only first level modules are listed here (for now)
        self.internal_role_names, self.external_role_names, self.modules_used = calculate_task_types(
            self.task_list,
            self.nsbl_context,
            allow_external_roles=self.allow_external_roles,
            relative_base_path=self.relative_base_path,
        )

    def render_ansible_tasklist(self):
        """Renders the playbook into a file."""

        tasklist = []

        for t in self.task_list:

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

            task_item = CommentedMap()
            task_item["name"] = desc
            vars = CommentedMap()
            for key, value in task.pop("vars").items():
                vars[key] = value
            task_item[task_name] = vars

            # add the remaining key/value pairs
            unknown_keys = []
            for key, value in task["task"].items():
                if key in ANSIBLE_TASK_KEYWORDS:
                    task_item[key] = value
                else:
                    unknown_keys.append(key)
            tasklist.append(task_item)

        return tasklist
