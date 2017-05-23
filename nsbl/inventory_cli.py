# -*- coding: utf-8 -*-

import pprint
import click
import sys
from .nsbl import Nsbl

@click.command()
@click.option('--list', help='list of all groups', required=False, is_flag=True)
@click.option('--host', help='variables of a host', required=False, nargs=1)
@click.option('--config', help='configuration file(s)', required=True, multiple=True)
def main(list, host, config):
    """Console script for nsbl"""

    if list and host:
        click.echo("Using both '--list' and '--host' options not allowd")
        sys.exit(1)

    nsbl_obj = Nsbl(config)

    # print(nsbl_obj.config)
    if list:
        result = nsbl_obj.list()
        print(result)
    elif host:
        result = nsbl_obj.host(host)
        print(result)



if __name__ == "__main__":
    main()
