#!/bin/bash

# Python 3.12 Repo
sudo add-apt-repository ppa:deadsnakes/ppa -y

# Make sure we're up-to-date
sudo apt update && sudo apt upgrade -y

# Install packages (registry checks use HTTP APIs; only ripgrep is needed
# outside Python itself)
sudo apt install ripgrep \
                python3-dev \
                python3.12-dev \
                -y

# Install pip3.12
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

# Setup Python3.12
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    sudo update-alternatives --config python

# Install requirements
pip3.12 install -r requirements.txt
