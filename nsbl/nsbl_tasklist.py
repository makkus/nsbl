# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

import copy
import logging
from os.path import splitext

from frkl import Frkl, load_object_from_url_or_path
from frkl.utils import get_url_parents
from frkl.processors import ConfigProcessor
from frutils import StringYAML, dict_merge, is_url_or_abbrev
from .defaults import *
from .exceptions import NsblException
from freckles import FrecklesTasklist, FrecklesContext
from .nsbl_context import NsblContext
from .role_utils import find_roles_in_repos
from .task_alias_utils import calculate_task_aliases
from .tasklist_utils import get_task_list_format, get_tasklist_file_format
from ruamel.yaml.comments import CommentedMap

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


class NsblContext(FrecklesContext):

    def __init__(self, allow_external_roles=None, allow_external_tasklists=None, **kwargs):

        super(NsblContext, self).__init__(**kwargs)

        if allow_external_roles is None:
            allow_external_roles = self.allow_remote
        self.allow_external_roles = allow_external_roles

        if allow_external_tasklists is None:
            allow_external_roles = self.allow_remote
        self.allow_external_tasklists = allow_external_tasklists

        self.role_repo_paths = self.environment_paths.get("role_repo_paths", [])
        self.task_alias_paths = self.environment_paths.get("task_alias_paths", [])
        self.tasklist_search_paths = self.environment_paths.get("tasklist_search_paths", [])

        temp_paths = []
        temp_paths.extend(self.role_repo_paths)
        temp_paths.extend(self.task_alias_paths)
        self.task_aliases = calculate_task_aliases(temp_paths)
        self.available_roles = find_roles_in_repos(self.role_repo_paths)



