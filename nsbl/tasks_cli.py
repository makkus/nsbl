# -*- coding: utf-8 -*-

import json
import pprint
import sys

import click
import click_log
import yaml

from . import __version__ as VERSION
from .defaults import *
from .nsbl import Nsbl, NsblRunner


def output(python_object, format="raw", pager=False):
    if format == 'yaml':
        output_string = yaml.safe_dump(python_object, default_flow_style=False, encoding='utf-8', allow_unicode=True)
    elif format == 'json':
        output_string = json.dumps(python_object, sort_keys=4, indent=4)
    elif format == 'raw':
        output_string = str(python_object)
    elif format == 'pformat':
        output_string = pprint.pformat(python_object)
    else:
        raise Exception("No valid output format provided. Supported: 'yaml', 'json', 'raw', 'pformat'")

    if pager:
        click.echo_via_pager(output_string)
    else:
        click.echo(output_string)


@click.group(invoke_without_command=True)
@click.option('--version', help='the version of frkl you are using', is_flag=True)
@click.option('--role-repo', '-r', help='path to a local folder containing ansible roles', multiple=True)
@click.option('--task-desc', '-t', help='path to a local task description yaml file', multiple=True)
@click_log.simple_verbosity_option()
@click.pass_context
@click_log.init("nsbl")
def cli(ctx, version, role_repo, task_desc):
    """Console script for nsbl"""

    if version:
        click.echo(VERSION)
        sys.exit(0)

    ctx.obj = {}
    ctx.obj['role-repos'] = calculate_role_repos(role_repo, use_default_roles=True)
    ctx.obj['task-desc'] = calculate_task_descs(task_desc, ctx.obj['role-repos'])


@cli.command('execute')
@click.argument('config', required=True, nargs=-1)
@click.option('--target', '-t',
              help="target output directory of created ansible environment, defaults to 'nsbl_env' in the current directory",
              default="nsbl_env")
@click.option('--stdout-callback', '-c', help='name of or path to callback plugin to be used as default stdout plugin',
              default="default")
# @click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
@click.option('--force', '-f', is_flag=True, help="delete potentially existing target directory", default=False)
@click.pass_context
def execute(ctx, config, stdout_callback, target, force):
    nsbl = Nsbl.create(config, ctx.obj['role-repos'], ctx.obj['task-desc'], wrap_into_localhost_env=True)

    runner = NsblRunner(nsbl)
    runner.run(target, force, "", stdout_callback)


if __name__ == "__main__":
    cli()
