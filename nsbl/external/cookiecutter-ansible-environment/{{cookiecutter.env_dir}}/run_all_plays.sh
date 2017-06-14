#!/usr/bin/env bash

if [ -e "$HOME/.nix-profile/etc/profile.d/nix.sh" ]; then source "$HOME/.nix-profile/etc/profile.d/nix.sh"; fi

cd {{cookiecutter.playbook_dir}}

{{cookiecutter.extra_script_commands}}


ansible-playbook {{cookiecutter.ansible_playbook_args}} {{cookiecutter.ask_sudo}} {{cookiecutter.playbook}}
