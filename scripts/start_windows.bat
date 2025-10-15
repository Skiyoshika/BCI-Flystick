@echo off
python -m venv .venv && call .venv\Scripts\activate
pip install -r python\requirements.txt
python python\bci_controller.py
