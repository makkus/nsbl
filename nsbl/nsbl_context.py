# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

from frutils import dict_merge
from .task_alias_utils import assemble_task_aliases

import logging
from six import string_types
from .defaults import *
from frutils.defaults import DEFAULT_EXCLUDE_DIRS
import fnmatch
from .exceptions import NsblException

log = logging.getLogger("nsbl")

ROLE_CACHE = {}
ROLE_MARKER_FOLDERNAME = "meta"
ROLE_META_FILENAME = "main.yml"



def find_roles_in_repos(role_repos):

    if isinstance(role_repos, string_types):
        role_repos = [role_repos]

    result = {}
    for rr in role_repos:
        roles = find_roles_in_repo(rr)
        dict_merge(result, roles, copy_dct=False)

    return result


def find_roles_in_repo(role_repo):
    """Utility function to find all roles in a role_repo.

    Args:
      role_repo: the path to the role repo

    Returns:
    dict: a dictionary with the name of the role as key, and the path to the role as value
    """

    if role_repo in ROLE_CACHE.keys():
        return ROLE_CACHE[role_repo]

    result = {}
    try:

        for root, dirnames, filenames in os.walk(
            os.path.realpath(role_repo), topdown=True, followlinks=True
        ):

            dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE_DIRS]
            # check for meta folders
            for dirname in fnmatch.filter(dirnames, ROLE_MARKER_FOLDERNAME):

                meta_file = os.path.realpath(
                    os.path.join(root, dirname, ROLE_META_FILENAME)
                )
                if not os.path.exists(meta_file):
                    continue

                role_folder = root
                role_name = os.path.basename(role_folder)
                result[role_name] = role_folder

    except (UnicodeDecodeError) as e:
        print(
            " X one or more filenames under '{}' can't be decoded, ignoring. This can cause problems later. ".format(
                root
            )
        )

    ROLE_CACHE[role_repo] = result

    return result



def calculate_task_list_repos(task_list_paths):
    """Utility method to calculate which task-list repos to use.

    task-list repos are folders containing freckles or ansible task lists.
    """

    if not task_list_paths:
        task_list_paths = []

    if isinstance(task_list_paths, string_types):
        task_list_paths = [task_list_paths]

    task_list_paths[:] = [os.path.realpath(os.path.expanduser(tlp)) for tlp in task_list_paths]

    task_list_paths[:] = [tlp for tlp in task_list_paths if os.path.exists(tlp) and os.path.isdir(os.path.realpath(tlp))]
    log.debug("final task-list-paths: {}".format(task_list_paths))

    return task_list_paths


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

    role_repos[:] = [os.path.realpath(os.path.expanduser(rr)) for rr in role_repos]

    role_repos[:] = [rr for rr in role_repos if os.path.exists(rr) and os.path.isdir(os.path.realpath(rr))]
    log.debug("final role_repos: {}".format(role_repos))

    return role_repos


def calculate_task_aliases(task_alias_files_or_repos, add_upper_case_versions=True):
    """Utility method to calculate which task descriptions to use.

    Task descriptions are yaml files that translate task-names in a task config
    into roles or ansible tasks, optionally with extra default parameters.

    If additional role_repos are provided, we will check whether each of them
    contains a file with the value of TASK_DESC_DEFAULT_FILENAME. If so, those
    will be added to the beginning of the resulting list.

    Args:
      task_alias_files_or_repos (list): a string or list of strings of local files or repos containing 'task-aliases.yml' files
      add_upper_case_versions (bool): if true, will add an upper-case version of every task desc that includes a meta/become = true entry

    Returns:
      list: a list of dicts of all task description configs to be used

    """

    if not task_alias_files_or_repos:
        return {}

    if isinstance(task_alias_files_or_repos, string_types):
        task_alias_files_or_repos = [task_alias_files_or_repos]
    elif not isinstance(task_alias_files_or_repos, (list, tuple)):
        raise Exception(
            "task_descs needs to be string or list: '{}'".format(task_alias_files_or_repos)
        )

    task_aliases = assemble_task_aliases(task_alias_files_or_repos)
    import pprint
    pprint.pprint(task_aliases)
    if add_upper_case_versions:

        ta_copy = copy.deepcopy(task_aliases)

        for alias, md in ta_copy.items():

            task_become = copy.deepcopy(md)

            task_become["task"]["name"] = md["task"]["name"].upper()
            task_become["task"]["become"] = True
            alias_become = alias.upper()
            task_aliases[alias_become] = task_become

    return task_aliases


class NsblContext(object):

    """Class to hold information about available roles, task-lists and task-aliases."""

    def __init__(self, role_repo_paths=None, task_list_paths=None, task_alias_paths=None):

        self.add_uppercase_task_descs = True

        if role_repo_paths is None:
            role_repo_paths = []

        if task_list_paths is None:
            task_list_paths = []
        if isinstance(task_list_paths, string_types):
            task_list_paths = [task_list_paths]

        if task_alias_paths is None:
            task_alias_paths = []
        if isinstance(task_alias_paths, string_types):
            task_alias_paths = [task_alias_paths]

        self.task_list_repo_paths = calculate_task_list_repos(task_list_paths)
        self.role_repo_paths = calculate_role_repos(role_repo_paths)

        self.task_aliases = calculate_task_aliases(self.role_repo_paths + task_alias_paths)
        self.available_roles =  find_roles_in_repos(self.role_repo_paths)

