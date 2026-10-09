#!/bin/sh
# Linux launcher; use the project's environment without activating it.
cd "$(dirname "$0")" || exit 1
if [ ! -x "venv/bin/python" ]; then
    printf '%s\n' 'Python environment missing. Follow the one-time setup in readme.md.'
    exit 1
fi
nohup "./venv/bin/python" "./gui.py" > .streamline.log 2>&1 < /dev/null &
