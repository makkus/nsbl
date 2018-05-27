# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

import fnmatch
import logging
import tempfile
import re
from collections import OrderedDict

import yaml
from cookiecutter.main import cookiecutter
from frkl.frkl import Frkl, UrlAbbrevProcessor, FrklProcessor
from jinja2 import Environment, PackageLoader

from .defaults import *
from .exceptions import NsblException

from frkl.processors import (
    UrlAbbrevProcessor,
    EnsurePythonObjectProcessor,
    EnsureUrlProcessor,
    ConfigProcessor,
)
from frkl.callbacks import FrklCallback
from frutils import dict_merge
from .utils import get_task_list_format
from .role_utils import find_roles_in_repos

from ruamel.yaml.comments import CommentedMap

from frutils import StringYAML

ANSIBLE_TASK_KEYWORDS = [
    "any_errors_fatal",
    "async",
    "become",
    "become_flags",
    "become_method",
    "become_user",
    "changed_when",
    "check_mode",
    "connection",
    "debugger",
    "delay",
    "delegate_facts",
    "delegate_to",
    "diff",
    "environment",
    "failed_when",
    "ignore_errors",
    "loop",
    "loop_control",
    "name",
    "no_log",
    "notify",
    "poll",
    "port",
    "register",
    "remote_user",
    "retries",
    "run_once",
    "tags",
    "until",
    "when"
]

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

    return {"meta": {
        "name": "import_tasks",
        "desc": "[importing tasks: {}]".format(task_list_name),
        "type": "ansible-module"},
        "vars": {
            "freeform": task_list_name
        }}

def generate_task_item_from_string(task_name):
    """Small helper to generate a task desc dict from a task name."""

    return {
        "meta": {
            "name": task_name,
        }
    }


def calculate_role_repos(role_repos):
    """Utility method to calculate which role repos to use.

    Role repos are folders containing ansible roles, and an (optional) task
    description file which is used to translate task-names in a task config
    file into roles or ansible tasks.

    Args:
      role_repos (list): a string or list of strings of local folders containing ansible roles

    Returns:
      list: a list of all local role repos to be used
    """

    if not role_repos:
        role_repos = []

    if isinstance(role_repos, string_types):
        role_repos = [role_repos]
    else:
        role_repos = role_repos

    # if not role_repos:
    # role_repos.append(DEFAULT_ROLES_PATH)
    # elif use_default_roles:
    # role_repos.insert(0, DEFAULT_ROLES_PATH)

    return role_repos


def calculate_task_aliases(task_aliases, role_repos=[], add_upper_case_versions=True):
    """Utility method to calculate which task descriptions to use.

    Task descriptions are yaml files that translate task-names in a task config
    into roles or ansible tasks, optionally with extra default parameters.

    If additional role_repos are provided, we will check whether each of them
    contains a file with the value of TASK_DESC_DEFAULT_FILENAME. If so, those
    will be added to the beginning of the resulting list.

    Args:
      task_aliases (list): a string or list of strings of local files
      role_repos (list): a list of role repos (see 'calculate_role_repos' method)
      add_upper_case_versions (bool): if true, will add an upper-case version of every task desc that includes a meta/become = true entry

    Returns:
      list: a list of dicts of all task description configs to be used

    """

    if not task_aliases:
        task_aliases = []

    if isinstance(task_aliases, string_types):
        task_aliases = [task_aliases]
    elif not isinstance(task_aliases, (list, tuple)):
        raise Exception(
            "task_descs needs to be string or list: '{}'".format(task_aliases)
        )

    if role_repos:
        repo_task_descs = []
        for repo in role_repos:
            task_desc_file = os.path.join(
                os.path.expanduser(repo), TASK_DESC_DEFAULT_FILENAME
            )
            if os.path.exists(task_desc_file):
                repo_task_descs.append(task_desc_file)

        task_aliases = repo_task_descs + task_aliases

    # TODO: check whether paths exist
    frkl_format = generate_nsbl_tasks_format([])
    task_desk_frkl = Frkl(
        task_aliases,
        [
            UrlAbbrevProcessor(),
            EnsureUrlProcessor(),
            EnsurePythonObjectProcessor(),
            FrklProcessor(frkl_format),
        ],
    )

    processed_task_descs = task_desk_frkl.process()

    if add_upper_case_versions:
        result = []
        for task in processed_task_descs:
            result.append(task)
            task_become = copy.deepcopy(task)
            task_become[TASKS_META_KEY][TASK_META_NAME_KEY] = task[TASKS_META_KEY][
                TASK_META_NAME_KEY
            ].upper()
            task_become[TASKS_META_KEY][TASK_BECOME_KEY] = True
            result.append(task_become)

        return result
    else:
        return processed_task_descs


