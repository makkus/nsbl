
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

POTENTIAL_CONDA_PATHS = [
    os.path.expanduser("~/.freckles/opt/conda/bin")
]

def get_conda_bin(module):

    conda_bin = find_executable('conda')
    if not conda_bin:
        for path in POTENTIAL_CONDA_PATHS:
            if os.path.isfile(os.path.join(path, 'conda')):
                conda_bin = os.path.join(path, 'conda')

    if not conda_bin:
        module.fail_json(msg="Could not find conda environment.")

    return conda_bin

def get_environment_paraemter(environment):

    if environment:
        return "--name {}".format(environment)
    else:
        return ""

def ensure_environment(module, environment):

    if environment == "root":
        return

    cmd = "{} info --json ".format(get_conda_bin(module))
    rc, stdout, stderr = module.run_command(cmd)

    if rc != 0:
        return module.fail_json(msg="Can't list conda envs: {}".format(stderr))

    info = json.loads(stdout)

    envs_dirs = info["envs_dirs"]
    for env_dir in envs_dirs:
        dir = os.path.join(env_dir, environment)
        if os.path.isdir(dir):
            return

    cmd = "{} create -y --name {}".format(get_conda_bin(module), environment)
    rc, stdout, stderr = module.run_command(cmd)

    if rc != 0:
        return module.fail_json(msg="Can't create conda env '{}': {}".format(environment, stderr))


def get_channel_parameters(channels):

    if not channels:
        return ""
    else:
        result = ""
        for c in channels:
            result += "--channel {} ".format(c)

        return result

def upgrade_packages(module, environment=None, channels=None):

    cmd = "{} update -y {} {} --all".format(get_conda_bin(module), get_channel_parameters(channels), get_environment_paraemter(environment))
    rc, stdout, stderr = module.run_command(cmd, check_rc=False)
    if rc != 0:
        module.fail_json(msg="failed to upgrade conda packages: {}".format(stderr))

    module.exit_json(changed=True, msg="Upgraded conda packages.")

def query_package(module, name, environment):

    cmd = "{} list --json {} -f {}".format(get_conda_bin(module), get_environment_paraemter(environment), name)
    rc, stdout, stderr = module.run_command(cmd)

    if rc != 0:
        return False

    packages = json.loads(stdout)
    if not packages:
        return False
    else:
        return True

def install_packages(module, packages, env=None, channels=None):

    if module.check_mode:
        for i, package in enumerate(packages):
            if query_package(module, package, env):
                continue
            else:
                module.exit_json(changed=True, name=package)

        module.exit_json(changed=False, name=packages)

    install_c = 0
    ensure_environment(module, env)
    for i, package in enumerate(packages):
        if query_package(module, package, env):
            continue

        cmd = "{} install -y {} {} {}".format(get_conda_bin(module), get_environment_paraemter(env), get_channel_parameters(channels), package)
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
            channels = dict(default=False, type='list', required=False),
            environment = dict(default="root", type='str', required=False),
            state=dict(default='present', choices=['present', 'installed', 'absent', 'removed'])),
        required_one_of=[['name', 'upgrade']],
        mutually_exclusive=[['name', 'upgrade']],
        supports_check_mode=True)

    # check for conda
    get_conda_bin(module)

    p = module.params

    # normalize the state parameter
    if p['state'] in ['present', 'installed']:
        p['state'] = 'present'
    elif p['state'] in ['absent', 'removed']:
        p['state'] = 'absent'

    if p['upgrade']:
        upgrade_packages(module, module.params.get("environment", None), module.params.get("channels", None))

    if p['name']:
        pkgs = p['name'].split(',')

        if p['state'] == 'present':
            install_packages(module, pkgs, module.params.get("environment", None), module.params.get("channels", None))

if __name__ == '__main__':
    main(
)
