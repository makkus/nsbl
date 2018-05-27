# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

import fnmatch
import logging
import os
import re
import yaml

from frutils import DEFAULT_EXCLUDE_DIRS
from frkl.utils import expand_string_to_git_details
from six import string_types

from .defaults import *
from .exceptions import NsblException

log = logging.getLogger("nsbl")

ROLE_CACHE = {}
ROLE_MARKER_FOLDERNAME = "meta"
ROLE_META_FILENAME = "main.yml"

ABBREV_VERBOSE = True
ABBREV_WARN = True

ANSIBLE_FORMAT_MARKER_KEYS = set(
    [
        "when",
        "become",
        "name",
        "register",
        "with_items",
        "with_dict",
        "loop",
        "with_list",
        "until",
        "retries",
        "delay",
        "changed_when",
        "loop_control",
        "block",
        "become_user",
        "rescue",
        "always",
        "notify",
        "ignore_errors",
        "failed_when",
        "changed_when",
    ]
)


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


def get_role_details_in_repo(role_repo):

    roles = find_roles_in_repo(role_repo)

    result = {}

    for role, path in roles.items():
        result[role] = {}
        result[role]["path"] = path
        result[role]["repo"] = role_repo
        readme = os.path.join(path, "README.md")
        if not os.path.exists(readme):
            result[role]["readme"] = "n/a"
        else:
            with open(readme, "r") as f:
                content = f.read()
                result[role]["readme"] = content

        defaults_path = os.path.join(path, "defaults")

        if not os.path.exists(defaults_path):
            result[role]["defaults"] = {}
        else:
            d_temp = {}
            for defaults_file in os.listdir(defaults_path):
                temp = os.path.join(defaults_path, defaults_file)
                with open(temp, "r") as f:
                    content = f.read()
                    d_temp[defaults_file] = yaml.safe_load(content)

            result[role]["defaults"] = d_temp

        meta_path = os.path.join(path, "meta", "main.yml")
        if not os.path.exists(meta_path):
            result[role]["meta"] = {}
        else:
            with open(meta_path, "r") as f:
                metadata = yaml.safe_load(f)
                if not metadata:
                    metadata = {}
            result[role]["meta"] = metadata

    return result


def check_role_desc(role_name, role_repos=[]):
    """Utility function to return the local path of a provided role name.

    If the input is a path, and that path exists on the local system, that path is returned.
    Otherwise all role repos will be checked whether they contain a role with the provided name, and if that
    is the case, that local path will be returned.

    Args:
      role_name: the path to or name of the role
      role_repos: all role repositories to check
    Returns:
    dict: a dictionary with the 'url' key being the found path
    """

    if isinstance(role_name, string_types):

        version = None
        src = None
        if os.path.exists(role_name):
            src = role_name
            name = os.path.basename(role_name)
            role_type = LOCAL_ROLE_TYPE
        else:
            # reverse list, so last repos have highest priority
            for repo in reversed(role_repos):
                _local_repo_roles = find_roles_in_repo(repo)
                path = _local_repo_roles.get(role_name, None)
                # path = os.path.join(os.path.expanduser(repo), role_name)

                if path and os.path.exists(path):
                    src = path
                    name = role_name
                    role_type = LOCAL_ROLE_TYPE
                    break

            if not src:
                src = role_name
                role_type = REMOTE_ROLE_TYPE
                if "." in role_name and "/" in role_name:
                    name = role_name.split("/")[-1]
                else:
                    # name = role_name.split(".")[-1]
                    name = src

    elif not isinstance(role_name, dict):
        raise NsblException(
            "Type for role needs to be either string or dict: {}".format(role_name)
        )
    else:
        name = role_name.get("name", None)
        src = role_name.get("src", None)
        version = role_name.get("version", None)

        if not name and not src:
            raise NsblException(
                "Role doesn't specify 'name' nor 'src', can't figure out what to do: {}".format(
                    role_name
                )
            )
        elif not name:
            if os.path.exists(src):
                name = os.path.basename(src)
                role_type = LOCAL_ROLE_TYPE
            else:
                role_type = REMOTE_ROLE_TYPE
                if "." in src and "/" in src:
                    name = src.split("/")[-1]
                else:
                    # name = src.split(".")[-1]
                    name = src
        elif not src:
            if os.path.exists(name):
                src = name
                name = os.path.basename(src)
                role_type = LOCAL_ROLE_TYPE
            else:
                role_type = REMOTE_ROLE_TYPE
                src = name
                if "." in src and "/" in src:
                    name = src.split("/")[-1]
                else:
                    # name = src.split(".")[-1]
                    name = src
        else:
            if os.path.exists(src):
                role_type = LOCAL_ROLE_TYPE
            else:
                role_type = REMOTE_ROLE_TYPE

    if src.startswith(DYN_ROLE_TYPE):
        role_type = DYN_ROLE_TYPE

    result = {"name": name, "src": src, "type": role_type}
    if version:
        result["version"] = version

    return result


