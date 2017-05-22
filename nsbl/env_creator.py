#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
from .nsbl import Nsbl
from cookiecutter.main import cookiecutter
import click
import yaml

log = logging.getLogger("nsbl")

class NsblCreateException(Exception):

    def __init__(self, message, errors=[]):
        super(NsblCreateException, self).__init__(message)

        self.errors = errors

class AnsibleEnvironment(object):

    def __init__(self, configs, env_dir):

        self.configs = configs
        self.env_dir = env_dir
        self.link_dir = None

        self.nsbl = Nsbl(self.configs)

    def create(self):

        try:
            os.makedirs(self.execution_dir)
        except (OSError) as e:
            raise NsblCreateException(e.msg, e)
