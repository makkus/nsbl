from __future__ import absolute_import, division, print_function

import datetime
import decimal
import json
import pprint
import uuid

import ansible
from ansible import constants as C
from ansible.executor.task_result import TaskResult
from ansible.playbook.task_include import TaskInclude
from ansible.plugins.callback import CallbackBase
from six import string_types

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


__metaclass__ = type

class CallbackModule(CallbackBase):
    """
    Forward task, play and result objects to freckles.
    """
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'stdout'
    CALLBACK_NAME = 'freckles_callback'
    CALLBACK_NEEDS_WHITELIST = False

    def __init__(self, *args, **kwargs):
        super(CallbackModule, self).__init__(*args, **kwargs)
        self.task = None
        self.play = None
        self.task_serialized = False
        self.play_serialized = False

    def get_task_serialized(self):

        if not self.task_serialized:
            self.task_serialized = self.task.serialize()

        return self.task_serialized

    def get_play_serialized(self):

        if not self.play_serialized:
            self.play_serialized = self.play.serialize()

        return self.play_serialized

    def get_task_detail(self, detail_key):

        if not self.task:
            return None
        temp = self.get_task_serialized()
        for level in detail_key.split("."):
            temp = temp.get(level, {})

        return temp

    def get_task_name(self):

        name = self.get_task_detail("name")
        return name

    def get_recursive_role_detail(self, detail_key, role):

        if detail_key in role.get("_role_params", {}).keys():
            return role["_role_params"][detail_key]

        for r in role.get("_parents", []):
            key = self.get_recursive_role_detail(detail_key, r)
            if isinstance(key, int):
                return key

        return None


    def get_env_id(self):

        #pprint.pprint(self.task.serialize())
        #pprint.pprint(self.play.serialize())

        id = self.get_task_detail("role._role_params._env_id")

        if not isinstance(id, int):
            id = self.get_recursive_role_detail("_env_id", self.get_task_serialized().get("role", {}))

        if isinstance(id, int):
            return id
        else:
            return None


    def get_role_id(self):

        # pprint.pprint(self.task.serialize())
        # pprint.pprint(self.play.serialize())

        id = self.get_task_detail("role._role_params._role_id")

        if not isinstance(id, int):
            id = self.get_recursive_role_detail("_role_id", self.get_task_serialized().get("role", {}))
        if isinstance(id, int):
            return id
        else:
            return None

        # parents = self.get_task_detail("role._parents")
        # if  parents:
            # for p in parents:
                # if "freck_id" in p["_role_params"].keys():

                    # return p["_role_params"]["freck_id"]


    def print_output(self, category, result, item=None):

        # if self.task:
            # pprint.pprint(self.task.serialize())
        output = {}
        output["category"] = category
        if category == "play_start":
            roles = self.get_play_serialized().get("roles", {})
            env_id = None
            if roles and len(roles) >= 1:
                env_id = roles[0].get("_role_params", {}).get("_env_id", None)

            output["_env_id"] = env_id
            display.display(json.dumps(output, encoding='utf-8'))
            return

        temp = self.get_role_id()
        output["_role_id"] = temp
        temp = self.get_env_id()
        output["_env_id"] = temp

        temp = self.get_task_name()
        if isinstance(temp, string_types) and temp.startswith("dyn_role"):
            task_id, task_name = temp.split(" -- ")
            output["dyn_task"] = True
            output["_dyn_task_id"] = task_id
            output["name"] = task_name
        else:
            output["dyn_task"] = False
            output["_dyn_task_id"] = None
            output["name"] = temp

        if item:
            output["item"] = item

        action = self.get_task_detail("action")
        if not action:
            action = "n/a"
        output["action"] = action

        output["ignore_errors"] = self.get_task_detail("ignore_errors")

        # output["task"] = self.task.serialize()
        # output["play"] = self.play.serialize()
        if category == "play_start" or category == "task_start":
            output["result"] = {}
        else:
            # output["result"] = result._result
            msg = result._result.get("msg", None)
            if msg:
                output["msg"] = msg
            stderr = result._result.get("stderr", None)
            if stderr:
                output["stderr"] = stderr
                output["stderr_lines"] = result._result.get("stderr_lines")

            if result._result.get('changed', False):
                status = 'changed'
            else:
                status = 'ok'
            output["status"] = status

            skipped = result._result.get('skipped', False)
            output["skipped"] = skipped

        display.display(json.dumps(output, encoding='utf-8'))


    def v2_runner_on_ok(self, result, **kwargs):

        self.print_output("ok", result)

    def v2_runner_on_failed(self, result, **kwargs):

        self.print_output("failed", result)

    def v2_runner_on_unreachable(self, result, **kwargs):

        self.print_output("unreachable", result)

    def v2_runner_on_skipped(self, result, **kwargs):

        self.print_output("skipped", result)

    def v2_playbook_on_play_start(self, play):
        self.play = play
        self.play_serialized = False
        self.print_output("play_start", None)

    def v2_playbook_on_task_start(self, task, is_conditional):

        self.task = task
        self.task_serialized = False
        self.print_output("task_start", None)

    def v2_runner_item_on_ok(self, result):

        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if isinstance(result._task, TaskInclude):
            return
        elif result._result.get('changed', False):
            status = 'changed'
        else:
            status = 'ok'

        item = self._get_item(result._result)

        self.print_output("item_ok", result, item)

    def v2_runner_item_on_failed(self, result):
        item = self._get_item(result._result)
        self.print_output("item_failed", result, item)

    def v2_runner_item_on_skipped(self, result):
        item = self._get_item(result._result)
        self.print_output("item_skipped", result, item)

    def v2_on_any(self, *args, **kwargs):

        # pprint.pprint(args)
        pass
