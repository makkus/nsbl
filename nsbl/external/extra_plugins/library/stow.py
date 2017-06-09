# -*- coding: utf-8 -*-
import logging
import pprint

from freckles import Freck
from freckles.constants import *
from freckles.runners.ansible_runner import (FRECK_META_ROLE_KEY,
                                             FRECK_META_ROLES_KEY)
from freckles.utils import create_dotfiles_dict, parse_dotfiles_item
from task import AbstractTask
from voluptuous import ALLOW_EXTRA, Required, Schema

log = logging.getLogger("freckles")

PRECENDENCE_ERROR_STRING = "Possible precedence issue with control flow operator at"
DEFAULT_STOW_SUDO = False
DEFAULT_STOW_TARGET_BASE_DIR = os.path.expanduser("~/")
STOW_TARGET_BASE_DIR_KEY = "stow_target_dir"
FRECKLES_DEFAULT_STOW_ROLE_NAME = "stow-pkg"
FRECKLES_DEFAULT_STOW_ROLE_URL = "frkl:ansible-stow"

NO_STOW_MARKER_FILENAME = ".no_stow.frkl"

class Stow(AbstractTask):

    def get_config_schema(self):
        s = Schema({
            Required(DOTFILES_KEY): list
        }, extra=ALLOW_EXTRA)

        return s

    def process_leaf(self, leaf, supported_runners=[FRECKLES_DEFAULT_RUNNER], debug=False):

        config = leaf[FRECK_VARS_KEY]
        dotfiles = parse_dotfiles_item(config[DOTFILES_KEY])

        target_dir = config.get("stow_target_dir", False)
        if target_dir:
            target_dir = os.path.expanduser(target_dir)
        else:
            target_dir = os.path.expanduser("~")

        apps = create_dotfiles_dict(dotfiles, default_details=config)
        result = []
        for app, details in apps.iteritems():

            base_dir = details[DOTFILES_BASE_KEY]
            folder = os.path.join(base_dir, app)
            no_stow_marker_file = os.path.join(folder, NO_STOW_MARKER_FILENAME)

            if os.path.exists(no_stow_marker_file):
                log.debug("stow: ignoring folder (because it contains '{}'-marker file): {}".format(NO_STOW_MARKER_FILENAME, folder))
                continue

            meta = {}
            meta[FRECK_META_ROLES_KEY] = {"stow": "frkl:ansible-stow"}
            meta[TASK_NAME_KEY] = "stow"
            meta[FRECK_ITEM_NAME_KEY] = app
            meta[FRECK_DESC_KEY] = "stow - {} -> {}".format(base_dir, target_dir)
            meta[FRECK_VARS_KEY] = {
                "name": details[FRECK_ITEM_NAME_KEY],
                "source_dir": base_dir,
                "target_dir": target_dir
            }

            result.append(meta)

        return (FRECKLES_ANSIBLE_RUNNER, result)


    def handle_task_output(self, task, output_details):

        output = super(Stow, self).handle_task_output(task, output_details)
        stdout = []
        stderr = []

        if output["state"] == FRECKLES_STATE_FAILED:
            for output in output_details:
                for line in output["result"]["msg"].split("\n"):
                    stderr.append(line)
        else:
            # flatten stderr sublist
            lines = [item for sublist in [entry.split("\n") for entry in output["stderr"]] for item in sublist]

            for line in lines:
                if not line or line.startswith(PRECENDENCE_ERROR_STRING):
                    continue
                elif line.startswith("LINK") or line.startswith("UNLINK"):
                    stdout.append(line)
                else:
                    stderr.append(line)

        output[FRECKLES_STDOUT_KEY] = stdout
        output[FRECKLES_STDERR_KEY] = stderr

        return output

    def default_freck_config(self):

        return {
            FRECK_SUDO_KEY: DEFAULT_STOW_SUDO,
            STOW_TARGET_BASE_DIR_KEY: DEFAULT_STOW_TARGET_BASE_DIR,
            FRECK_RUNNER_KEY: FRECKLES_ANSIBLE_RUNNER,
            FRECK_META_ROLES_KEY: {FRECKLES_DEFAULT_STOW_ROLE_NAME: FRECKLES_DEFAULT_STOW_ROLE_URL},
            FRECK_META_ROLE_KEY: FRECKLES_DEFAULT_STOW_ROLE_NAME
        }
