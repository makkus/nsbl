# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
import signal
import subprocess
import sys
import time

import click
import pexpect

from .output import CursorOff, NsblLogCallbackAdapter, NsblPrintCallbackAdapter


log = logging.getLogger("nsbl")

DEFAULT_PEXPECT_TIMEOUT = 36000


class NsblRunner(object):

    def __init__(self, nsbl):
        """Class to kick off rendering and running the ansible environment in question.

        Args:
          nsbl (Nsbl): the Nsbl object holding the (processed) configuration
        """
        self.nsbl = nsbl

    def run(
        self,
        target,
        global_vars=None,
        force=True,
        ansible_args="",
        ask_become_pass=None,
        password=None,
        secure_vars=None,
        callback=None,
        add_timestamp_to_env=False,
        add_symlink_to_env=False,
        no_run=False,
        display_sub_tasks=True,
        display_skipped_tasks=True,
        display_ignore_tasks=[],
        pre_run_callback=None,
        extra_paths="",
    ):
        """Starts the ansible run, executing all generated playbooks.

        By default the 'nsbl_internal' ansible callback is used, which outputs easier to read outputs/results. You can, however,
        also use the callbacks that come with ansible, like 'default', 'skippy', etc.

        Args:
          target (str): the target directory where the ansible environment should be rendered
          global_vars (dict): vars to be rendered on top of each playbook
          force (bool): whether to overwrite potentially existing files at the target (most likely an old rendered ansible environment)
          ansible_args (str): verbosity arguments to ansible-playbook command
          ask_become_pass (bool): whether to include the '--ask-become-pass' arg to the ansible-playbook call
          password (str): if provided, it will be used instead of asking for a password
          secure_vars (dict): other vars to keep secure, not implemented yet
          callback (str): the callback to use for the ansible run. default is 'default'
          add_timestamp_to_env (bool): whether to append a timestamp to the run directory (default: False)
          add_symlink_to_env (str): whether to add a symlink to the run directory (will be deleted if exists already and force is specified) - default: False, otherwise path to symlink
          no_run (bool): whether to only render the environment, but not run it
          display_sub_tasks (bool): whether to display subtasks in the output (not applicable for all callbacks)
          display_skipped_tasks (bool): whether to display skipped tasks in the output (not applicable for all callbacks)
          display_ignore_tasks (list): a list of strings that indicate task titles that should be ignored when displaying the task log (using the default nsbl output plugin -- this is ignored with other output callbacks)
          pre_run_callback (function): a callback to execute after the environment is rendered, but before the run is kicked off
          extra_paths (str): a colon-separated of extra paths that should be exported for the nsbl run

        Return:
          dict: the parameters of the run
        """
        if callback is None:
            callback = "default"

        if callback == "nsbl_internal":
            lookup_dict = self.nsbl.get_lookup_dict()
            callback_adapter = NsblLogCallbackAdapter(
                lookup_dict,
                display_sub_tasks=display_sub_tasks,
                display_skipped_tasks=display_skipped_tasks,
                display_ignore_tasks=display_ignore_tasks,
            )
        else:
            callback_adapter = NsblPrintCallbackAdapter()

        try:
            parameters = self.nsbl.render(
                target,
                global_vars=global_vars,
                extract_vars=True,
                force=force,
                ask_become_pass=ask_become_pass,
                password=password,
                secure_vars=secure_vars,
                ansible_args=ansible_args,
                callback=callback,
                add_timestamp_to_env=add_timestamp_to_env,
                add_symlink_to_env=add_symlink_to_env,
                extra_paths=extra_paths,
            )

            env_dir = parameters["env_dir"]
            if pre_run_callback:
                pre_run_callback(env_dir)

            if no_run:
                log.debug("Not running environment due to 'no_run' flag set.")
                return parameters

            run_env = os.environ.copy()
            if callback.startswith("nsbl_internal"):
                run_env["NSBL_ENVIRONMENT"] = "true"

            def preexec_function():
                # Ignore the SIGINT signal by setting the handler to the standard
                # signal handler SIG_IGN.
                signal.signal(signal.SIGINT, signal.SIG_IGN)

            script = parameters["run_playbooks_script"]

            if password is None:
                proc = subprocess.Popen(
                    script,
                    stdout=subprocess.PIPE,
                    stderr=sys.stdout.fileno(),
                    stdin=subprocess.PIPE,
                    shell=True,
                    env=run_env,
                    preexec_fn=preexec_function,
                )
                with CursorOff():
                    click.echo("")

                    for line in iter(proc.stdout.readline, ""):
                        callback_adapter.add_log_message(line)

                    callback_adapter.finish_up()

                while proc.poll() is None:
                    # Process hasn't exited yet, let's wait some
                    time.sleep(0.5)

                # Get return code from process
                return_code = proc.returncode
                parameters["return_code"] = return_code
                parameters["signal_status"] = -1

            else:
                with CursorOff():
                    proc = pexpect.spawn(
                        "/bin/bash -c {}".format(script),
                        env=run_env,
                        preexec_fn=preexec_function,
                    )
                    proc.expect("SUDO password:")
                    proc.timeout = DEFAULT_PEXPECT_TIMEOUT
                    proc.sendline(password)
                    proc.logfile = callback_adapter
                    proc.logfile_send = None
                    proc.expect(pexpect.EOF)
                    proc.close()

                    callback_adapter.finish_up()

                return_code = proc.exitstatus
                signal_status = proc.signalstatus

                parameters["return_code"] = return_code
                parameters["signal_status"] = signal_status

        except KeyboardInterrupt:
            parameters["return_code"] = 11
            parameters["signal_status"] = -1
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            print()
            print()
            callback_adapter.add_error_message(
                "Keyboard interrupt received. Exiting..."
            )
            print()
            pass

        return parameters
