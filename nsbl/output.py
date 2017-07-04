# -*- coding: utf-8 -*-

import json
import logging
import pprint
import sys

import click
from six import string_types

import cursor

from .defaults import *

log = logging.getLogger("nsbl")

class CursorOff(object):
    def __enter__(self):
        cursor.hide()

    def __exit__(self, *args):
        cursor.show()


class NsblPrintCallbackAdapter(object):

    def add_log_message(self, line):

        click.echo(line, nl=False)

    def finish_up(self):

        pass

class NsblLogCallbackAdapter(object):

    def __init__(self, lookup_dict, display_sub_tasks=True):

        self.display_utility_tasks = False
        self.display_sub_tasks = display_sub_tasks
        self.display_skipped_tasks = False

        self.lookup_dict = lookup_dict
        self.new_line = True

        self.current_env_id = None
        self.current_role_id = None
        self.current_dyn_task_id = None
        self.current_task_is_dyn_role = False
        self.current_dyn_task = None
        self.current_task_name = None
        self.current_role = None

        self.task_has_items = False
        self.task_has_nsbl_items = False
        self.current_ansible_task_name = None
        self.saved_item = None
        self.last_action = None
        self.msgs = []
        self.stderrs = []

        self.failed = False
        self.skipped = True
        self.changed = False

        self.output = ClickStdOutput()


    def add_log_message(self, line):

        details = json.loads(line)

        category = details["category"]
        # print("")
        # print(category)
        # print("")
        role_changed = False
        task_changed = False

        env_id = details.get(ENV_ID_KEY, None)
        if category == "play_start":
            name = self.lookup_dict[0][ENV_NAME_KEY]
            self.output.start_env(name)
            # click.echo("")
            return

        role_id = details.get(ROLE_ID_KEY, None)

        if category.startswith("nsbl") and env_id == None or role_id == None:
            env_id = self.current_env_id
            role_id = self.current_role_id

        if (env_id == None or role_id == None) and not self.display_utility_tasks:
            return

        if env_id != self.current_env_id:
            role_changed = True

        if role_id != self.current_role_id:
            role_changed = True

        category = details["category"]
        task_name = details.get(TASK_META_NAME_KEY, None)
        if not task_name and category.startswith("nsbl"):
            task_name = self.current_task_name

        dyn_task_id = details.get(DYN_TASK_ID_KEY, None)
        if not dyn_task_id and category.startswith("nsbl"):
            dyn_task_id = self.current_dyn_task_id

        # print("role: {}, dyn_id: {} - {}, task_name: {} - {}".format(role_changed, self.current_dyn_task_id, dyn_task_id, self.current_task_name, task_name))
        if role_changed or self.current_dyn_task_id != dyn_task_id or task_name != self.current_task_name:
            task_changed = True

        if role_changed:
            if self.current_role_id != None:
                self.output.process_task_changed(self.task_has_items, self.task_has_nsbl_items, self.saved_item, self.current_task_is_dyn_role)
                self.output.process_role_changed(self.failed, self.skipped, self.changed, self.msgs, self.stderrs)
            self.current_env_id = env_id
            self.current_role_id = role_id
            self.current_dyn_task_id = dyn_task_id

            self.current_role = self.lookup_dict[self.current_env_id][TASKS_KEY][self.current_role_id]
            self.output.start_role(self.current_role)

            self.saved_item = None
            self.failed = False
            self.skipped = True
            self.changed = False

            self.task_has_items = False
            self.task_has_nsbl_items = False

        if task_changed:
            if self.current_task_name != None and not role_changed:
                self.output.process_task_changed(self.task_has_items, self.task_has_nsbl_items, self.saved_item, self.current_task_is_dyn_role)

            self.current_task_name = task_name
            self.current_dyn_task_id = dyn_task_id
            if self.current_dyn_task_id != None:
                self.current_task = self.current_role[TASKS_KEY][self.current_dyn_task_id]
                self.current_task_is_dyn_role = True
            else:
                self.current_task_is_dyn_role = False

            self.output.start_task(self.current_task_name, self.current_role, self.current_task_is_dyn_role)

            self.saved_item = None

            self.task_has_items = False
            self.task_has_nsbl_items = False

        # task_desc = self.current_task[TASK_DESC_KEY]
        # task_name = self.current_task[TASK_NAME_KEY]
        task_desc = details.get('name', None)

        msg = details.get('msg', None)
        stderr = details.get('stderr_lines', [])
        item = details.get('item', None)
        status = details.get('status', None)
        skipped = details.get('skipped', None)
        ignore_errors = details.get('ignore_errors', False)
        action = details.get('action', self.last_action)
        ansible_task_name = details.get('name', None)

        if msg:
            msg = msg.encode(sys.stdout.encoding, errors='replace').strip()
        if msg:
            self.msgs.append(msg)

        if stderr:
            for s in stderr:
                s = s.encode(sys.stdout.encoding, errors='replace').strip()
                self.stderrs.append(s)

        event = {"category": category, "task_name": task_name, "task_desc": task_desc, "status": status, "item": item, "msg": msg, "skipped": skipped, "ignore_errors": ignore_errors, "ansible_task_name": ansible_task_name, "action": action, "stderr": stderr}

        if status and status == "changed":
            self.changed = True

        if skipped != None and not skipped:
            self.skipped = False
        if category == "failed" and not ignore_errors:
            self.failed = True

        if category in ["ok", "failed", "skipped"] and not self.task_has_items and not self.task_has_nsbl_items:
            self.saved_item = event
            return
        elif category.startswith("nsbl"):
            self.task_has_nsbl_items = True
            self.saved_item = None
            self.output.display_nsbl_item(event, self.current_task_is_dyn_role)
        elif category in ["item_ok", "item_failed"] and not self.task_has_nsbl_items:
            self.saved_item = None
            self.task_has_items = True
            self.output.display_item(event, self.current_task_is_dyn_role)


    def finish_up(self):

        self.output.process_task_changed(self.task_has_items, self.task_has_nsbl_items, self.saved_item, self.current_task_is_dyn_role)
        self.output.process_role_changed(self.failed, self.skipped, self.changed, self.msgs, self.stderrs)


