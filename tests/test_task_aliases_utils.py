import os
import pprint

from nsbl.tasklist import *
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

REPO_PATHS = [
    (os.path.join(PATH_TA, "fine"), ["install-oracle-java", "install-oracle-java-8", "install-oracle-java-9", "install-oracle-java-10"]),
]

@pytest.mark.parametrize("path, expected", REPO_PATHS)
def test_task_alias_single_repo(path, expected):
    repo = TaskAliasLucifier()
    repo.overlay_dictlet(path, add_dictlet=True)
    result = repo.process().values()
    print(result[0].keys())
    assert sorted(list(result[0].keys())) == sorted(expected)

REPO_PATHS_DUP = [
    (os.path.join(PATH_TA, "duplicate_alias"))
]

@pytest.mark.parametrize("path", REPO_PATHS_DUP)
def test_task_alias_single_repo_duplicate_alias(path):

    repo = TaskAliasLucifier()
    repo.overlay_dictlet(path, add_dictlet=True)
    with pytest.raises(NsblException):
        repo.process().values()


REPO_PATHS_MULTI = [
    (os.path.join(PATH_TA, "fine"), ["install-oracle-java", "install-oracle-java-8", "install-oracle-java-9", "install-oracle-java-10"]),
]

@pytest.mark.parametrize("path, expected", REPO_PATHS_MULTI)
def test_task_alias_single_repo(paths, expected):
    repo = TaskAliasLucifier()
    for path in paths:
        repo.overlay_dictlet(path, add_dictlet=True)
    result = repo.process().values()
    print(result[0].keys())
    assert sorted(list(result[0].keys())) == sorted(expected)

