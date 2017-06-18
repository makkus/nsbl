#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_nsbl
----------------------------------

Tests for `nsbl` module.
"""

import pytest

import pprint

from contextlib import contextmanager
from click.testing import CliRunner

from nsbl import nsbl
from nsbl import cli

def test_command_line_interface():
    runner = CliRunner()
    result = runner.invoke(cli.cli)
    assert result.exit_code == 0
    help_result = runner.invoke(cli.cli, ['--help'])
    pprint.pprint(help_result.output)
    assert help_result.exit_code == 0
    assert 'Show this message and exit.' in help_result.output


