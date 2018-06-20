#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open("README.rst") as readme_file:
    readme = readme_file.read()

with open("HISTORY.rst") as history_file:
    history = history_file.read()

requirements = [
    "Click>=6.7",
    "click-log>=0.1.8",
    "click-completion==0.3.1",
    "cookiecutter==1.6.0",
    "ansible==2.5.5",
    "frkl>=0.4.0",
    "lupkg>=0.1.1",
    "cursor>=1.2.0",
    "six>=1.11.0",
    "pexpect==4.5.0",
]

test_requirements = ["pytest>=3.6.0"]

setup(
    name="nsbl",
    version="0.3.7",
    description="elastic ansible configuration",
    long_description=readme + "\n\n" + history,
    author="Markus Binsteiner",
    author_email="makkus@posteo.de",
    url="https://gitlab.com/frkl/nsbl",
    packages=["nsbl"],
    package_dir={"nsbl": "nsbl"},
    entry_points={
        "console_scripts": [
            "nsbl=nsbl.cli:cli",
            "nsbl-inventory=nsbl.inventory_cli:main",
            "nsbl-plbk=nsbl.playbook_cli:cli",
        ],
        "frkl.collector": [
            "inventory=nsbl:NsblInventory",
        ],
        "frkl.frklists": [
            "nsbl=nsbl:NsblTasklist"
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    license="GNU General Public License v3",
    zip_safe=False,
    keywords="nsbl",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
    ],
    test_suite="tests",
    tests_require=test_requirements,
)
