import os
import pprint

from nsbl.tasklist import *
from nsbl.tasklist_utils import *
import pytest

from ruamel.yaml import YAML
from frutils import *
from nsbl.task_alias_utils import *

CWD = os.path.dirname(os.path.realpath(__file__))
PATH_TL = os.path.join(CWD, "task_lists")
PATH_RR = os.path.join(CWD, "role_repos")
PATH_IN = os.path.join(CWD, "inventory")
PATH_TA = os.path.join(CWD, "task_aliases")

yaml = YAML()
yaml.default_flow_style = False

TLREPO_PATHS = [(PATH_TL, ["simple1.tsks"])]
