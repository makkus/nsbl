#!/usr/bin/env python
# -*- coding: utf-8 -*-

import inspect
import logging
import subprocess

import os
from cookiecutter.main import cookiecutter

from .nsbl import NsblInventory

log = logging.getLogger("nsbl")

PLAYBOOK_DIR = "plays"
INVENTORY_DIR = "inventory"
EXECUTION_SCRIPT_FILE = "run_play.sh"


def can_passwordless_sudo():
    """Checks if the user can use passwordless sudo on this host."""

    FNULL = open(os.devnull, 'w')
    p = subprocess.Popen('sudo -n ls', shell=True, stdout=FNULL, stderr=subprocess.STDOUT, close_fds=True)
    r = p.wait()
    return r == 0


class NsblCreateException(Exception):
    def __init__(self, message_or_parent, parent=None):
        if isinstance(message_or_parent, Exception):
            self.msg = message_or_parent.__str__()
            self.parent = message_or_parent
        else:
            self.msg = message_or_parent
            self.parent = parent

        super(NsblCreateException, self).__init__(self.msg)


class AnsibleEnvironment(object):
    def __init__(self, configs, env_dir, roles={}, callback_plugins={}, callback_plugin_name=None):

        self.configs = configs
        self.env_dir = env_dir
        self.parent_dir = os.path.abspath(os.path.join(self.env_dir, os.pardir))
        self.link_dir = None
        self.roles = roles
        self.callback_plugins = callback_plugins,
        self.callback_plugin_name = callback_plugin_name

        self.nsbl = NsblInventory(self.configs)

    def create(self):

        try:
            if not os.path.exists(self.parent_dir):
                os.makedirs(self.parent_dir)
        except (OSError) as e:
            raise NsblCreateException(e)

        self.playbook_dir = os.path.join(self.env_dir, PLAYBOOK_DIR)
        self.inventory_dir = os.path.join(self.env_dir, INVENTORY_DIR)

        this_file = inspect.stack()[0][1]
        this_parent_folder = os.path.abspath(os.path.join(this_file, os.pardir))

        passwordless_sudo = can_passwordless_sudo()

        cookiecutter_details = {
            "env_dir": self.env_dir,
            "nsbl_script_configs": " --config ".join(self.configs),
            "nsbl_roles": self.roles,
            "nsbl_callback_plugins": self.callback_plugins,
            "nsbl_callback_plugin_name": ""
        }

        log.debug("Creating build environment from template...")
        log.debug("Using cookiecutter details: {}".format(cookiecutter_details))

        template_path = os.path.join(os.path.dirname(__file__), "external", "cookiecutter-ansible-environment")

        cookiecutter(template_path, extra_context=cookiecutter_details, no_input=True)
