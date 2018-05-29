# -*- coding: utf-8 -*-

import logging
import sys

import click
import click_completion
import click_log

from frutils.frutils_cli import output
from . import __version__ as VERSION
from .defaults import *
from .inventory import NsblInventory
from .nsbl_config import create_config
from .nsbl_context import NsblContext

logger = logging.getLogger("nsbl")
click_log.basic_config(logger)

# optional shell completion
click_completion.init()


def raise_error(exc):

    if hasattr(exc, "message"):
        raise click.ClickException(exc.message)
    else:
        raise click.ClickException(exc)


@click.group(invoke_without_command=True)
@click.option("--version", help="the version of frkl you are using", is_flag=True)
@click.option(
    "--role-repo",
    "-r",
    help="path to a local folder containing ansible roles",
    multiple=True,
)
@click.option(
    "--task-aliases",
    "-a",
    help="path to a local task alias files or repos",
    multiple=True,
)
@click.option(
    "--task-lists",
    "-l",
    help="path to a local task-list or task-list repo"
)
@click.option(
    "--allow-external-roles", "-a", help="try to download roles from Ansible Galaxy if not available locally",
    is_flag=True)
@click_log.simple_verbosity_option(logger, "--verbosity", default="WARN")
@click.pass_context
def cli(ctx, version, role_repo, task_aliases, task_lists, allow_external_roles):
    """'nsbl' is a wrapper framework for Ansible, trying to minimize configuration."""

    if version:
        click.echo(VERSION)
        sys.exit(0)

    ctx.obj = {}
    nsbl_context = NsblContext(role_repo_paths=role_repo, task_list_paths=task_lists, task_alias_paths=task_aliases)
    ctx.obj["nsbl-context"] = nsbl_context
    ctx.obj["allow-external-roles"] = allow_external_roles


@cli.command("list-groups")
@click.argument("config", required=True, nargs=-1)
@click.option(
    "--format",
    "-f",
    required=False,
    default="yaml",
    help="output format, either json or yaml (default)",
)
@click.option(
    "--pager",
    "-p",
    required=False,
    default=False,
    is_flag=True,
    help="output via pager",
)
@click.pass_context
def list_groups(ctx, config, format, pager):
    """Lists all groups and their variables."""

    inventory = NsblInventory.create(config)
    if inventory.groups:
        output(inventory.groups, format)


@cli.command("list-hosts")
@click.argument("config", required=True, nargs=-1)
@click.option(
    "--format",
    "-f",
    required=False,
    default="yaml",
    help="output format, either json or yaml (default)",
)
@click.option(
    "--pager",
    "-p",
    required=False,
    default=False,
    is_flag=True,
    help="output via pager",
)
@click.pass_context
def list_hosts(ctx, config, format, pager):
    """Lists all hosts and their variables"""

    inventory = NsblInventory.create(config)
    if inventory.hosts:
        output(inventory.hosts, format)


# @cli.command("list-roles")
# @click.argument("config", required=True, nargs=-1)
# @click.option(
#     "--format",
#     "-f",
#     required=False,
#     default="yaml",
#     help="output format, either json or yaml (default)",
# )
# @click.option(
#     "--pager",
#     "-p",
#     required=False,
#     default=False,
#     is_flag=True,
#     help="output via pager",
# )
# @click.pass_context
# def list_roles(ctx, config, format, pager):
#     """Lists all roles from a task list"""
#
#     tasks = NsblTasks.create(config, ctx.obj["role-repos"], ctx.obj["task-desc"])
#     result = []
#     for role in tasks.roles:
#         result.append(role.details())
#
#     output(result, format, pager)


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


