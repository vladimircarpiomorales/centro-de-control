#!/bin/bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
cd ~/Music/ACE-Audio
source venv/bin/activate
python webui.py
