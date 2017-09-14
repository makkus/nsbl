# -*- coding: utf-8 -*-

import json
import logging

import click
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

        self.lookup_dict = lookup_dict
        self.display_sub_tasks = display_sub_tasks
        self.current_env_id = None
        self.current_role_id = None
        self.current_dyn_task_id = None
        self.current_task_is_dyn_role = False
        self.current_dyn_task = None
        self.current_task_name = None
        self.current_role = None

        self.new_line = False
        # self.task_has_items = False
        # self.task_has_nsbl_items = False
        self.current_ansible_task_name = None
        self.saved_item = None
        self.last_action = None
        self.msgs = []

    def add_log_message(self, line):

        details = json.loads(line)

        category = details["category"]

        role_changed = False
        task_changed = False

        env_id = details.get(ENV_ID_KEY, None)
        if category == "play_start":
            click.echo("Play start: {}".format(env_id))
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
            self.current_env_id = env_id
            self.current_role_id = role_id
            self.current_dyn_task_id = dyn_task_id

            self.current_role = self.lookup_dict[self.current_env_id][self.current_role_id]
            click.echo("new role: {}".format(self.current_role["name"]))

        if task_changed:
            self.current_task_name = task_name
            self.current_dyn_task_id = dyn_task_id
            if self.current_dyn_task_id != None:
                self.current_task = self.current_role[TASKS_KEY][self.current_dyn_task_id]
                self.current_task_is_dyn_role = True
            else:
                self.current_task_is_dyn_role = False
            click.echo("new task: {}".format(self.current_task_name))

        click.echo("\t{}".format(category))

        # print(details)
        # output = " * {}...".format(self.current_task[TASK_DESC_KEY])
        # output = " * {}...".format(self.lookup_dict[self.current_env_id][self.current_role_id])
        # output = " * {}".format(details["name"])
        # click.echo(output)
        self.new_line = True

        self.failed = False
        self.skipped = True
        self.changed = False

        # if not self.current_task:
        #     log.debug("No current task when processing: {}".format(line))
        #     return

        # task_desc = self.current_task[TASK_DESC_KEY]
        # task_name = self.current_task[TASK_NAME_KEY]

        # msg = details.get('msg', None)
        # stderr = details.get('stderr_lines', [])
        # item = details.get('item', None)
        # status = details.get('status', None)
        # skipped = details.get('skipped', None)
        # ignore_errors = details.get('ignore_errors', False)
        # action = details.get('action', self.last_action)
        # ansible_task_name = details.get('name', None)
        # event = {"category": category, "task_name": task_name, "task_desc": task_desc, "status": status, "item": item, "msg": msg, "skipped": skipped, "ignore_errors": ignore_errors, "ansible_task_name": ansible_task_name, "action": action}

        # if skipped != None and not skipped:
        #     self.skipped = False
        # if category == "failed" and not ignore_errors:
        #     self.failed = True

        # if msg:
        #     msg = msg.encode(sys.stdout.encoding, errors='replace').strip()
        # if msg:
        #     self.msgs.append(msg)

        # if stderr:
        #     for s in stderr:
        #         s = s.encode(sys.stdout.encoding, errors='replace').strip()
        #         self.stderrs.append(s)

        # if status and status == "changed":
        #     self.changed = True

        # sub_task_changed = self.current_ansible_task_name != ansible_task_name

        # if sub_task_changed and self.saved_item and not self.task_has_items and not self.task_has_nsbl_items:
        #     if not self.saved_item["action"] in NSBLIZED_TASKS:
        #         self.display_result(self.saved_item)
        #     elif self.saved_item["category"] == "skipped" and not self.new_line:
        #         self.display_result(self.saved_item)

        # if sub_task_changed:
        #     self.task_has_items = False
        #     self.saved_item = None
        #     self.task_has_nsbl_items = False
        #     self.last_action = None

        # current_task_is_nsblized = action in NSBLIZED_TASKS


        # if category.startswith("nsbl") and current_task_is_nsblized:
        #     self.saved_item = None
        #     if category == "nsbl_item_started":
        #         if not self.new_line:
        #             click.echo("")
        #         output = "       - {} => ".format(item)
        #         click.echo(output, nl=False)
        #         self.new_line = False
        #     else:
        #         self.display_nsbl_item(event)
        # elif category.startswith("item") and not current_task_is_nsblized:
        #     self.saved_item = None
        #     self.task_has_items = True
        #     self.display_item(event)
        # elif category == "task_start":
        #     if self.current_task_is_dyn_role:
        #         return
        #     elif ansible_task_name.startswith("nsbl_finished"):
        #         return

        #     if not self.new_line:
        #         click.echo("")
        #     if ansible_task_name.startswith("nsbl_started="):
        #         name = ansible_task_name[13:]
        #     else:
        #         name = ansible_task_name
        #     output = "    - {} => ".format(name)
        #     click.echo(output, nl=False)
        #     self.new_line = False
        # elif category in ["ok", "failed", "skipped"]:

        #     if not self.task_has_items and not self.task_has_nsbl_items and sub_task_changed and not current_task_is_nsblized:
        #         self.display_result(event)
        #     else:
        #         self.saved_item = event
        # else:
        #     pass
        #     # print("NO CATEGORY: {}".format(category))

        # self.current_ansible_task_name = ansible_task_name
        # self.last_action = action

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

    def display_nsbl_item(self, ev):

        item = self.pretty_print_item(ev["item"])
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
            self.new_line = True
            click.echo(output)
        elif ev["category"] == "nsbl_item_failed":
            msg = ev.get('msg', None)
            if not msg:
                if ev.get("ignore_errors", False):
                    msg = "(but errors ignored)"
                else:
                    msg = "(no error details)"
                    output = "failed: {}".format(msg)

            output = "failed: {}".format(msg)
            click.echo(output)
            self.new_line = True

    def display_item(self, ev):

        item = self.pretty_print_item(ev["item"])
        if not self.new_line:
            click.echo("")

        if ev["category"] == "item_ok":
            skipped = ev["skipped"]
            if skipped:
                msg = "skipped"
            else:
                if ev["status"] == "changed":
                    msg = "changed"
                else:
                    msg = "no change"
            output = "      - {} => ok ({})".format(item, msg)
            click.echo(output)
            self.new_line = True
        elif ev["category"] == "item_failed":
            msg = ev.get('msg', None)
            if not msg:
                if ev.get("ignore_errors", False):
                    msg = "(but errors ignored)"
                else:
                    msg = "(no error details)"
                    output = "failed: {}".format(msg)
            output = "      - {} => failed: {}".format(item, msg)
            click.echo(output)
            self.new_line = True
        elif ev["category"] == "item_skipped":
            output = "      - {} => skipped".format(item)
            click.echo(output)
            self.new_line = True

    def display_result(self, ev):

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
                output = "skipped"
                click.echo(output)
                self.new_line = True

    def process_task_changed(self):

        msg = ["n/a"]
        if not self.new_line:
            click.echo("")
        if self.failed:
            output = []
            if self.msgs:
                if len(self.msgs) < 2:
                    output.append("   => failed: {}".format("".join(self.msgs)))
                else:
                    output.append("   => failed:")
                    output.append("      messages in this task:")
                    for m in self.msgs:
                        output.append("        -> {}".format(m))
            else:
                output.append("   => failed")

            if self.stderrs:
                output.append("      stderr:")
                for e in self.stderrs:
                    output.append("        -> {}".format(e))

            output = "\n".join(output)

        elif self.changed:
            output = "   => ok (changed)"
        else:
            output = "   => ok (no change)"

        click.echo(output)
        click.echo("")
        self.new_line = True

    def finish_up(self):

        self.process_task_changed()
