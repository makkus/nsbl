# -*- coding: utf-8 -*-

import pprint
import click
import sys
import json
from .inventory import NsblInventory
from frkl import Frkl
from .defaults import NSBL_INVENTORY_BOOTSTRAP_CHAIN

@click.command()
@click.option('--list', help='list of all groups', required=False, is_flag=True)
@click.option('--host', help='variables of a host', required=False, nargs=1)
@click.option('--config', help='configuration file(s)', required=True, multiple=True)
def main(list, host, config):
    """Console script for nsbl"""

    if list and host:
        click.echo("Using both '--list' and '--host' options not allowd")
        sys.exit(1)

    inventory = NsblInventory()
    inv_obj = Frkl(config, NSBL_INVENTORY_BOOTSTRAP_CHAIN)
    inv_obj.process(inventory)

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