@cli.command("create-inventory")
@click.argument("config", required=True, nargs=-1)
@click.option(
    "--target",
    "-t",
    nargs=1,
    required=False,
    help="the target inventory dir, defaults to 'inventory' in the current directory",
    default="inventory",
)
# @click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
# @click.option('--relative/--absolute', default=True, help="only applicable for dynamic inventory script, determine to use relative or absolute paths to config files and role repos in the script. default: relative (to the target dir the script is in)")
@click.pass_context
def extract_inventory(ctx, config, target):
    """Creates an ansible inventory folder with in inventory file, and all group and host vars folders"""

    inventory = NsblInventory.create(config)

    # if static:
    inventory.extract_vars(target)
    inventory.write_inventory_file_or_script(target, extract_vars=True)
    click.echo("Inventory written to folder: {}".format(os.path.abspath(target)))

    # else:
    # os.makedirs("/tmp/inventory")
    # inventory.write_inventory_file_or_script("/tmp/inventory", extract_vars=False, relative_paths=relative)


@cli.command("print-inventory")
@click.argument("config", required=True, nargs=-1)
@click.option("--pager", "-p", required=False, default=False, help="output via pager")
@click.pass_context
def print_inventory(ctx, config, pager):
    """Prints the assembled inventory file, containing hosts, groups and subgroups"""

    inventory = NsblInventory.create(config)

    inv_string = inventory.get_inventory_config_string()
    output(inv_string, output_type="raw", pager=pager)


@cli.command("list-task-aliases")
@click.option("--pager", "-p", required=False, default=False, help="output via pager")
@click.option(
    "--format",
    "-f",
    required=False,
    default="yaml",
    help="output format, either json or yaml (default)",
)
@click.pass_context
def list_task_aliases(ctx, pager, format):
    """Prints all available tasks included in the included (or specified) task-desc files"""

    context = ctx.obj["nsbl-context"]

    alias_names = context.task_aliases.keys()
    output(alias_names, format, pager)


# @cli.command("expand-packages")
# @click.argument("config", required=True, nargs=-1)
# @click.option("--pager", "-p", required=False, default=False, help="output via pager")
# @click.option(
#     "--format",
#     "-f",
#     required=False,
#     default="yaml",
#     help="output format, either json or yaml (default)",
# )
# @click.pass_context
# def expand_packages(ctx, config, pager, format):
#     """Creates an expanded list of packages out of a package list (for debugging purposes)"""
#
#     frkl_format = {
#         "child_marker": "packages",
#         "default_leaf": "vars",
#         "default_leaf_key": "name",
#         "key_move_map": {"*": "vars"},
#     }
#     chain = [
#         EnsureUrlProcessor(),
#         EnsurePythonObjectProcessor(),
#         FrklProcessor(frkl_format),
#     ]
#
#     frkl_obj = Frkl(config, chain)
#     result = frkl_obj.process()
#     output(result, format, pager)


@cli.command("create-environment")
@click.argument("config", required=True, nargs=-1)
@click.option(
    "--target",
    "-t",
    help="target output directory of created ansible environment, defaults to 'nsbl_env' in the current directory",
    default="nsbl_env",
)
# @click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="delete potentially existing target directory",
    default=False,
)
@click.pass_context
def create(ctx, config, target, force):

    try:
        role_repos = ctx.obj["role-repos"]
        task_aliases_paths = ctx.obj["task-desc"]
        allow_external_roles = ctx.obj["allow-external-roles"]
        config = create_config(config, role_repo_paths=role_repos, task_aliases_paths=task_aliases_paths, allow_external_roles=allow_external_roles)

        config.render(target, extract_vars=True, force=force, ansible_args="", callback="default")
    except (Exception) as e:
        logger.debug(e)
        raise click.ClickException(e.message)

    # try:
    #     nsbl = Nsbl.create(config, ctx.obj["role-repos"], ctx.obj["task-desc"])
    #     nsbl.render(
    #         target, extract_vars=True, force=force, ansible_args="", callback="default"
    #     )
    #     click.echo("Ansible environment written to: {}".format(os.path.abspath(target)))
    # except (Exception) as e:
    #     raise_error(e)

    # for play, tasks in result["plays"].items():
    # pprint.pprint(play)
    # pprint.pprint(tasks.roles)

    # nsbl.render_environment(target, extract_vars=static, force=force, ansible_verbose="")


if __name__ == "__main__":
    cli()
