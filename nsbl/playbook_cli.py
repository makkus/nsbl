# -*- coding: utf-8 -*-

import json
import pprint
import sys

import click
import click_log
import logging
import yaml

from . import __version__ as VERSION
from .nsbl import Nsbl, NsblRunner

logger = logging.getLogger("nsbl")
click_log.basic_config(logger)

@click.command()
@click.option('--version', help='the version of frkl you are using', is_flag=True)
@click.option('--role-repo', '-r', help='path to a local folder containing ansible roles', multiple=True)
@click.option('--task-desc', '-t', help='path to a local task description yaml file', multiple=True)
@click.option('--stdout-callback', '-c', help='name of or path to callback plugin to be used as default stdout plugin',
              default="default")
@click.option('--target', '-t',
              help="target output directory of created ansible environment, defaults to 'nsbl_env' in the current directory",
              default="~/.nsbl/runs/archive/run")
# @click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
@click.option('--force/--no-force', help="delete potentially existing target directory", default=True)
@click.argument('config', required=True, nargs=-1)
@click.option('--no-run', help="don't run the environment, only render it to the target directory", is_flag=True,
              default=False)
@click.option('--ask-become-pass', help='whether to ask the user for a sudo password if necessary', is_flag=True,
              default=True)
@click_log.simple_verbosity_option(logger)
def cli(version, role_repo, task_desc, stdout_callback, target, force, config, no_run, ask_become_pass):
    """Console script for nsbl"""

    if version:
        click.echo(VERSION)
        sys.exit(0)

    nsbl_obj = Nsbl.create(config, role_repo, task_desc)

    runner = NsblRunner(nsbl_obj)
    runner.run(target, force=force, ansible_verbose="", ask_become_pass=ask_become_pass, callback=stdout_callback,
               add_timestamp_to_env=True, add_symlink_to_env="~/.nsbl/runs/current", no_run=no_run)


def output(python_object, format="raw", pager=False):
    if format == 'yaml':
        output = yaml.safe_dump(python_object, default_flow_style=False, encoding='utf-8', allow_unicode=True)
    elif format == 'json':
        output = json.dumps(python_object, sort_keys=4, indent=4)
    elif format == 'raw':
        output = str(python_object)
    elif format == 'pformat':
        output = pprint.pformat(python_object)

    if pager:
        click.echo_via_pager(output)
    else:
        click.echo(output)