def get_default_role_repos_and_task_aliases(role_repos, task_aliases):
    """Returns the default role repos and task aliases to use.

    role_repos is a list of local paths, task_aliases is
    """

    role_repos = calculate_role_repos(role_repos)
    task_aliases = calculate_task_aliases(task_aliases, role_repos)

    return (role_repos, task_aliases)


class AugmentingTaskProcessor(ConfigProcessor):
    """Processor to augment a basic task list.

    This will augment tasks that have a 'name' property which can be found in the task aliases list with the
    content of this task alias entry. Existing task properties won't be overwritten.

    This will also make sure that the task description has a 'meta/task-name' and 'vars' key/value pair.
    """

    def __init__(self, init_params=None):

        self.role_repos = None
        self.task_aliases = None
        self.ignore_case = None
        super(AugmentingTaskProcessor, self).__init__(init_params)

    def validate_init(self):

        self.role_repos = self.init_params.get("role_repos", [])
        if not self.role_repos:
            self.role_repos = calculate_role_repos([])
        self.task_aliases = self.init_params.get("task_aliases", [])
        self.ignore_case = self.init_params.get("ignore_case", True)
        if not self.task_aliases:
            self.task_aliases = calculate_task_descs(None, self.role_repos)
        return True

    def process_current_config(self):

        new_config = self.current_input_config
        meta_task_name = new_config["meta"]["name"]

        for task_alias in self.task_aliases:

            task_desc_name = task_alias.get("meta", {}).get(
            "name", None)

            if not task_desc_name == meta_task_name:
                continue

            new_config = dict_merge(task_alias, new_config, copy_dct=True)

        task_name = new_config.get(TASKS_META_KEY, {}).get("task-name", None)
        if not task_name:
            task_name = meta_task_name
            new_config["meta"]["task-name"] = task_name

        if "vars" not in new_config.keys():
            new_config["vars"] = {}

        return new_config

def augment_and_expand_task_list(task_lists, role_repos, task_aliases):
    """Augments a task list with defaults and/or task aliases.

    Args:
        task_list (list): the task list
        task_aliases (list): a list of task alias files
    Returns:
        list: the augmented task list
    """

    init_params = {}
    if role_repos:
        init_params["role_repos"] = role_repos
    if task_aliases:
        init_params["task_aliases"] = task_aliases

    task_format = generate_nsbl_tasks_format(task_aliases)
    chain = [FrklProcessor(task_format),
             AugmentingTaskProcessor(init_params),
        ]
    f = Frkl(task_lists, chain)
    new_list = f.process()

    for task in new_list:
        name = task["meta"]["task-name"]

        if name.isupper():
            task["meta"]["task-name"] = name.lower()
            task["meta"]["become"] = True

    return new_list

def guess_task_type(task_item, available_roles):
    """Utility method to guess the type of a task.

    Args:
        task_item (dict): the task item
        available_roles (dict): available roles dictionary
    Returns:
        str: the task type
    """

    task_name = task_item["meta"]["task-name"]

    if '.' in task_name:
        return ROLE_TASK_TYPE
    else:
        return MODULE_TASK_TYPE

