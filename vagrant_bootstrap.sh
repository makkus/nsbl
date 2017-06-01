#!/usr/bin/env bash

export DEBIAN_FRONTEND=noninteractive

set -x
set -e

#cp -r /vagrant/bootstrap/.pip /home/vagrant/.pip

# create freckles virtualenv
FRECKLES_DIR="$HOME/.freckles"
FRECKLES_VIRTUALENV="$FRECKLES_DIR/opt/venv_freckles"
export WORKON_HOME="$FRECKLES_VIRTUALENV"

sudo apt-get update
sudo apt-get install -y build-essential git python-dev python-virtualenv libssl-dev libffi-dev stow libsqlite3-dev

mkdir -p "$FRECKLES_DIR"
mkdir -p "$FRECKLES_DIR/data"
mkdir -p "$FRECKLES_VIRTUALENV"
cd "$FRECKLES_VIRTUALENV"
virtualenv freckles

# install freckles & requirements
source freckles/bin/activate
pip install --upgrade pip
pip install --upgrade setuptools wheel


echo 'source "$HOME/.freckles/opt/venv_freckles/freckles/bin/activate"' >> "$HOME/.bashrc"
#ln -s /vagrant/examples/example_only_zsh/dotfiles /home/vagrant/dotfiles

# install freckles
source "$HOME/.freckles/opt/venv_freckles/freckles/bin/activate"
cd /vagrant
pip install -r requirements_dev.txt
python setup.py develop
