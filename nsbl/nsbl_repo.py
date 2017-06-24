# -*- coding: utf-8 -*-

import click
import sys
import os
join = os.path.join

from git import Repo

class RolesRepo(object):
    """Holds a repo of ansible roles.
    """

    def __init__(self, dir):

        self.dir = os.path.abspath(dir)
        self.dirname = os.path.basename(self.dir)
        self.parent = os.path.abspath(os.path.join(self.dir, os.pardir))
