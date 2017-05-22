# -*- coding: utf-8 -*-

import pprint
import json
import copy

from frkl import Frkl
from frkl import CHILD_MARKER_NAME, DEFAULT_LEAF_NAME, DEFAULT_LEAFKEY_NAME, KEY_MOVE_MAP_NAME, UrlAbbrevProcessor, EnsureUrlProcessor, EnsurePythonObjectProcessor, FrklProcessor

ENVS_KEY = "envs"
ENV_META_KEY = "meta"
ENV_NAME_KEY = "name"
ENV_TYPE_KEY = "type"
ENV_HOSTS_KEY = "hosts"
ENV_GROUPS_KEY = "groups"
VARS_KEY = "vars"


NSBL_BOOTSTRAP_FORMAT = {
    CHILD_MARKER_NAME: ENVS_KEY,
    DEFAULT_LEAF_NAME: ENV_META_KEY,
    DEFAULT_LEAFKEY_NAME: ENV_NAME_KEY,
    KEY_MOVE_MAP_NAME: VARS_KEY
}
NSBL_BOOTSTRAP_CHAIN = [
    UrlAbbrevProcessor(), EnsureUrlProcessor(), EnsurePythonObjectProcessor(), FrklProcessor(NSBL_BOOTSTRAP_FORMAT)
]

class NsblException(Exception):

    def __init__(self, message):

        super(NsblException, self).__init__(message)

ENV_TYPE_HOST = 'host'
ENV_TYPE_GROUP = 'group'
DEFAULT_ENV_TYPE = ENV_TYPE_GROUP

class Nsbl(object):

    def __init__(self, configs, default_env_type=DEFAULT_ENV_TYPE):

        self.frkl_obj = Frkl(configs, NSBL_BOOTSTRAP_CHAIN)
        self.config = self.frkl_obj.process()
        self.default_env_type = default_env_type
        self.groups = {}
        self.hosts = {}

        self.assemble_groups()

    def add_group(self, group_name, group_vars):

        if group_name in self.groups.keys():
            raise NsblException("Group '{}' defined twice".format(group_name))

        self.groups[group_name] = {}
        self.groups[group_name]["vars"] = group_vars
        self.groups[group_name]["hosts"] = []
        self.groups[group_name]["children"] = []

    def add_host(self, host_name, host_vars):

        if host_name in self.hosts.keys():
            raise NsblException("Host '{}' defined twice".format(host_name))

        self.hosts[host_name] = host_vars

    def add_group_to_group(self, child, group):

        if group not in self.groups[group]["children"]:
            self.groups[group]["children"].append(child)

    def add_host_to_group(self, host, group):

        if host not in self.groups[group]["hosts"]:
            self.groups[group]["hosts"].append(host)

    def assemble_groups(self):

        for env in self.config:
            if ENV_META_KEY not in env.keys():
                raise NsblException("Environment does not have metadata (missing '{}') key: {})".format(ENV_META_KEY, env))
            env_type = env[ENV_META_KEY].get(ENV_TYPE_KEY, False)
            if not env_type:
                if ENV_HOSTS_KEY in env[ENV_META_KEY].keys():
                    env_type = ENV_TYPE_GROUP
                elif ENV_GROUPS_KEY in env[ENV_META_KEY].keys():
                    env_type = ENV_TYPE_HOST
                else:
                    env_type = self.default_env_type

            env_name = env[ENV_META_KEY].get(ENV_NAME_KEY, False)
            if not env_name:
                raise NsblException("Environment metadata needs to contain a name (either host- or group-name): {}".format(env[ENV_META_KEY]))

            if env_type == ENV_TYPE_HOST:
                self.add_host(env_name, env[VARS_KEY])

                if ENV_HOSTS_KEY in env[ENV_META_KEY].keys():
                    raise NsblException("An environment of type {} can't contain the {} key".format(ENV_TYPE_HOST, ENV_HOSTS_KEY))

                for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
                    self.add_host_to_group(env_name, group)

            elif env_type == ENV_TYPE_GROUP:
                self.add_group(env_name, env[VARS_KEY])

                for host in env[ENV_META_KEY].get(ENV_HOSTS_KEY, []):
                    self.add_host_to_group(host, env_name)

                for group in env[ENV_META_KEY].get(ENV_GROUPS_KEY, []):
                    self.add_group_to_group(group, env_name)

            else:
                raise NsblException("Environment type needs to be either 'host' or 'group': {}".format(env_type))


    def list(self):

        result = copy.copy(self.groups)
        result["_meta"] = {"hostvars": self.hosts}

        return json.dumps(result, sort_keys=4, indent=4)

    def host(self, host):

        host_vars = self.hosts.get(host, {})
        return json.dumps(host_vars, sort_keys=4, indent=4)
