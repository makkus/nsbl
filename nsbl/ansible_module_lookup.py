#!/usr/bin/env python
# -*- coding: utf-8 -*-__

from ansible.utils import module_docs
from os import walk

path = "/home/markus/projects/other/ansible/lib/ansible/modules/cloud/amazon"
if path[-1] != '/':
    path = path + '/'

all_docs = []
errors = []
for (dirpath, dirnames, ansible_modules) in walk(path):
    if dirpath == path:
        for mod in ansible_modules:
            print(mod)
            try:
                try:
                    doc, plainexamples, returndocs = module_docs.get_docstring(path + mod)

                except ValueError:
                    print("XXX")
                    doc, plainexamples = module_docs.get_docstring(path + mod)
                    print("ZZZ")
                    print(plainexamples)
                except Exception as e:
                    print("YYY")
                    print(str(e))
                    # module.fail_json(msg='error', error=str(e))

                try:
                    examples_list = plainexamples.split('\n')
                    doc['examples'] = examples_list
                except:
                    errors.append(doc)
                    errors.append('error-examples')
                    continue

                all_docs.append(doc)
            except Exception as ee:
                print(ee)
                errors.append(mod)
                errors.append('unknown')
