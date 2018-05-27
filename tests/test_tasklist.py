import os
import pprint

from nsbl.tasklist import *
import pytest

from ruamel.yaml import YAML
from frutils import *
from nsbl.defaults import *

CWD = os.path.dirname(os.path.realpath(__file__))
PATH_TL = os.path.join(CWD, "task_lists")
PATH_RR = os.path.join(CWD, "role_repos")

yaml = YAML()
yaml.default_flow_style = False

TL1 = [
    {
        "meta": {
            "name": "apt",
            "become": True,
            "type": "ansible-module",
            "desc": "installing zile",
        },
        "var": {"name": "zile"},
    }
]
TL2 = [{"name": "installing zile", "apt": {"name": "zile"}, "become": True}]
TL2_R = get_import_task_item("task_list_name")

FORMAT_TASK_LISTS = [(TL1, TL1, []), (TL2, [TL2_R], TL2)]


@pytest.mark.parametrize(
    "task_list, expected_task_list, expected_task_list_content", FORMAT_TASK_LISTS
)
def test_task_list_format(
    tmpdir, task_list, expected_task_list, expected_task_list_content
):

    tf_file = tmpdir.join("task_list_name")

    task_list_new, task_list_file = ensure_task_list_format(task_list, str(tf_file))

    assert task_list_new == expected_task_list
    if task_list_file is not None:
        task_list_file_content = yaml.load(tf_file.open())
        task_list_file_content[0] = special_dict_to_dict(task_list_file_content[0])
        assert task_list_file_content == expected_task_list_content
        tf_file.remove(ignore_errors=False)


ETL1 = [{"apt": {"name": "zile"}}]
ETL1_R = [{"meta": {"name": "apt", "task-name": "apt"}, "vars": {"name": "zile"}}]
ETL2 = [{"apt": {"meta": {"become": True}, "vars": {"name": "zile"}}}]
ETL2_R = [
    {
        "meta": {"name": "apt", "task-name": "apt", "become": True},
        "vars": {"name": "zile"},
    }
]
EXPAND_LISTS = [(ETL1, ETL1_R), (ETL2, ETL2_R)]

OTL1 = ["apt"]
OTL1_R = [{"meta": {"name": "apt", "task-name": "apt", "vars": {}}}]
OTL2 = ["APT"]
OTL2_R = [{"meta": {"name": "APT", "task-name": "apt", "become": True}, "vars": {}}]
OTL3 = ["install_zile"]
OTL3_TA = os.path.join(PATH_TL, "task-aliases-1.yml")
OTL3_R = [
    {
        "meta": {"task-name": "apt", "name": "install_zile", "become": True},
        "vars": {"name": "zile"},
    }
]
OTL3_b = ["INSTALL_ZILE"]
OTL3_b_R = [
    {
        "meta": {"task-name": "apt", "name": "INSTALL_ZILE", "become": True},
        "vars": {"name": "zile"},
    }
]
OTL4 = ["install_zile"]
OTL4_TA = os.path.join(PATH_TL, "task-aliases-2.yml")
OTL4_R = [
    {"meta": {"task-name": "apt", "name": "install_zile"}, "vars": {"name": "zile"}}
]
OTL4_b = ["INSTALL_ZILE"]
OTL4_b_R = [
    {
        "meta": {"task-name": "apt", "name": "INSTALL_ZILE", "become": True},
        "vars": {"name": "zile"},
    }
]
AUGMENT_LISTS = [
    (OTL2, [], None, OTL2_R),
    (OTL3, [], OTL3_TA, OTL3_R),
    (OTL3_b, [], OTL3_TA, OTL3_b_R),
    (ETL1, [], None, ETL1_R),
    (ETL2, [], None, ETL2_R),
    (OTL4, [], OTL4_TA, OTL4_R),
    (OTL4_b, [], OTL4_TA, OTL4_b_R),
]


@pytest.mark.parametrize(
    "task_list, role_repos, task_alias_files, expected", AUGMENT_LISTS
)
def test_augment_task_list(task_list, role_repos, task_alias_files, expected):

    role_repos, task_aliases = get_default_role_repos_and_task_aliases(
        role_repos, task_alias_files
    )
    result = augment_and_expand_task_list(task_list, role_repos, task_aliases)

    assert result == expected


