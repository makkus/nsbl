from __future__ import absolute_import, division, print_function

import errno
import os
import sys

from ansible.module_utils._text import to_bytes, to_text
from ansible.plugins.callback.default import \
    CallbackModule as CallbackModule_default
from ansible.utils.color import stringc
from ansible.utils.display import Display

__metaclass__ = type


class FileWriter(Display):

    def __init__(self, log_file, verbosity=4):
        self.log_file = log_file
        super(FileWriter, self).__init__(verbosity)

    def display(self, msg, color=None, stderr=False, screen_only=False, log_only=False):
        """ Display a message to the user
        Note: msg *must* be a unicode string to prevent UnicodeError tracebacks.
        """

        msg2 = msg.lstrip(u'\n')

        msg2 = to_bytes(msg2)

        # We first convert to a byte string so that we get rid of
        # characters that are invalid in the user's locale
        msg2 = to_text(msg2, self._output_encoding(stderr=stderr))

        #print(msg2, file=self.log_file)
        with open(self.log_file, "ab+") as fd:
            fd.write("{}\n".format(msg))


class CallbackModule(CallbackModule_default):  # pylint: disable=too-few-public-methods,no-init
    '''
    Override for the default callback module.
    Render std err/out outside of the rest of the result which it prints with
    indentation.
    '''
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'default_to_file'

    def __init__(self):

        self._play = None
        self._last_task_banner = None
        super(CallbackModule, self).__init__()

        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs", "run_log_ansible.log")

        self._display = FileWriter(log_file)
