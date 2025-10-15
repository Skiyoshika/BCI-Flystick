#!/usr/bin/env bash
set -e
python3 -m venv .venv && source .venv/bin/activate
pip install -r python/requirements.txt
python python/bci_controller.py
