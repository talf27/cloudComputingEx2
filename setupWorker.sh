#!/bin/bash

sudo apt update
sudo apt install python3-flask -y
nohup python3 worker.py