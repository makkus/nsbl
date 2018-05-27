import os
import pprint

from nsbl.tasklist import *
import pytest

from ruamel.yaml import YAML
from frutils import *
from nsbl.defaults import *
from nsbl.inventory import *
CWD = os.path.dirname(os.path.realpath(__file__))
PATH_TL = os.path.join(CWD, "task_lists")
PATH_RR = os.path.join(CWD, "role_repos")
PATH_IN = os.path.join(CWD, "inventory")

yaml = YAML()
yaml.default_flow_style = False

CONFIG_LIST = [
    (os.path.join(PATH_IN, "basic.yml"), {"_meta": {"hostvars": {"localhost": {"ansible_connection": "local", "ansible_user": "markus"}}}})
]
@pytest.mark.parametrize("config_path, expected", CONFIG_LIST)
def test_inventory(config_path, expected):

    inv = NsblInventory.create(config_path)
    assert inv.list() == expected