TTL1 = [
    {
        "meta": {
            "name": "ansiblebit.oracle-java",
            "task-name": "ansiblebit.oracle-java",
            "task-type": "ansible-role",
        }
    }
]
TTL1_R = [
    {
        "meta": {
            "name": "ansiblebit.oracle-java",
            "task-name": "ansiblebit.oracle-java",
            "task-type": "ansible-role",
        }
    }
]
TTL2 = [
    {
        "meta": {
            "name": "ansiblebit.oracle-java2",
            "task-name": "ansiblebit.oracle-java2",
            "task-type": "ansible-role",
        }
    }
]
TTL2_R = [
    {
        "meta": {
            "name": "ansiblebit.oracle-java2",
            "task-name": "ansiblebit.oracle-java2",
            "task-type": "ansible-role",
        }
    }
]
TTL3 = [{"meta": {"name": "apt-task", "task-name": "apt"}}]
TTL3_R = [
    {"meta": {"name": "apt-task", "task-name": "apt", "task-type": "ansible-module"}}
]

TASK_TYPE_LIST = [
    (
        TTL1,
        os.path.join(PATH_RR, "example_roles"),
        False,
        TTL1_R,
        ["ansiblebit.oracle-java"],
        [],
        [],
    ),
    (
        TTL2,
        os.path.join(PATH_RR, "example_roles"),
        True,
        TTL2_R,
        [],
        ["ansiblebit.oracle-java2"],
        [],
    ),
    (TTL3, [], False, TTL3_R, [], [], ["apt"]),
]


@pytest.mark.parametrize(
    "task_list, role_repos, allow_external_roles, expected, internal_expected, external_expected, modules_expected",
    TASK_TYPE_LIST,
)
def test_calculate_task_types(
    task_list,
    role_repos,
    allow_external_roles,
    expected,
    internal_expected,
    external_expected,
    modules_expected,
):

    internal_roles, external_roles, modules_used = calculate_task_types(
        task_list, role_repos, allow_external_roles
    )

    assert task_list == expected
    assert internal_roles == internal_expected
    assert external_roles == external_expected
    assert modules_used == modules_expected


TASK_TYPE_LIST_FAIL = [(TTL2, os.path.join(PATH_RR, "example_roles"), False)]


@pytest.mark.parametrize(
    "task_list, role_repos, allow_external_roles", TASK_TYPE_LIST_FAIL
)
def test_calculate_task_types_fail(task_list, role_repos, allow_external_roles):

    with pytest.raises(NsblException):
        calculate_task_types(task_list, role_repos, allow_external_roles)


CTL_1 = ["apt"]
CTL_1_EX = [
    {
        "meta": {"name": "apt", "task-name": "apt", "task-type": "ansible-module"},
        "vars": {},
    }
]
CTL_1_EX_I = []
CTL_1_EX_E = []
CTL_1_EX_M = ["apt"]

# TODO: more test cases here

TASK_LISTS_CONSTRUCTOR = [
    (CTL_1, [], [], False, CTL_1_EX, CTL_1_EX_I, CTL_1_EX_E, CTL_1_EX_M)
]


@pytest.mark.parametrize(
    "task_list, role_repos, task_alias_files, allow_external_roles, expected, exp_int, exp_ext, exp_mod",
    TASK_LISTS_CONSTRUCTOR,
)
def test_tasklist_class_init(
    task_list,
    role_repos,
    task_alias_files,
    allow_external_roles,
    expected,
    exp_int,
    exp_ext,
    exp_mod,
):

    tl = TaskList(
        task_list,
        external_files=None,
        run_metadata={
            "role_repos": role_repos,
            "task_alias_files": task_alias_files,
            "allow_external_roles": allow_external_roles,
        },
    )

    assert tl.task_list == expected
    assert tl.internal_role_names == exp_int
    assert tl.external_role_names == exp_ext
    assert tl.modules_used == exp_mod


TL1 = [{"apt": {"name": "zile"}}]
TL1_EX = [{"name": "apt", "apt": {"name": "zile"}}]
TL1_b = [{"apt": {"vars": {"name": "zile"}}}]
TL1_c = [{"apt": {"vars": {"name": "zile"}, "meta": {}}}]
TASK_LISTS = [
    (TL1, [], [], False, TL1_EX),
    (TL1_b, [], [], False, TL1_EX),
    (TL1_c, [], [], False, TL1_EX),
]


@pytest.mark.parametrize(
    "task_list, role_repos, task_alias_files, allow_external_roles, expected",
    TASK_LISTS,
)
def test_tasklist(
    task_list, role_repos, task_alias_files, allow_external_roles, expected
):

    tl = TaskList(
        task_list,
        external_files=None,
        run_metadata={
            "role_repos": role_repos,
            "task_alias_files": task_alias_files,
            "allow_external_roles": allow_external_roles,
        },
    )

    result = tl.render_ansible_tasklist()

    assert list_of_special_dicts_to_list_of_dicts(result) == expected