class ClickStdOutput(object):

    def __init__(self):

        self.new_line = True
        self.display_sub_tasks = False

    def start_new_line(self):

        click.echo("")
        self.new_line = True

    def start_env(self, env_name):

        click.echo("* starting tasks for environment '{}'...".format(env_name))

    def start_role(self, current_role):

        if current_role["role_type"] == DYN_ROLE_TYPE:
            click.echo(" * starting custom tasks:")
        else:
            click.echo(" * applying role '{}'...".format(current_role["name"]), nl=False)
            self.new_line = False

    def start_task(self, task_name, current_role, current_is_dyn_role):
        if current_is_dyn_role:
            if not self.new_line:
                click.echo("")
            click.echo("     * {}... ".format(task_name), nl=False)
            self.new_line = False
        else:
            if self.display_sub_tasks:
                if not self.new_line:
                    click.echo("")
                click.echo("   - {} => ".format(task_name), nl=False)
                self.new_line = False


    def pretty_print_item(self, item):

        if isinstance(item, string_types):
            try:
                item = json.loads(item)
            except Exception as e:
                return item

        if isinstance(item, dict):
            if item.get("name", None):
                return item["name"]
            elif item.get("repo", None):
                return item["repo"]
            elif item.get("vars", {}).get("name", None):
                return item["vars"]["name"]
            elif item.get("vars", {}).get("repo", None):
                return item["vars"]["name"]

        return item

    def display_nsbl_item(self, ev, current_is_dyn_role):

        if not self.display_sub_tasks and not current_is_dyn_role:
            return

        item = self.pretty_print_item(ev["item"])
        if ev["category"] == "nsbl_item_started":
            if not self.new_line:
                click.echo("")

            output = "       - {} => ".format(item)
            click.echo(output, nl=False)
            self.new_line = False
            return

        if ev["category"] == "nsbl_item_ok":
            skipped = ev["skipped"]
            if skipped:
                msg = "skipped"
            else:
                if ev["status"] == "changed":
                    msg = "changed"
                else:
                    msg = "no change"
            output = "ok ({})".format(msg)
            click.echo(output)
        elif ev["category"] == "nsbl_item_failed":
            msg = ev.get('msg', None)
            if not msg:
                if ev.get("ignore_errors", False):
                    msg = "errors ignored"
                else:
                    msg = "no error details"

            output = "failed: {}".format(msg)
            click.echo(output)

        self.new_line = True

    def display_item(self, ev, current_is_dyn_role):

        if not self.display_sub_tasks and not current_is_dyn_role:
            return

        item = self.pretty_print_item(ev["item"])
        if not self.new_line:
            click.echo("")

        if ev["category"] == "item_ok":
            skipped = ev["skipped"]
            if skipped:
                msg = "item skipped"
            else:
                if ev["status"] == "changed":
                    msg = "changed"
                else:
                    msg = "no change"
            output = "       - {} => ok ({})".format(item, msg)
            click.echo(output)
        elif ev["category"] == "item_failed":
            msg = ev.get('msg', None)
            if not msg:
                if ev.get("ignore_errors", False):
                    msg = "errors ignored"
                else:
                    msg = "no error details"
            output = "       - {} => failed: {}".format(item, msg)
            click.echo(output)
        elif ev["category"] == "item_skipped":
            output = "       - {} => skipped".format(item)
            click.echo(output)

        self.new_line = True

    def display_result(self, ev, current_is_dyn_role):

        if not self.display_sub_tasks and not current_is_dyn_role:
            return

        if ev["ansible_task_name"].startswith("nsbl_started="):
            return
        if ev["ansible_task_name"].startswith("nsbl_finished="):
            output = "no task information available"
            click.echo(output)
            self.new_line = True
        else:
            if ev["category"] == "ok":
                skipped = ev["skipped"]
                if skipped:
                    msg = "skipped"
                else:
                    if ev["status"] == "changed":
                        msg = "changed"
                    else:
                        msg = "no change"
                output = "ok ({})".format(msg)
                click.echo(output)
                self.new_line = True
            elif ev["category"] == "failed":
                if ev["msg"]:
                    output = "failed: {}".format(ev["msg"])
                else:
                    if ev.get("ignore_errors", False):
                        msg = "(but errors ignored)"
                    else:
                        msg = "(no error details)"
                    output = "failed: {}".format(msg)
                click.echo(output)
                self.new_line = True
            elif ev["category"] == "skipped":
                if not self.display_skipped_tasks:
                    click.echo(u"\u001b[2K\r", nl=False)
                    self.new_line = True
                    return
                output = "skipped"
                click.echo(output)
                self.new_line = True

    def process_role_changed(self, failed, skipped, changed, msgs, stderrs):

        if not self.new_line:
            click.echo("\b\b\b  => ", nl=False)
        else:
            click.echo("   => ", nl=False)

        if failed:

            msg = ["n/a"]

            click.echo("")
            output = []
            if msgs:
                if len(msgs) < 2:
                    output.append("failed: {}".format("".join(msgs)))
                else:
                    output.append("failed:")
                    output.append("      messages in this task:")
                    for m in msgs:
                        output.append("        -> {}".format(m))
            else:
                output.append("failed")

            if stderrs:
                output.append("      stderr:")
                for e in stderrs:
                    output.append("        -> {}".format(e))

            output = "\n".join(output)
            click.echo(output)
            click.echo("")

        elif skipped:

            output = "skipped"
            click.echo(output)

        elif self.changed:
            output = "ok (changed)"
            click.echo(output)
        else:
            output = "ok (no change)"
            click.echo(output)

        # click.echo("")

    def process_task_changed(self, task_has_items, task_has_nsbl_items, saved_item, current_is_dyn_role):

        if task_has_items or task_has_nsbl_items:
            return

        elif saved_item:
            self.display_result(saved_item, current_is_dyn_role)
