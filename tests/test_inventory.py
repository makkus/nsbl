#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_nsbl
----------------------------------

Tests for `nsbl` module.
"""

import pprint

import os
import pytest
import yaml
from frkl import frkl


@pytest.mark.parametrize("test_name", [
    "localhost_inventory",
    "groups_inventory"
])
def test_files(test_name):

    folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), "chain_tests", test_name)

    input_files = []
    for child in os.listdir(folder):
        if not child.startswith("_"):
            input_files.append(os.path.join(folder, child))
    input_files.sort()

    result_file = os.path.join(folder, "__result.yml")

    with open(result_file) as f:
        content = f.read()

    expected_obj = yaml.safe_load(content)

    init_file = os.path.join(folder, "_init.yml")
    result_obj = frkl.FrklCallback.init(init_file, input_files)
    result = result_obj.result()

    pprint.pprint(expected_obj)
    print("XXX")
    pprint.pprint(result)

    assert expected_obj == result
