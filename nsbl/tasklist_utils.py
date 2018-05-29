# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

from .defaults import *
import logging

log = logging.getLogger("nsbl")

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
        if "meta" in item.keys():
            log.debug(
                "task item '{}' has 'meta' key, determining this is a 'freckles' task list".format(
                    item["meta"].get("name", item)
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
    return None
