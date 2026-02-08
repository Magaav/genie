#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/env.sh"
# Check required packages
require "nano"

set_docker(){
  # Install docker
  curl -fsSL https://get.docker.com | sh
  # Start Docker Daemon
  sudo systemctl start docker
  # Enable Docker to start on boot
  sudo systemctl enable docker
  # Add current user to the docker group to run docker without sudo
  sudo usermod -aG docker $USER
}





sudo reboot