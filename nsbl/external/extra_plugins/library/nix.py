#!/usr/bin/python -tt
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
---
module: nix
short_description: Manage packages with Nix
'''

EXAMPLES = '''
# Install package foo
- nix: name=foo state=present
'''

import json
import os
from distutils.spawn import find_executable

from ansible.module_utils.basic import *

NIX_PATH = os.path.join(os.environ['HOME'], ".nix-profile")
SINGLE_USER_NIX_PATH = os.path.join(NIX_PATH, "bin")
MULTI_USER_MAC_NIX_PATH = "/nix/var/nix/profiles/default/bin"

POTENTIAL_NIX_PATHS = [SINGLE_USER_NIX_PATH, MULTI_USER_MAC_NIX_PATH]

SINGLE_USER_SOURCE_PATH = os.path.join(NIX_PATH, 'etc', "profile.d", "nix.sh")
MULTI_USER_SOURCE_PATH = "/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh"
POTENTIAL_SOURCE_FILES = [SINGLE_USER_SOURCE_PATH, MULTI_USER_SOURCE_PATH]

# NIX_SOURCE_PATH = os.path.join(NIX_PATH, 'etc', 'profile.d', 'nix.sh')
# NIX_ENV_PATH = os.path.join(NIX_PATH, "bin", "nix-env")
# NIX_CHANNEL_PATH = os.path.join(NIX_PATH, "bin", "nix-channel")

# this creates the nix env in case the run was started without that environment set
WRAP = True

BIN_CACHE = {}

def get_source_file(module):

    for source_file in POTENTIAL_SOURCE_FILES:
        if os.path.exists(source_file):
            return source_file

    module.fail_json(msg="Could not find nix source environment.")

def get_nix_bin(module, bin_name):

    nix_bin = BIN_CACHE.get(bin_name, False)

    if not nix_bin:

        nix_bin = find_executable(bin_name)
        if not nix_bin:
            tried = []
            for path in POTENTIAL_NIX_PATHS:
                tried.append(path)
                if os.path.isfile(os.path.join(path, bin_name)):
                    nix_bin = os.path.join(path, bin_name)

        if not nix_bin:
            module.fail_json(msg="Could not find nix environment for executable '{}', tried: {}".format(bin_name, tried))

        BIN_CACHE[bin_name] = nix_bin

    return nix_bin



def query_package(module, name, state="present"):
    if state == "present":
        if WRAP:
            cmd = 'bash -c "source {}; {} -q {}"'.format(get_source_file(module), get_nix_bin(module, "nix-env"), name)
        else:
            cmd = "{} -q {}".format(get_nix_bin(module, "nix-env"), name)


        rc, stdout, stderr = module.run_command(cmd, check_rc=False)

        if rc == 0:
            return True

        return False

def update_cache(module):

    if WRAP:
        cmd = 'bash -c "source {}; {} --update"'.format(get_source_file(module), get_nix_bin(module, "nix-channel"))
    else:
        cmd = "{} --update".format(get_nix_bin(module, "nix-channel"))

    rc, stdout, stderr = module.run_command(cmd, check_rc=False)
    if rc != 0:
        module.fail_json(msg="failed to update cache: {} {}".format(stderr))

    module.exit_json(changed=True, msg="Updated nix cache.")

def upgrade_packages(module):

    if WRAP:
        cmd = 'bash -c "source {}; {} --upgrade"'.format(get_source_file(module), get_nix_bin(module, "nix-env"))
    else:
        cmd = "{} --upgrade".format(get_nix_bin(module, "nix-env"))

    rc, stdout, stderr = module.run_command(cmd, check_rc=False)
    if rc != 0:
        module.fail_json(msg="failed to upgrade packages: {}".format(stderr))

    module.exit_json(changed=True, msg="Upgraded nix packages.")

def install_packages(module, packages):
    install_c = 0

    if module.check_mode:
        for i, package in enumerate(packages):
            if query_package(module, package):
                continue
            else:
                module.exit_json(changed=True, name=package)

        module.exit_json(changed=False, name=packages)

    for i, package in enumerate(packages):
        if query_package(module, package):
            continue

        if WRAP:
            cmd = 'bash -c "source {}; {} -i {}"'.format(get_source_file(module), get_nix_bin(module, "nix-env"), package)
        else:
            cmd = "{} -i {}".format(get_nix_bin(module, "nix-env"), package)

        rc, stdout, stderr = module.run_command(cmd, check_rc=False)

        if rc != 0:
            module.fail_json(msg="failed to install {}: {}".format(package, stderr))

        install_c += 1

    if install_c > 0:
        module.exit_json(changed=True, msg="installed %s package(s)" % (install_c))

    module.exit_json(changed=False, msg="package(s) already installed")

def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(aliases=['pkg', 'package']),
            upgrade = dict(default=False, type='bool'),
            update_cache = dict(default=False, aliases=['update-cache'], type='bool'),
            state=dict(default='present', choices=['present', 'installed', 'absent', 'removed'])),
        required_one_of=[['name', 'upgrade', 'update_cache']],
        mutually_exclusive=[['name', 'upgrade']],
        supports_check_mode=True)

    if not os.path.exists(get_nix_bin(module, "nix-env")):
        module.fail_json(msg="cannot find nix-env, looking for %s" % (get_nix_bin(module, "nix-env")))

    p = module.params

    # normalize the state parameter
    if p['state'] in ['present', 'installed']:
        p['state'] = 'present'
    elif p['state'] in ['absent', 'removed']:
        p['state'] = 'absent'

    if p['update_cache']:
        update_cache(module)

    if p['upgrade']:
        upgrade_packages(module)

    if p['name']:
        pkgs = p['name'].split(',')

        if p['state'] == 'present':
            install_packages(module, pkgs)

if __name__ == '__main__':
    main()
