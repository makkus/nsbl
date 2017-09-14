import yaml
from ansible.plugins.filter.core import FilterModule
from jinja2.ext import Extension


def to_yaml(var):
    return yaml.safe_dump(var, default_flow_style=False)


class AnsibleFilterExtension(Extension):
    def __init__(self, environment):
        super(Extension, self).__init__()
        fm = FilterModule()
        filters = fm.filters()
        environment.filters.update(filters)


utils = AnsibleFilterExtension
