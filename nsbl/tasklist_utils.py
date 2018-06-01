# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

from six import string_types
import logging

import os
from collections import OrderedDict

from ruamel.yaml.comments import CommentedMap

from frutils import StringYAML

from lucify.finders import FolderOrFileFinder
from lucify.lucify import Lucifier
from lucify.readers import YamlFolderReader
from nsbl.exceptions import NsblException
from frkl import load_object_from_url_or_path
from .defaults import *

log = logging.getLogger("nsbl")

yaml = StringYAML()
yaml.default_flow_style = False



def get_tasklist_file_format(path):

    if not isinstance(path, string_types):
        raise NsblException("tasklist file needs to be string: {}".format(path))

    tasklist = load_object_from_url_or_path(path)
    return get_task_list_format(tasklist), tasklist


def get_task_list_format(task_list):
    """This is a not quite 100% method to check whether a task list is in ansbile format, or freckle.
    """

    for item in task_list:

        if isinstance(item, string_types):
            log.debug(
                "task item '{}' is string, determining this is a 'freckles' task list".format(
                    item
                )
            )
            return "freckles"
        elif isinstance(item, dict):
            keys = set(item.keys())
            if keys & set(ANSIBLE_TASK_KEYWORDS):
                log.debug(
                    "task item keys ({}) contain at least one known Ansible keyword , determining this is 'ansible' task list format".format(
                        keys
                    )
                )
                return "ansible"
        else:
            raise Exception("Not a valid task-list item: {}".format(item))

    # TODO: log outupt
    # could check for 'meta' key above, but 'meta' can be a keyword in ansible too,
    # so figured I check for everything else first
    for item in task_list:
        if "task" in item.keys():
            log.debug(
                "task item '{}' has 'task' key, determining this is a 'freckles' task list".format(
                    item["task"].get("name", item)
                )
            )
            return "freckles"
        for key in item.keys():
            if key.isupper():
                log.debug(
                    "task item key '{}' is all uppercase, determining this is a 'freckles' task list".format(
                        key
                    )
                )
                return "freckles"
    return "unknown"

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