def _add_role_check_duplicates(all_roles, new_role):
    """Adds a new role only if it isn't already in the list of all roles.

    Throws an exception if two roles with the same name but different details exist.

    Args:
      all_roles (list): all current roles
      new_role (dict): new role to add
    """

    new_role_name = new_role["name"]
    new_role_src = new_role["src"]
    new_role_version = new_role.get("version", None)

    match = False
    for role in all_roles:
        role_name = role["name"]
        src = role["src"]
        version = role.get("version")

        if new_role_name != role_name:
            continue

        match = True
        if new_role_src != src:
            raise NsblException(
                "Two roles with the same name ('{}') but different 'src' details: {} <-> {}".format(
                    role_name, new_role, role
                )
            )
        if new_role_version != version:
            if new_role_version == None:
                continue
            elif version == None:
                role["version"] = new_role_version
            else:
                raise NsblException(
                    "Two roles with the same name ('{}') but different 'version' details: {} <-> {}".format(
                        role_name, new_role_version, version
                    )
                )

    if not match:
        all_roles.append(new_role)


def add_roles(all_roles, role_obj, role_repos=[]):
    """ TODO: desc

    Args:
      all_roles (list): a list of all roles
      role_obj (object): a string (role_name) or dict (roles) or list (role_names/-details)
      role_repos (list): list of local role repos to check

    Returns:
    dict: merged roles
    """

    if isinstance(role_obj, dict):
        if "src" not in role_obj.keys():
            if "name" in role_obj.keys():
                temp = check_role_desc(role_obj, role_repos)
                _add_role_check_duplicates(all_roles, temp)
            else:
                # raise NsblException("Neither 'src' nor 'name' keys in role description, can't parse: {}".format(role_obj))
                for role_name, role_details in role_obj.items():
                    if isinstance(role_details, dict):
                        if "name" in role_details.keys():
                            raise NsblException(
                                "Role details can't contain 'name' key, name already provided as key of the parent dict: {}".format(
                                    role_obj
                                )
                            )
                        role_details["name"] = role_name
                        temp = check_role_desc(role_details, role_repos)
                        _add_role_check_duplicates(all_roles, temp)
                    elif isinstance(role_details, string_types):
                        temp = check_role_desc(
                            {"src": role_details, "name": role_name}, role_repos
                        )
                        _add_role_check_duplicates(all_roles, temp)
                    else:
                        raise NsblException(
                            "Role description needs to be either string or dict: {}".format(
                                role_details
                            )
                        )
        else:
            temp = check_role_desc(role_obj, role_repos)
            _add_role_check_duplicates(all_roles, temp)
    elif isinstance(role_obj, string_types):
        temp = check_role_desc(role_obj, role_repos)
        _add_role_check_duplicates(all_roles, temp)
    elif isinstance(role_obj, (list, tuple)):
        for role_obj_child in role_obj:
            add_roles(all_roles, role_obj_child, role_repos)
    else:
        raise NsblException(
            "Role description needs to be either a list of strings or a dict. Value '{}' is not valid.".format(
                role_obj
            )
        )


def calculate_local_repo_path(repo_url, branch=None):

    repo_name = repo_url.split(os.sep)[-1]

    if repo_name.endswith(".git"):
        repo_name = repo_name[0:-4]

    # clean_string = re.sub('[^A-Za-z0-9]+', os.sep, repo_url) + os.sep + repo_name
    REPL_CHARS = "[^_\-A-Za-z0-9\.]+"

    if branch is None:
        branch = "default"

    clean_string = (
        re.sub(REPL_CHARS, os.sep, repo_url) + os.sep + branch + os.sep + repo_name
    )

    return clean_string


# DEFAULT_LOCAL_REPO_PATH_BASE, DEFAULT_REPOS, DEFAULT_ABBREVIATIONS
# def get_all_roles_in_repos(repos, repo_path_base, default_repo_dict, default_abbrevs):
#     result = []
#     repos = get_local_repos(repos, "roles", repo_path_base, default_repo_dict, default_abbrevs)

#     return find_all_roles_in_repos(repos)

# def find_all_roles_in_repos(repos):

#     result = []
#     for repo in repos:
#         roles = find_roles_in_repo(repo)
#         result.extend(roles)

#     return result


def get_local_repos(repo_names, repo_path_base, default_repo_dict, default_abbrevs):
    result = []
    for repo_name in repo_names:

        repo = default_repo_dict.get(repo_name, None)

        if not repo:

            if not os.path.exists(repo_name):
                repo_details = expand_string_to_git_details(repo_name, default_abbrevs)
                repo_url = repo_details["url"]
                repo_branch = repo_details.get("branch", None)
                relative_repo_path = calculate_local_repo_path(repo_url, repo_branch)
                repo_path = os.path.join(repo_path_base, relative_repo_path)
            else:
                repo_path = repo_name

            result.append(repo_path)
        else:
            result.append(repo["path"])

    return result


def get_internal_role_path(role, role_repos=[]):
    """Resolves the local path to the (internal) role with the provided name.

    Args:
      role (str): string or dict of the role, can be either a name of a subdirectory in one of the role_repos, or a path
      role_repos (list): role repos to check whether one of them contains the role name as first level directory
    """

    if isinstance(role, string_types):
        url = role
    elif isinstance(role, dict):
        url = role["src"]
    else:
        raise NsblException(
            "Type '{}' not supported for role description: {}".format(type(role), role)
        )

    if os.path.exists(url):
        return url

    role_desc = check_role_desc(role, role_repos)

    if role_desc["type"] == "local":
        return role_desc["src"]

    role_desc = check_role_desc(role.lower(), role_repos)
    if role_desc["type"] == "local":
        return role_desc["src"]

    return False


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
            if keys & ANSIBLE_FORMAT_MARKER_KEYS:
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
