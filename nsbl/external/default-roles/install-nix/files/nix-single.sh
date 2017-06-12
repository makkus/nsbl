#! /usr/bin/env bash

TEMP_DIR=/tmp/freckles_install

function command_exists {
    type "$1" > /dev/null 2>&1 ;
}

function download {
    if command_exists wget; then
        wget -O $2 $1
    elif command_exists curl; then
        curl -o $2 $1
    else
        echo "Could not find 'wget' nor 'curl' to download files. Exiting..."
        exit 1
    fi
}

mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"
download https://nixos.org/nix/install "$TEMP_DIR/install_nix"
sh install_nix
