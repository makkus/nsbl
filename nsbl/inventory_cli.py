# -*- coding: utf-8 -*-

import json
import sys

import click

from .inventory import NsblInventory


@click.command()
@click.option('--list', help='list of all groups', required=False, is_flag=True)
@click.option('--host', help='variables of a host', required=False, nargs=1)
@click.option('--config', help='configuration file(s)', required=True, multiple=True)
def main(list, host, config):
    """Console script for nsbl"""

    if list and host:
        click.echo("Using both '--list' and '--host' options not allowd")
        sys.exit(1)

    inventory = NsblInventory.create(config)
    if list:
        result = inventory.list()
        result_json = json.dumps(result, sort_keys=4, indent=4)
        print(result_json)
    elif host:
        result = inventory.host(host)
        result_json = json.dumps(result, sort_keys=4, indent=4)
        print(result_json)


if __name__ == "__main__":
    main()
