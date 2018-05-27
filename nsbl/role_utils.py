# -*- coding: utf-8 -*-

# python 3 compatibility
from __future__ import absolute_import, division, print_function, unicode_literals

import fnmatch
import logging
import re
from collections import OrderedDict

import yaml
from cookiecutter.main import cookiecutter
from jinja2 import Environment, PackageLoader
from frkl.utils import expand_string_to_git_details, expand_string_to_git_repo

from .defaults import *
from .exceptions import NsblException

from .utils import *

from frkl.processors import (
    UrlAbbrevProcessor,
    EnsurePythonObjectProcessor,
    EnsureUrlProcessor,
    ConfigProcessor,
)
from frkl.callbacks import FrklCallback
from frutils import dict_merge

from frutils.defaults import DEFAULT_EXCLUDE_DIRS

log = logging.getLogger("nsbl")

ROLE_CACHE = {}
ROLE_MARKER_FOLDERNAME = "meta"
ROLE_META_FILENAME = "main.yml"

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
