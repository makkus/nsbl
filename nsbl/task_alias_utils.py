# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

import copy
import logging
import os
from collections import OrderedDict

from ruamel.yaml.comments import CommentedMap
from six import string_types

from lucify.finders import FolderOrFileFinder
from lucify.lucify import Lucifier
from lucify.readers import YamlFolderReader
from nsbl.exceptions import NsblException

log = logging.getLogger("nsbl")


class TaskAliasFolderReader(YamlFolderReader):

    def __init__(self, **kwargs):

        super(TaskAliasFolderReader, self).__init__(
            meta_file_name=None, use_relative_paths_as_keys=False, **kwargs
        )

    def is_usable_file(self, path):
        """Returns all files called 'task-aliases.yml'
        """
        f = os.path.basename(path)
        result = f == "task-aliases.yml"

        return result

    def process_content(
        self, content, current_metadata, luci_metadata, luci_metadata_key_name=None
    ):

        result = CommentedMap()
        for path, metadata in content.items():

            if not isinstance(metadata, (dict, OrderedDict, CommentedMap)):
                raise Exception("tasks-alias files need to be a dictionary")

            result[path] = metadata

        return result


def assemble_task_aliases(paths):
    """Helper method to assemble one task-alias dictionary from a list of paths.

    Check :class:`TaskAliasLucifier` for more details.

    Args:
        paths (list): a list of paths to directories or files
    Returns:
        dict: the (merged) task aliases
    """

    tl = TaskAliasLucifier()
    for p in paths:
        tl.overlay_dictlet(p, add_dictlet=True)
    task_aliases = tl.process()

    return task_aliases


def calculate_task_aliases(
    task_alias_files_or_repos, add_upper_case_versions=True
):
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
            "task_descs needs to be string or list: '{}'".format(
                task_alias_files_or_repos
            )
        )

    task_aliases = assemble_task_aliases(task_alias_files_or_repos)

    if add_upper_case_versions:

        ta_copy = copy.deepcopy(task_aliases)

        for alias, md in ta_copy.items():

            task_become = copy.deepcopy(md)

            task_become["task"]["name"] = md["task"]["name"].upper()
            task_become["task"]["become"] = True
            alias_become = alias.upper()
            task_aliases[alias_become] = task_become

    return task_aliases


class TaskAliasLucifier(Lucifier):
    """Class to read and merge task aliases into a single dictionary.

    This can read both directories and files. If you add a directory dictlet,
    it will find and read all files called 'task-aliases.yml' recursively under
    that folder. It is not allowed to for multiple 'task-aliases.yml' files to contain
    the same alias key (with different values) as that would result in unpredictable
    behaviour depending on which file is read first.

    If the path added is a file, it can be named anything, but needs to be in yaml
    format.

    In both cases, the yaml files need to contain a single dictionary with the alias as key,
    and a metadata dict as value.
    """

    def __init__(self, **kwargs):
        super(TaskAliasLucifier, self).__init__("repo", **kwargs)

        self.reader = TaskAliasFolderReader()
        self.finder = FolderOrFileFinder()

        self.pkg_descs = CommentedMap()

    def get_default_dictlet_reader(self):

        return self.reader

    def get_default_dictlet_finder(self):

        return self.finder

    def process_dictlet(self, metadata, dictlet_details=None):

        all_aliases = OrderedDict()
        for path, aliases in metadata.items():
            for alias, md in aliases.items():
                if alias in all_aliases.keys():
                    raise NsblException(
                        "Duplicate alias '{}' in: {}".format(alias, path)
                    )

                all_aliases[alias] = md

        return all_aliases

    def process(self):
        """Processes all dictlets that were added to this Lucifier, one after the other.
        """

        result = CommentedMap()
        for dictlet_name, details in self.dictlets.items():
            p_r = self.process_dictlet(details["metadata"], dictlet_details=details)
            for alias, md in p_r.items():

                if alias in result.keys() and md != result[alias]:
                    log.warn(
                        "Duplicate alias '{}' in task aliases, overwriting with value from: {}".format(
                            alias, dictlet_name
                        )
                    )
                if "name" not in md["task"].keys():
                    md["task"]["name"] = alias
                result[alias] = md

        return result
