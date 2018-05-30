# -*- coding: utf-8 -*-

import logging
import sys

import click
import click_completion
import click_log

from . import __version__ as VERSION
from .nsbl import create_nsbl_env
from .nsbl_context import NsblContext
from .runner import NsblRunner

logger = logging.getLogger("nsbl")
click_log.basic_config(logger)

# optional shell completion
click_completion.init()


def raise_error(exc):

    if hasattr(exc, "message"):
        raise click.ClickException(exc.message)
    else:
        raise click.ClickException(exc)


@click.command(short_help="create and run ansible environments")
@click.option("--version", help="the version of frkl you are using", is_flag=True)
@click.option(
    "--role-repo", "-a", help="path to a local task alias files or repos", multiple=True
)
@click.option(
    "--task-alias",
    "-t",
    help="path to a local task description yaml file",
    multiple=True,
)
@click.option(
    "--stdout-callback",
    "-c",
    help="name of or path to callback plugin to be used as default stdout plugin",
    default="default",
)
@click.option(
    "--target",
    "-t",
    help="target output directory of created ansible environment, defaults to '~/.local/share/nsbl/runs/archive' in the current directory",
    default="~/.local/share/nsbl/runs/archive",
)
# @click.option('--static/--dynamic', default=True, help="whether to render a dynamic inventory script using the provided config files instead of a plain ini-type config file and group_vars and host_vars folders, default: static")
@click.option(
    "--force/--no-force",
    help="delete potentially existing target directory",
    default=True,
)
@click.argument("config", required=True, nargs=-1)
@click.option(
    "--no-run",
    help="don't run the environment, only render it to the target directory",
    is_flag=True,
    default=False,
)
@click.option(
    "--ask-become-pass",
    help="whether to ask the user for a sudo password if necessary",
    is_flag=True,
    default=True,
)
@click_log.simple_verbosity_option(logger, "--verbosity", default="INFO")
def cli(
    version,
    role_repo,
    task_alias,
    stdout_callback,
    target,
    force,
    config,
    no_run,
    ask_become_pass,
):
    """Create Ansible environments from (single) configuration files and execute them.


    """

    if version:
        click.echo(VERSION)
        sys.exit(0)

    nsbl_context = NsblContext(role_repo_paths=role_repo, task_alias_paths=task_alias)

    nsbl_obj = create_nsbl_env(config, base_path=None, nsbl_context=nsbl_context)

    if stdout_callback == "verbose":
        stdout_callback = "default"
        ansible_verbose = "-vvvv"
    elif stdout_callback == "verbose-yaml":
        stdout_callback = "yaml"
        ansible_verbose = "-vvvv"
    else:
        ansible_verbose = ""

    if target != "~/.local/share/nsbl/runs/archive":
        symlink = None
        timestamp = False
    else:
        symlink = "~/.local/share/nsbl/runs/current"
        timestamp = True

    runner = NsblRunner(nsbl_obj)
    runner.run(
        target,
        force=force,
        ansible_args=ansible_verbose,
        ask_become_pass=ask_become_pass,
        callback=stdout_callback,
        add_timestamp_to_env=timestamp,
        add_symlink_to_env=symlink,
        no_run=no_run,
    )
