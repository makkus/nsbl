import os
import pprint

from nsbl.tasklist import *
import pytest

from ruamel.yaml import YAML
from frutils import *
from nsbl.defaults import *

from nsbl.role_utils import *
CWD = os.path.dirname(os.path.realpath(__file__))
PATH_RR = os.path.join(CWD, "role_repos")

yaml = YAML()
yaml.default_flow_style = False

REPO_LIST = [
    (os.path.join(PATH_RR, "example_roles"), {"ansiblebit.oracle-java": os.path.join(PATH_RR, "example_roles", "languages/java/ansiblebit.oracle-java")})
]

@pytest.mark.parametrize("repo_path, expected", REPO_LIST)
def test_find_roles_in_repo(repo_path, expected):

    result = find_roles_in_repo(repo_path)

    assert result == expected