class NsblTasklist(FrecklesTasklist):

    def __init__(self, tasklist, context=None, meta=None, vars=None):

        self.internal_roles = set()
        self.external_roles = set()
        self.modules_used = set()
        self.tasklist_files = {}
        self.children = []
        self.additional_files = {}

        super(NsblTasklist, self).__init__(tasklist, context, meta=meta, vars=vars)

    def preprocess_tasklist(self, tasklist, context, meta, vars):

        content = super(NsblTasklist, self).preprocess_tasklist(tasklist, context, meta, vars)

        # if ansible format, replace task with import_task
        log.debug("Tasklist, preprocessed: {}".format(content))

        tasklist = self.ensure_freckles_task_list_format(content)

        log.debug("Tasklist, after format check: {}".format(tasklist))
        return tasklist

    def ensure_freckles_task_list_format(self, task_list):
        """Make sure the task list is in 'freckles' format, if not, convert and add additional task file.

        Args:
            task_list (list): the task list
            env_id: the id of the environment (used to calculate the variable name)
            task_list_id: the id of the task_list inside the environment (used to calculate the variable name)
        Returns:
            tuple: tuple in the form of (final_task_list, external_files_dict)
        """

        task_list_format = get_task_list_format(task_list)
        if task_list_format == "ansible":

            if self.tasklist_raw_type == "list":
                file_name = "tasklist"
                extension = ".yml"
            else:
                file_name, extension = splitext(os.path.basename(self.tasklist_raw))

            unique_file_name = "{}_env_{}_tasklist_{}{}".format(
                file_name, self.env_id, self.tasklist_id, extension
            )
            var_name = "_{}_env_{}_tasklist_{}".format(file_name, self.env_id, self.tasklist_id)

            task_list_item_new = {
                "name": "import_tasks",
                "desc": "[importing tasks: {}".format(self.tasklist_raw),
                "task-type": TASK_LIST_TASK_TYPE,
                "task-name": "import_tasks",
                "include-type": "import_tasks",
                "tasklist_format": "ansible",
                "tasklist_var": var_name,
                "tasklist_target": unique_file_name,
                "parse_ignore": True
            }

            self.tasklist_files[unique_file_name] = {
                "var_name": var_name,
                "target_name": unique_file_name,
                "type": ADD_TYPE_TASK_LIST,
                "tasklist_format": "ansible",
                "tasklist_content": task_list
            }

            return [{"task": task_list_item_new}]
        else:
            return task_list

    def create_context(self, context_params):

        return NsblContext(**context_params)

    def expand_and_augment_tasklist(self, tasklist):

        # we assume we only have one tasklist, so this makes sure
        # frkl behaves properly
        tasklist = [tasklist]

        task_format = self.generate_nsbl_tasks_format()
        chain = [FrklProcessor(**task_format), AugmentingTaskProcessor(context=self.context)]
        f = Frkl(tasklist, chain)
        tasklist = f.process()

        for task in tasklist:

            if task.get("task", {}).pop("parse_ignore", None):
                continue

            self.fill_task_type(task)

            task_type = task["task"]["task-type"]
            task_name = task["task"]["task-name"]

            task_roles = task["task"].get("task-roles", [])
            for tr in task_roles:
                if tr not in self.context.available_roles.keys():
                    if self.context.allow_external_roles:
                        self.external_roles.add(tr)
                    else:
                        raise NsblException(
                            "Role '{}' not available in local role repos ({}), and external roles download not allowed.".format(
                                task_name, self.context.role_repo_paths
                            )
                        )
                else:
                    self.internal_roles.add(task_name)

        self.parse_child_tasklists()

        return tasklist

    def parse_child_tasklists(self):

         # parsing other tasklists
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
                    m = copy.deepcopy(self.meta)
                    m["tasklist_id"] = tl_id
                    tl = NsblTasklist(
                        details["tasklist_content"],
                        nsbl_context=self.context,
                        meta=m,
                    )
                    details["tasklist_format"] == "freckles"
                except (Exception) as e:
                    details["tasklist_format"] == "ansible"
                    continue
            else:
                m = copy.deepcopy(self.meta)
                m["tasklist_id"] = tl_id
                tl = NsblTasklist(
                    details["tasklist_content"],
                    context=self.context,
                    meta=m
                )

            self.children.append(tl)
            dict_merge(self.additional_files, tl.additional_files, copy_dct=False)
            for child in tl.children:
                self.children.append(child)
                dict_merge(
                    self.additional_files, child.additional_files, copy_dct=False
                )

            details["tasklist_rendered"] = tl.render_tasklist()
            # print(details["tasklist_rendered"])
            counter = counter + 1

        # adding tasklists to additional files
        dict_merge(self.additional_files, self.tasklist_files, copy_dct=False)

        # adding roles to additional files
        for role in self.internal_roles:

            role_path = self.nsbl_context.available_roles.get(role)
            self.additional_files[role_path] = {
                "type": ADD_TYPE_ROLE,
                "target_name": role,
            }


    def fill_task_type(self, task_item):
        """Utility method to guess the type of a task and fill in all necessary properties.

        Args:
            task_item (dict): the task item
        """

        if task_item["task"].pop("task_ignore", False):
            return task_item

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
            role_available = task_name in self.context.available_roles
            if not role_available:
                if not self.context.allow_external_roles:
                    raise NsblException(
                        "Role '{}' not available and exernal roles not allowed".format(
                            task_name
                        )
                    )
                else:
                    task_item["task"]["role-type"] = "external"
                    self.external_roles.add(task_name)
            else:
                task_item["task"]["role-type"] = "internal"
                self.internal_roles.add(task_name)

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
                not os.path.isabs(task_list_file) and is_url_or_abbrev(self.meta["tasklist_parent"])
            ):
                if self.context.allow_external_tasklists:
                    raise NsblException(
                        "Remote task lists not allowed for this environment."
                    )
                if is_url_or_abbrev(task_list_file):
                    url = task_list_file
                elif not os.path.isabs(task_list_file):
                    url = os.path.join(self.meta["tasklist_parent"], task_list_file)
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
                    if self.meta["tasklist_parent"]:
                        search_paths.append(self.meta["tasklist_parent"])
                    search_paths.extend(self.context.tasklist_search_paths)

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
                file_name, self.meta["env_id"], self.meta["tasklist_id"], extension
            )
            var_name = "_{}_env_{}_tasklist_{}".format(file_name, self.meta["env_id"], self.meta["tasklist_id"])

            self.tasklist_files[file_path] = {
                "var_name": var_name,
                "target_name": unique_file_name,
                "type": ADD_TYPE_TASK_LIST,
                "tasklist_format": tf_format,
                "tasklist_content": content
            }

            task_item["task"]["tasklist_var"] = var_name
            task_item["task"]["tasklist_target"] = unique_file_name

            log.debug("tasklist task-item: {}".format(task_item))
        else:
            task_item["task"]["task-type"] = MODULE_TASK_TYPE
            log.debug("module task-item: {}".format(task_item))
            self.modules_used.add(task_name)

    def generate_nsbl_tasks_format(self,
        tasks_format=DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT):
        """Utility method to populate the KEY_MOVE_MAP key for the tasks """

        result = copy.deepcopy(DEFAULT_NSBL_TASKS_BOOTSTRAP_FORMAT)
        for alias, task_desc in self.context.task_aliases.items():

            if DEFAULT_KEY_KEY in task_desc["task"].keys():
                # TODO: check for duplicate keys?
                result[KEY_MOVE_MAP_NAME][task_desc["task"]["name"]] = "vars/{}".format(
                task_desc["task"][DEFAULT_KEY_KEY]
                )

        return result

    def render_tasklist(self):
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


