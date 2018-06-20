import os
import pprint

import pytest

from ruamel.yaml import YAML

CWD = os.path.dirname(os.path.realpath(__file__))
PATH_TL = os.path.join(CWD, "task_lists")
PATH_RR = os.path.join(CWD, "role_repos")
PATH_IN = os.path.join(CWD, "inventory")
PATH_TA = os.path.join(CWD, "task_aliases")

yaml = YAML()
yaml.default_flow_style = False

TLREPO_PATHS = [(PATH_TL, ["simple1.tsks"])]
