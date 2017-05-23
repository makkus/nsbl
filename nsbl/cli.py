# -*- coding: utf-8 -*-

import pprint
import click
import sys
from .nsbl import Nsbl
from .env_creator import AnsibleEnvironment, NsblCreateException

@click.command()
def main():
    """Console script for nsbl"""

    print("XX")
    execute()

def execute():
    env = AnsibleEnvironment(["/home/markus/projects/nsbl/examples/boxes.yml"], "/home/markus/temp/test_env")
    try:
        env.create()
    except NsblCreateException as e:
        print(e)

if __name__ == "__main__":
    main()