def calculate_task_types(task_list, role_repos, allow_external_roles=False):
    """Parses the task list and auto-assigns task-types if necessary.

    Args:
        roles_repos (list): list of available local role repos
        allow_external_roles (bool): whether to allow (and auto-download) external ansible roles
    Returns:
        tuple: tuple in the form of (internal_role_names(list), external_role_names(list), modules_used(list))
    """

    available_roles = find_roles_in_repos(role_repos)

    typed_list = []

    internal_roles = set()
    external_roles = set()
    modules_used = set()

    for task in task_list:
        task_type = task["meta"].get("task-type", None)

        if task_type is None:
            task_type = guess_task_type(task, available_roles)
            task["meta"]["task-type"] = task_type

        if task_type not in [ROLE_TASK_TYPE, MODULE_TASK_TYPE]:
            raise NsblException("Unknown task type: {}".format(task_type))

        task_name = task["meta"]["task-name"]
        if task_type == ROLE_TASK_TYPE:
            if task_name not in available_roles.keys():
                if allow_external_roles:
                    external_roles.add(task_name)
                else:
                    raise NsblException("Role '{}' not available in local role repos ({}), and external roles download not allowed.".format(task_name, role_repos))

            else:
                internal_roles.add(task_name)
        elif task_type == MODULE_TASK_TYPE:
            modules_used.add(task_name)
        else:
            raise NsblException("Invalid task type: {}".format(task_type))

    return (list(internal_roles), list(external_roles), list(modules_used))


def ensure_task_list_format(task_list, ansible_task_file):
    """Make sure the task list is in 'freckles' format, if not, convert and add additional task file.

    Args:
        task_list (list): the task list
        ansible_task_file (str): the path to the external task file to be created (if necessary), if None a temporary one will be created
    Returns:
        tuple: tuple in the form of (final_task_list, external_files_dict)
    """

    task_list_format = get_task_list_format(task_list)

    if task_list_format == "ansible":
        file_name = os.path.basename(ansible_task_file)
        task_list_new = [get_import_task_item(file_name)]
        with open(ansible_task_file, 'w') as f:
            yaml.dump(task_list, f)
        return (task_list_new, {"type": "ansible-tasks", "path": ansible_task_file})
    else:
        return (task_list, None)

class TaskList(object):

    def __init__(self, task_list, external_files=None, run_metadata=None):

        if external_files is None:
            external_files = {}

        # runtime metadata
        if run_metadata is None:
            run_metadata = {}
        self.env_name = run_metadata.get("env_name", "localhost")
        self.env_id = run_metadata.get("env_id", None)
        if self.env_id is None:
            self.env_id = GLOBAL_ENV_ID()
        self.global_vars = run_metadata.get("vars", {})
        role_repos = run_metadata.get("role_repos", [])
        task_alias_files = run_metadata.get("task_alias_files", [])

        self.role_repos, self.task_aliases = get_default_role_repos_and_task_aliases(
              role_repos, task_alias_files)

        self.allow_external_roles = run_metadata.get("allow_external_roles", False)

        log.debug("Task list repos: {}".format(self.role_repos))
        log.debug("Task list aliases: {}".format(self.task_aliases))

        # TODO: validate task list?
        self.task_list_raw = task_list
        self.task_list = augment_and_expand_task_list(task_list, self.role_repos, self.task_aliases)
        # be aware, only first level modules are listed here (for now)
        self.internal_role_names, self.external_role_names, self.modules_used = calculate_task_types(self.task_list, self.role_repos, allow_external_roles=self.allow_external_roles)

    def render_ansible_tasklist(self):
        """Renders the playbook into a file."""

        tasklist = []

        for t in self.task_list:

            task = copy.deepcopy(t)
            log.debug("Task item: {}".format(task))
            name = task["meta"].pop("name")
            task_name = task["meta"].pop("task-name")
            task_type = task["meta"].pop("task-type")
            desc = task["meta"].pop("desc", None)
            # legacy
            task_desc = task["meta"].pop("task-desc", None)
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
            for key, value in task["meta"].items():
                if key in ANSIBLE_TASK_KEYWORDS:
                    task_item[key] = value
                else:
                    unknown_keys.append(key)
            tasklist.append(task_item)

        return tasklist

