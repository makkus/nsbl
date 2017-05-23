#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'Click>=6.0',
    'cookiecutter>=1.5.1',
]

test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='nsbl',
    version='0.1.0',
    description="elastic ansible configuration",
    long_description=readme + '\n\n' + history,
    author="Markus Binsteiner",
    author_email='makkus@posteo.de',
    url='https://github.com/makkus/nsbl',
    packages=[
        'nsbl',
    ],
    package_dir={'nsbl':
                 'nsbl'},
    entry_points={
        'console_scripts': [
            'nsbl=nsbl.cli:main',
            'nsbl_inv=nsbl.inventory_cli:main'
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    license="GNU General Public License v3",
    zip_safe=False,
    keywords='nsbl',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements
)
