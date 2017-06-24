from __future__ import absolute_import, division, print_function

import os
import pprint
import sys

from ansible import constants as C
from ansible.errors import AnsibleError, AnsibleFileNotFound
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.plugins.action import ActionBase
from ansible.template import generate_ansible_template_vars
from ansible.utils.hashing import checksum_s
from requests.structures import CaseInsensitiveDict
from six import string_types

from nsbl.nsbl import ensure_git_repo_format, get_pkg_mgr_sudo

__metaclass__ = type


try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()



boolean = C.mk_boolean

VARS_KEY = "vars"

PKG_MGR_VARS = {
    'apt': ["name", "state", "allow_unauthenticated", "autoclean", "autoremove", "cache_valid_time", "deb", "default_release", "dpkg_options", "force", "install_recommends", "only_upgrades", "purge", "update_cache", "upgrade"],
    'yum': ["name", "state", "conf_file", "disable_gpg_check", "disablerepo", "enablerepo", "exclude", "installroot", "skip_broken", "update_cache", "validate_certs"],
    'nix': ["name", "state"],
    'git': ["accept_hostkey", "archive", "bare", "clone", "depth", "dest", "executable", "force", "key_file", "recursive", "reference", "refspec", "repo", "ssh_opts", "track_submodules", "umask", "update", "verify_commit", "version"],
    'pip': ["chdir", "editable", "executable", "extra_args", "name", "requirements", "state", "umask", "version", "virtualenv", "virtualenv_command", "virtualenv_python", "virtualenv_site_packages"]
}

DEFAULT_PKG_MGR_VARS = ["name", "state"]
SUPPORTED_PKG_MGRS = ["nix"]
USE_TOP_LEVEL_AS_PKG_NAME = False

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        ''' handler for template operations '''

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        pkg_mgr = self._task.args["pkg_mgr"]

        if pkg_mgr not in SUPPORTED_PKG_MGRS:
            result['msg'] = "'{}' not supported for pkg_mgr auto-install, skipping...".format(pkg_mgr)
            result['skipped'] = True
            return result

        install_pkg_mgr_role_name = "install-{}".format(pkg_mgr)
        print(install_pkg_mgr_role_name)
        pprint.pprint(task_vars)
        run = self._execute_module(module_name="include_role", module_args={"name": install_pkg_mgr_role_name}, task_vars=task_vars, wrap_async=self._task.async)
        pprint.pprint(run)
        # raise Exception("XXX")

        # facts = self._execute_module(module_name='setup', module_args=dict(gather_subset='!all'), task_vars=task_vars)
        # if pkg_mgr not in self._shared_loader_obj.module_loader:
            # result['failed'] = True
            # result['msg'] = 'Could not find a module for %s.' % pkg_mgr
            # return result

        result.update(run)
        return result
