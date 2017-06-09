# -*- coding: utf-8 -*-

import os
import pprint
import click
import sys
from .nsbl import NsblInventory, Nsbl
from .env_creator import AnsibleEnvironment, NsblCreateException
from . import __version__ as VERSION
import yaml
import json

import click_log

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
    ctx.obj['role-repos'] = role_repo
    ctx.obj['task-desc'] = task_desc


@cli.command('list-groups')
@click.argument('config', required=True, nargs=-1)
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.option('--pager', '-p', required=False, default=False, is_flag=True, help='output via pager')
@click.pass_context
def list_groups(ctx, config, format, pager):

    nsbl = Nsbl(config, ctx.obj['task-desc'], ctx.obj['role-repos'])
    output(nsbl.inventory.groups, format)

def output(python_object, format="raw", pager=False):

    if format == 'yaml':
        output = yaml.dump(python_object, default_flow_style=False)
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

@cli.command('list-hosts')
@click.argument('config', required=True, nargs=-1)
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.option('--pager', '-p', required=False, default=False, is_flag=True, help='output via pager')
@click.pass_context
def list_hosts(ctx, config, format, pager):

    nsbl = Nsbl(config, ctx.obj['task-desc'], ctx.obj['role-repos'])
    output(nsbl.inventory.hosts, format)

@cli.command('list-tasks')
@click.argument('config', required=True, nargs=-1)
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.option('--pager', '-p', required=False, default=False, is_flag=True, help='output via pager')
@click.pass_context
def list_tasks(ctx, config, format, pager):
    nsbl = Nsbl(config, ctx.obj['task-desc'], ctx.obj['role-repos'])

    result = []
    for task in nsbl.tasks:
        tasks = task.get_dict()
        result.append(tasks)

    output(result, format, pager)

@cli.command('create-inventory')
@click.argument('config', required=True, nargs=-1)
@click.option('--target', '-t', nargs=1, required=False, help="the target inventory dir, defaults to nsbl_inv in the current directory", default="nsb_inv")
@click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
@click.option('--relative/--absolute', default=True, help="only applicable for dynamic inventory script, determine to use relative or absolute paths to config files and role repos in the script. default: relative (to the target dir the script is in)")
@click.pass_context
def extract_inventory(ctx, config, target, static, relative):

    nsbl = Nsbl(config, ctx.obj['task-desc'], ctx.obj['role-repos'])
    if static:
        nsbl.inventory.extract_vars("/tmp/inventory")
        nsbl.inventory.write_inventory_file_or_script("/tmp/inventory", extract_vars=True)
    else:
        os.makedirs("/tmp/inventory")
        nsbl.inventory.write_inventory_file_or_script("/tmp/inventory", extract_vars=False, relative_paths=relative)

@cli.command('print-inventory')
@click.argument('config', required=True, nargs=-1)
@click.option('--pager', '-p', required=False, default=False, help='output via pager')
@click.pass_context
def print_inventory(ctx, config, pager):

    nsbl = Nsbl(config, ctx.obj['task-desc'], ctx.obj['role-repos'])

    inv_string = nsbl.inventory.get_inventory_config_string()
    output(inv_string, format="raw", pager=pager)

@cli.command('print-available-tasks')
@click.option('--pager', '-p', required=False, default=False, help='output via pager')
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.pass_context
def print_available_tasks(ctx, pager, format):

    nsbl = Nsbl([], ctx.obj['task-desc'], ctx.obj['role-repos'])
    int_tasks = nsbl.int_task_descs
    output(int_tasks, format, pager)

@cli.command('create-environment')
@click.argument('config', required=True, nargs=-1)
@click.option('--target', '-t', help="target output directory of created ansible environment, defaults to 'nsbl_env' in the current directory", default="nsbl_env")
@click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
@click.option('--force', '-f', is_flag=True, help="delete potentially existing target directory", default=False)
@click.pass_context
def create(ctx, config, target, static, force):

    nsbl = Nsbl(config, ctx.obj['task-desc'], ctx.obj['role-repos'])

    nsbl.render_environment(target, extract_vars=static, force=force)



if __name__ == "__main__":
    cli()
