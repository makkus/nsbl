import fnmatch
import os
import subprocess

from ansible.module_utils.basic import *
from ansible.module_utils.basic import AnsibleModule

OTHER_PATHS_TO_CHECK = [
    os.path.expanduser("~/.local/bin")
]

def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        temp = []
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

        for path in OTHER_PATHS_TO_CHECK:
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

def missing_from_path(module, exe):

        exe_missing = which(exe) is None
        if exe_missing or exe != 'git':
            return exe_missing
        else:
            # needed because Mac OS has some sort of wrapper script for git if xcode is not installed
            try:
                git_output = module.run_command(['git', '--help'], check_rc=False)
                #git_output = "xcode-select"
                if "xcode-select" in git_output:
                    return True
                else:
                    return False
            except:
                return True

def main():
    module = AnsibleModule(
        argument_spec = dict(
            executables_to_check = dict(required=True, type='list')
        ),
        supports_check_mode=False
    )

    p = module.params

    executable_facts = {}

    executable_missing = []
    for exe in p.get('executables_to_check', []):
        if missing_from_path(module, exe):
            executable_missing.append(exe)
    executable_facts['executables_missing'] = executable_missing

    module.exit_json(changed=False, ansible_facts=dict(executable_facts))

if __name__ == '__main__':
    main()
