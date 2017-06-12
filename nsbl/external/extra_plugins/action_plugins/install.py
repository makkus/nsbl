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
import json
import pprint
from six import string_types
import frkl
from ansible import constants as C
from ansible.errors import AnsibleError, AnsibleFileNotFound
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.plugins.action import ActionBase
from ansible.template import generate_ansible_template_vars
from ansible.utils.hashing import checksum_s
import sys

from nsbl.nsbl import get_pkg_mgr_sudo, ensure_git_repo_format
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

USE_TOP_LEVEL_AS_PKG_NAME = False

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        ''' handler for template operations '''

        self.nsbl_env = os.environ.get("NSBL_ENVIRONMENT", False) == "true"

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        format = {"child_marker": "packages",
              "default_leaf": "vars",
              "default_leaf_key": "name",
              "key_move_map": {'*': "vars"}}
        chain = [frkl.FrklProcessor(format)]

        frkl_obj = frkl.Frkl(self._task.args["packages"], chain)

        package = frkl_obj.process()
        if len(package) == 0:
            raise Exception("No packages provided for package: {}".format(self._task.args["packages"]))
        if len(package) != 1:
            raise Exception("For some reason more than one package provided, this shouldn't happen: {}".format(package))

        package = package[0]

        if "pkg_mgr" not in package[VARS_KEY].keys():
            pkg_mgr = self._task.args.get('pkg_mgr', 'auto')
        else:
            pkg_mgr = package[VARS_KEY]["pkg_mgr"]

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

        if pkg_mgr not in self._shared_loader_obj.module_loader:
            result['failed'] = True
            result['msg'] = 'Could not find a module for %s.' % pkg_mgr
            return result

        # calculate package name, just in case
        pkg_dict = CaseInsensitiveDict(package[VARS_KEY].get("pkgs"))
        if not auto:
            if pkg_mgr.lower() in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict[pkg_mgr.lower()]
            elif 'other' in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict['other']
            else:
                calculated_package = None
        else:
            if full_version_string in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict[full_version_string]
            elif full_release_string in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict[full_release_string]
            elif distribution_major_string in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict[distribution_major_string]
            elif distribution_string in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict[distribution_string]
            elif os_string in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict[os_string]
            elif 'other' in (name.lower() for name in pkg_dict.keys()):
                calculated_package = pkg_dict['other']
            else:
                calculated_package = None

        if calculated_package in ['ignore', 'omit']:
            result['msg'] = "Ignoring package {}".format(package[VARS_KEY]["name"])
            result['skipped'] = True
            return result

        module_result = self.execute_package_module_new(package, calculated_package, auto, pkg_mgr, task_vars, result)

        if module_result:
            result.update(module_result)

        return result

    def prepare_git(self, package, calculated_package, task_vars, result):
        if calculated_package:
            calculated_package = ensure_git_repo_format(calculated_package)
            # we can be sure pkg_name is now a dict
            return {calculated_package["repo"]: calculated_package}
        else:
            if "repo" in package.keys():
                temp = ensure_git_repo_format(package["repo"], package.get("dest", None))
            else:
                temp = ensure_git_repo_format(package["name"], package.get("dest", None))

            return {temp["repo"]: temp}

    def prepare_generic(self, package, calculated_package, pkg_mgr, task_vars, result):

        result = {}
        if calculated_package:
            if not isinstance(calculated_package, (list, tuple)):
                calculated_package = [calculated_package]
            for pkg in calculated_package:
                result[pkg] = {"name": pkg}
        else:
            temp = package["name"]
            result[temp] = {"name": temp}

        return result

    def execute_package_module_new(self, package, calculated_package, auto, pkg_mgr, task_vars, result):

        if pkg_mgr == 'git':
            pkg_vars = self.prepare_git(package[VARS_KEY], calculated_package, task_vars, result)
        else:
            pkg_vars = self.prepare_generic(package[VARS_KEY], calculated_package, pkg_mgr, task_vars, result)

        msgs = []
        overall_changed = False
        overall_failed = False

        installed = []
        skipped = []
        failed = []

        runs = []
        for pkg_id, pkg_vars in pkg_vars.items():
            if package[VARS_KEY].get("no_install", False):
                skipped.append(pkg_id)
                run = {"skipped": True, "msg": "Package '{}' tagged with 'no_install', ignoring".format(pkg_id)}
                runs.append(run)
                continue

            #display.display("nsbl: installing {}".format(pkg_id))

            new_module_args = {}
            keys = PKG_MGR_VARS.get(pkg_mgr, None)
            if not keys:
                keys = DEFAULT_PKG_MGR_VARS

            for key in keys:
                if key in package[VARS_KEY].keys():
                    new_module_args[key] = package[VARS_KEY][key]
                else:
                    if key in self._task.args.keys():
                        new_module_args[key] = self._task.args[key]

            new_module_args.update(pkg_vars)

            display.vvvv("Running %s" % pkg_mgr)
            if self.nsbl_env:
                output = {"category": "nsbl_item_started", "item": "{} (using: {})".format(pkg_id, pkg_mgr)}
                # env_id = task_vars['vars'].get('_env_id', None)
                # if env_id != None:
                    # msg["_env_id"] = env_id
                # task_id = task_vars['vars'].get('_tasks_id', None)
                # if task_id != None:
                    # msg["_task_id"] = task_id
                display.display(json.dumps(output))
            self._play_context.become = get_pkg_mgr_sudo(pkg_mgr)
            run = self._execute_module(module_name=pkg_mgr, module_args=new_module_args, task_vars=task_vars, wrap_async=self._task.async)

            runs.append(run)

            if "failed" in run.keys():
                run_failed = run["failed"]
            else:
                run_failed = False

            if run_failed:
                failed.append(pkg_id)
                overall_failed = True

            if "changed" in run.keys():
                changed = run["changed"]
            else:
                changed = False

            if "msg" in run.keys():
                run_msg = run['msg']
                msgs.append(run_msg)
            else:
                run_msg = None

            if changed:
                overall_changed = True
                installed.append(pkg_id)
            elif not run_failed:
                skipped.append(pkg_id)

            if self.nsbl_env:
                output = {"item": "{} (using: {})".format(pkg_id, pkg_mgr)}
                if run_msg:
                    output["msg"] = run_msg
                if run_failed:
                    output["failed"] = True
                    output["category"] = "nsbl_item_failed"
                else:
                    output["category"] = "nsbl_item_ok"
                    output["changed"] = changed

                display.display(json.dumps(output))


        if len(pkg_vars) == 1:
            return runs[0]
        else:
            msg = "Installed: {}, Skipped: {}, Failed: {}".format(installed, skipped, failed)
            runs_result = {"changed": overall_changed, "msg": msg, "failed": overall_failed, "runs": runs}
            return runs_result



    def execute_package_module(self, name, auto, pkg_mgr, task_vars, result, full_version_string, full_release_string, distribution_major_string, distribution_string, os_string):

        if isinstance(name, string_types) and pkg_mgr != 'git':
            pkg_name = name

        else:

            if not auto:

                if pkg_mgr == 'git':
                    pkg_name = ensure_git_repo_format(name, self._task.args.get("dest", None))
                else:
                    if not isinstance(name, dict):
                        result['failed'] = True
                        result['msg'] = "Wrong value for 'name', only string or dict allowed: {}".format(name)
                        return result

                    if not len(name) == 1:
                        result['failed'] = True
                        result['msg'] = "Only dicts of length 1 allowed for package name hierarchy: {}".format(name)
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
                    result['msg'] = "Only dicts of length 1 allowed for package name hierarchy: {}".format(name)
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

        if pkg_mgr != 'git' and pkg_name is None:
            if USE_TOP_LEVEL_AS_PKG_NAME:
                pkg_name = meta_name
            else:
                result['msg'] = "Ignoring package {} for package manager {}, no entry in package hierarchy found.".format(meta_name, pkg_mgr)
                return result

        if self._task.args.get('no_install', False):
            result['changed'] = False
            result['failed'] = False
            result['msg'] = "Package {} tagged as 'no_install', doing nothing...".format(pkg_name)
            return result

        # run the 'package' pkg_mgr
        new_module_args = {}
        keys = PKG_MGR_VARS.get(pkg_mgr, None)
        if not keys:
            keys = DEFAULT_PKG_MGR_VARS

        for key in keys:
            if key in self._task.args.keys():
                new_module_args[key] = self._task.args[key]

        if pkg_mgr != 'git':
            if pkg_mgr == 'apt' and pkg_name.endswith(".deb"):
                new_module_args.pop('name', None)
                new_module_args["deb"] = pkg_name
            else:
                new_module_args["name"] = pkg_name
        else:
            new_module_args.update(pkg_name)
            if "repo" in new_module_args.keys():
                new_module_args.pop('name', None)

        display.vvvv("Running %s" % pkg_mgr)
        self._play_context.become = get_pkg_mgr_sudo(pkg_mgr)
        result.update(self._execute_module(module_name=pkg_mgr, module_args=new_module_args, task_vars=task_vars, wrap_async=self._task.async))

        return result
