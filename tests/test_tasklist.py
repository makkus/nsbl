import os
import pprint

from nsbl.tasklist import *
import pytest

from ruamel.yaml import YAML
from frutils import *
from nsbl.defaults import *
CWD = os.path.dirname(os.path.realpath(__file__))
PATH_TL = os.path.join(CWD, "task_lists")

yaml = YAML()
yaml.default_flow_style = False

TL1 = [{"meta": {"name": "apt", "become": True, "type": "ansible-module", "desc": "installing zile"}, "var": {"name": "zile"}}]
TL2 = [{"name": "installing zile", "apt": {"name": "zile"}, "become": True}]
TL2_R = get_import_task_item("task_list_name")

FORMAT_TASK_LISTS = [
    (TL1, TL1, []),
    (TL2, [TL2_R], TL2)
]

@pytest.mark.parametrize("task_list, expected_task_list, expected_task_list_content", FORMAT_TASK_LISTS)
def test_task_list_format(tmpdir, task_list, expected_task_list, expected_task_list_content):

    tf_file = tmpdir.join("task_list_name")

    task_list_new, task_list_file = ensure_task_list_format(task_list, str(tf_file))

    assert task_list_new == expected_task_list
    if task_list_file is not None:
        task_list_file_content = yaml.load(tf_file.open())
        task_list_file_content[0] = special_dict_to_dict(task_list_file_content[0])
        assert task_list_file_content == expected_task_list_content
        tf_file.remove(ignore_errors=False)


ETL1= [{"apt": {"name": "zile"}}]
ETL1_R = [{'meta': {'name': 'apt', 'task-name': 'apt'}, 'vars': {'name': 'zile'}}]
ETL2= [{"apt": {"meta": {"become": True}, "vars": {"name": "zile"}}}]
ETL2_R = [{'meta': {'name': 'apt', 'task-name': 'apt', "become": True}, 'vars': {'name': 'zile'}}]
EXPAND_LISTS = [
    (ETL1, ETL1_R),
    (ETL2, ETL2_R)
]

OTL3 = ["install_zile"]
OTL3_TA = os.path.join(PATH_TL, "task-aliases-1.yml")
OTL3_R = [{'meta': {'task-name': 'apt', 'name': 'install_zile', "become": True}, 'vars': {'name': 'zile'}}]

AUGMENT_LISTS = [
    (OTL3, [], OTL3_TA, OTL3_R),
    (ETL1, [], None, ETL1_R),
    (ETL2, [], None, ETL2_R)
]
@pytest.mark.parametrize("task_list, role_repos, task_alias_files, expected", AUGMENT_LISTS)
def test_augment_task_list(task_list, role_repos, task_alias_files, expected):

    role_repos, task_aliases = get_default_role_repos_and_task_aliases(
              role_repos, task_alias_files)
    result = augment_and_expand_task_list(task_list, role_repos, task_aliases)

    assert result == expected


@pytest.mark.parametrize("task_list, role_repos, task_alias_files, expected", AUGMENT_LISTS)
def test_tasklist_class_init(task_list, role_repos, task_alias_files, expected):

    tl = TaskList(task_list, external_files=None, run_metadata={"role_repos": role_repos, "task_alias_files": task_alias_files})

    assert tl.task_list == expected
