#!/usr/bin/env bash

export DEBIAN_FRONTEND=noninteractive

set -x
set -e

# if [ -d "/pip" ]; then
#    rm -f .pip
#    ln -s /pip "$HOME/.pip"
# fi

# create freckles virtualenv
BASE_DIR="$HOME/.local/opt"
NSBL_DIR="$BASE_DIR/nsbl"
NSBL_VIRTUALENV_BASE="$NSBL_DIR/venv/"
NSBL_VIRTUALENV="$NSBL_VIRTUALENV_BASE/nsbl"
NSBL_VIRTUALENV_ACTIVATE="$NSBL_VIRTUALENV/bin/activate"
export WORKON_HOME="$NSBL_VIRTUALENV"

sudo apt-get update
sudo apt-get install -y build-essential git python-dev python-virtualenv libssl-dev libffi-dev stow libsqlite3-dev

mkdir -p "$NSBL_VIRTUALENV"
cd "$NSBL_VIRTUALENV_BASE"
virtualenv nsbl

# install freckles & requirements
source nsbl/bin/activate
pip install --upgrade pip
pip install --upgrade setuptools wheel


echo source "$NSBL_VIRTUALENV_ACTIVATE" >> "$HOME/.bashrc"

# install nsbl
source "$NSBL_VIRTUALENV_ACTIVATE"
cd /nsbl
pip install -r requirements_dev.txt
if [ -d "/frkl" ]; then
    pip install -e "/frkl"
fi
python setup.py develop
