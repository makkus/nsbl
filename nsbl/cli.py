# -*- coding: utf-8 -*-

import pprint
import click
import sys
from .nsbl import NsblInventory, Nsbl
from .env_creator import AnsibleEnvironment, NsblCreateException
from . import __version__ as VERSION

import click_log

@click.group(invoke_without_command=True)
@click.option('--version', help='the version of frkl you are using', is_flag=True)
@click_log.simple_verbosity_option()
@click.pass_context
@click_log.init("nsbl")
def cli(ctx, version):
    """Console script for nsbl"""

    if version:
        click.echo(VERSION)
        sys.exit(0)

    ctx.obj = {}


@cli.command('create')
@click.argument('config', required=True, nargs=-1)
@click.option('--output', '-o', help="output directory of created ansible environment, defaults to 'nsbl_env' in the current directory", default="nsbl_env")
@click.pass_context
def execute(ctx, config, output):

    nsbl = Nsbl(config, "/home/markus/projects/nsbl-roles")
    nsbl.render_environment(output)

if __name__ == "__main__":
    cli()
