# -*- coding: utf-8 -*-

import json
import logging
import sys

import click
import click_log
import yaml

from . import __version__ as VERSION
from .defaults import *
from .inventory import NsblInventory
from .nsbl import Nsbl
from .tasks import NsblTasks

logger = logging.getLogger('nsbl')


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
@click_log.simple_verbosity_option(logger)
@click.pass_context
def cli(ctx, version, role_repo, task_desc):
    """Console script for nsbl"""

    if version:
        click.echo(VERSION)
        sys.exit(0)

    ctx.obj = {}
    ctx.obj['role-repos'] = calculate_role_repos(role_repo, use_default_roles=True)
    ctx.obj['task-desc'] = calculate_task_descs(task_desc, ctx.obj['role-repos'])


@cli.command('list-groups')
@click.argument('config', required=True, nargs=-1)
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.option('--pager', '-p', required=False, default=False, is_flag=True, help='output via pager')
@click.pass_context
def list_groups(ctx, config, format, pager):
    """Lists all groups and their variables"""

    inventory = NsblInventory.create(config)
    if inventory.groups:
        output(inventory.groups, format)


@cli.command('list-hosts')
@click.argument('config', required=True, nargs=-1)
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.option('--pager', '-p', required=False, default=False, is_flag=True, help='output via pager')
@click.pass_context
def list_hosts(ctx, config, format, pager):
    """Lists all hosts and their variables"""

    inventory = NsblInventory.create(config)
    if inventory.hosts:
        output(inventory.hosts, format)


@cli.command('list-roles')
@click.argument('config', required=True, nargs=-1)
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.option('--pager', '-p', required=False, default=False, is_flag=True, help='output via pager')
@click.pass_context
def list_roles(ctx, config, format, pager):
    """Lists all roles from a task list"""

    tasks = NsblTasks.create(config, ctx.obj['role-repos'], ctx.obj['task-desc'])
    result = []
    for role in tasks.roles:
        result.append(role.details())

    output(result, format, pager)


# @cli.command('describe-tasks')
# @click.argument('config', required=True, nargs=-1)
# @click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
# @click.option('--pager', '-p', required=False, default=False, is_flag=True, help='output via pager')
# @click.pass_context
# def describe_tasks(ctx, config, format, pager):

#     init_params = {"role_repos": ctx.obj['role-repos'], "task_descs": ctx.obj['task-desc'], "meta": {}, "vars": {}}
#     tasks = NsblTasks(init_params)

#     task_format = generate_nsbl_tasks_format(tasks.task_descs)
#     # pprint.pprint(task_format)
#     chain = [frkl.UrlAbbrevProcessor(), frkl.EnsureUrlProcessor(), frkl.EnsurePythonObjectProcessor(), frkl.FrklProcessor(task_format), NsblTaskProcessor(init_params), NsblDynamicRoleProcessor(init_params)]
#     # chain = [frkl.UrlAbbrevProcessor(), frkl.EnsureUrlProcessor(), frkl.EnsurePythonObjectProcessor(), frkl.FrklProcessor(task_format), NsblTaskProcessor(init_params)]
#     frkl_obj = frkl.Frkl(config, chain)
#     # print(config)
#     result = frkl_obj.process(tasks)
#     pprint.pprint(result)
#     # result.render_roles("/tmp/role_test")
#     # result.render_playbook("/tmp/plays")


@cli.command('create-inventory')
@click.argument('config', required=True, nargs=-1)
@click.option('--target', '-t', nargs=1, required=False,
              help="the target inventory dir, defaults to 'inventory' in the current directory", default="inventory")
# @click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
# @click.option('--relative/--absolute', default=True, help="only applicable for dynamic inventory script, determine to use relative or absolute paths to config files and role repos in the script. default: relative (to the target dir the script is in)")
@click.pass_context
def extract_inventory(ctx, config, target):
    """Creates an ansible inventory folder with in inventory file, and all group and host vars folders"""

    inventory = NsblInventory.create(config)

    # if static:
    inventory.extract_vars(target)
    inventory.write_inventory_file_or_script(target, extract_vars=True)
    # else:
    # os.makedirs("/tmp/inventory")
    # inventory.write_inventory_file_or_script("/tmp/inventory", extract_vars=False, relative_paths=relative)


@cli.command('print-inventory')
@click.argument('config', required=True, nargs=-1)
@click.option('--pager', '-p', required=False, default=False, help='output via pager')
@click.pass_context
def print_inventory(ctx, config, pager):
    """Prints the assembled inventory file, containing hosts, groups and subgroups"""

    inventory = NsblInventory.create(config)

    inv_string = inventory.get_inventory_config_string()
    output(inv_string, format="raw", pager=pager)


@cli.command('print-available-tasks')
@click.option('--pager', '-p', required=False, default=False, help='output via pager')
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.pass_context
def print_available_tasks(ctx, pager, format):
    """Prints all available tasks included in the included (or specified) task-desc files"""

    nsbl = Nsbl.create([], ctx.obj['role-repos'], ctx.obj['task-desc'])
    int_tasks = nsbl.task_descs
    output(int_tasks, format, pager)


@cli.command('expand-packages')
@click.argument('config', required=True, nargs=-1)
@click.option('--pager', '-p', required=False, default=False, help='output via pager')
@click.option('--format', '-f', required=False, default='yaml', help='output format, either json or yaml (default)')
@click.pass_context
def expand_packages(ctx, config, pager, format):
    """Creates an expanded list of packages out of a package list (for debugging purposes)"""

    frkl_format = {"child_marker": "packages",
                   "default_leaf": "vars",
                   "default_leaf_key": "name",
                   "key_move_map": {'*': "vars"}
                   }
    chain = [frkl.EnsureUrlProcessor(), frkl.EnsurePythonObjectProcessor(), frkl.FrklProcessor(frkl_format)]

    frkl_obj = frkl.Frkl(config, chain)
    result = frkl_obj.process()
    output(result, format, pager)


@cli.command('create-environment')
@click.argument('config', required=True, nargs=-1)
@click.option('--target', '-t',
              help="target output directory of created ansible environment, defaults to 'nsbl_env' in the current directory",
              default="nsbl_env")
# @click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
@click.option('--force', '-f', is_flag=True, help="delete potentially existing target directory", default=False)
@click.pass_context
def create(ctx, config, target, force):
    nsbl = Nsbl.create(config, ctx.obj['role-repos'], ctx.obj['task-desc'])

    nsbl.render(target, extract_vars=True, force=force, ansible_args="", callback='default')
    # for play, tasks in result["plays"].items():
    # pprint.pprint(play)
    # pprint.pprint(tasks.roles)

    # nsbl.render_environment(target, extract_vars=static, force=force, ansible_verbose="")


if __name__ == "__main__":
    cli()
