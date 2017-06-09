from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.plugins.action import ActionBase
from requests.structures import CaseInsensitiveDict

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()

import os
import pprint
from six import string_types

from ansible import constants as C
from ansible.errors import AnsibleError, AnsibleFileNotFound
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.plugins.action import ActionBase
from ansible.template import generate_ansible_template_vars
from ansible.utils.hashing import checksum_s
import sys

from nsbl.nsbl import get_pkg_mgr_sudo
boolean = C.mk_boolean


PKG_MGR_VARS = {
    'apt': ["name", "state", "allow_unauthenticated", "autoclean", "autoremove", "cache_valid_time", "deb", "default_release", "dpkg_options", "force", "install_recommends", "only_upgrades", "purge", "update_cache", "upgrade"],
    'yum': ["name", "state", "conf_file", "disable_gpg_check", "disablerepo", "enablerepo", "exclude", "installroot", "skip_broken", "update_cache", "validate_certs"],
    'nix': ["name", "state"]
}

DEFAULT_PKG_MGR_VARS = ["name", "state"]

USE_TOP_LEVEL_AS_PKG_NAME = False

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        ''' handler for template operations '''

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)

        pkg_mgr = self._task.args.get('pkg_mgr', 'auto')

        if pkg_mgr == 'auto':
            try:
                if self._task.delegate_to:
                    pkg_mgr = self._templar.template("{{hostvars['%s']['ansible_facts']['ansible_pkg_mgr']}}" % self._task.delegate_to)
                else:
                    pkg_mgr = self._templar.template('{{ansible_facts["ansible_pkg_mgr"]}}')
            except Exception as e:
                pass  # could not get it from template!

        auto = False
        if pkg_mgr == 'auto':
            auto = True
            facts = self._execute_module(module_name='setup', module_args=dict(gather_subset='!all'), task_vars=task_vars)
            pkg_mgr = facts['ansible_facts']['ansible_pkg_mgr']
            os_family = facts['ansible_facts']['ansible_os_family']
            distribution = facts['ansible_facts']['ansible_distribution']
            distribution_major_version = facts['ansible_facts']['ansible_distribution_major_version']
            distribution_version = facts['ansible_facts']['ansible_distribution_version']
            distribution_release = facts['ansible_facts']['ansible_distribution_release']
            # figure out actual package name
            full_version_string = "{}-{}".format(distribution, distribution_version).lower()
            full_release_string = "{}-{}".format(distribution, distribution_release).lower()
            distribution_major_string = "{}-{}".format(distribution, distribution_major_version).lower()

            distribution_string = distribution.lower()
            os_string = os_family.lower()
        else:
            os_family = None
            distribution = None
            distribution_major_version = None
            distribution_version = None
            distribution_release = None
            full_version_string = None
            full_release_string = None
            distribution_major_string = None
            distribution_string = None
            os_string = None

        # TODO: error
        if pkg_mgr == 'auto':
            result['failed'] = True
            result['msg'] = 'Could not detect which package manager to use. Try gathering facts or setting the "use" option.'
            return result


        name = self._task.args.get("name", None)

        if not name:
            result['failed'] = True
            result['msg'] = "No name provided for package"
            return result

        if pkg_mgr not in self._shared_loader_obj.module_loader:
            result['failed'] = True
            result['msg'] = 'Could not find a module for %s.' % pkg_mgr
            return result

        if isinstance(name, (list, tuple)):
            for n in name:
                self.execute_package_module(n, auto, pkg_mgr, task_vars, result, full_version_string, full_release_string, distribution_major_string, distribution_string, os_string)
        else:
            self.execute_package_module(name, auto, pkg_mgr, task_vars, result, full_version_string, full_release_string, distribution_major_string, distribution_string, os_string)

        return result

    def execute_package_module(self, name, auto, pkg_mgr, task_vars, result, full_version_string, full_release_string, distribution_major_string, distribution_string, os_string):

        if isinstance(name, string_types):
            pkg_name = name

        else:

            if not auto:

                if not isinstance(name, dict):
                    result['failed'] = True
                    result['msg'] = "Wrong value for 'name', only string or dict allowed: {}".format(name)
                    return result

                if not len(name) == 1:
                    result['failed'] = True
                    result['msg'] = "Only dicts of length 1 allowed for package name hierarchy"
                    return result

                meta_name = next(iter(name))

                pkg_dict = CaseInsensitiveDict(name[meta_name])

                if pkg_mgr.lower() in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict[pkg_mgr.lower()]
                elif 'default' in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict['default']
                else:
                    pkg_name = None

            else:
                if not isinstance(name, dict):
                    result['failed'] = True
                    result['msg'] = "Wrong value for 'name', only string or dict allowed: {}".format(name)
                    return result

                if not len(name) == 1:
                    result['failed'] = True
                    result['msg'] = "Only dicts of length 1 allowed for package name hierarchy"
                    return result

                meta_name = next(iter(name))

                pkg_dict = CaseInsensitiveDict(name[meta_name])

                if full_version_string in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict[full_version_string]
                elif full_release_string in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict[full_release_string]
                elif distribution_major_string in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict[distribution_major_string]
                elif distribution_string in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict[distribution_string]
                elif os_string in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict[os_string]
                elif 'default' in (name.lower() for name in pkg_dict.keys()):
                    pkg_name = pkg_dict['default']
                else:
                    pkg_name = None

        if pkg_name is None:
            if USE_TOP_LEVEL_AS_PKG_NAME:
                pkg_name = meta_name
            else:
                result['msg'] = "Ignoring package {} for package manager {}, no entry in package hierarchy found.".format(meta_name, pkg_mgr)
                return result

        # run the 'package' pkg_mgr
        new_module_args = {}
        keys = PKG_MGR_VARS.get(pkg_mgr, None)
        if not keys:
            keys = DEFAULT_PKG_MGR_VARS

        for key in keys:
            if key in self._task.args.keys():
                new_module_args[key] = self._task.args[key]

        if pkg_mgr == 'apt' and pkg_name.endswith(".deb"):
            new_module_args.pop('name', None)
            new_module_args["deb"] = pkg_name
        else:
            new_module_args["name"] = pkg_name

        display.vvvv("Running %s" % pkg_mgr)
        self._play_context.become = get_pkg_mgr_sudo(pkg_mgr)
        result.update(self._execute_module(module_name=pkg_mgr, module_args=new_module_args, task_vars=task_vars, wrap_async=self._task.async))

        return result
