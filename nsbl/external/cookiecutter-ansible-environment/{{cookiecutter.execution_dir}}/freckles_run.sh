#!/usr/bin/env bash

if [ -e "$HOME/.nix-profile/etc/profile.d/nix.sh" ]; then source "$HOME/.nix-profile/etc/profile.d/nix.sh"; fi

cd {{cookiecutter.freckles_playbook_dir}}

export PATH="$HOME/.freckles/bin:../bin:$PATH:$HOME/.freckles/opt/conda/bin:$HOME/.freckles/opt/venv_freckles/freckles/bin"

mkdir -p ../logs

{{cookiecutter.freckles_extra_script_commands}}

ansible-playbook {{cookiecutter.freckles_ask_sudo}} {{cookiecutter.freckles_playbook}}
