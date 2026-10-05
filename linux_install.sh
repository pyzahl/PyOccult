#!/bin/sh
# PyOccult quick install for Linux (also works on macOS): virtual environment, Python packages, one-time data setup
# (asks for your site and the catalog), then the web interface. Run from the PyOccult folder:  sh linux_install.sh
# Safe to rerun: an existing .venv is reused, setup resumes and skips what is already there.
set -e
cd "$(dirname "$0")"

PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
    echo "Python 3 not found. Install it first (Debian/Ubuntu: sudo apt install python3 python3-venv)."
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "== creating the virtual environment .venv"
    "$PY" -m venv .venv || {
        echo "Could not create .venv. On Debian/Ubuntu install the venv module: sudo apt install python3-venv"
        rm -rf .venv
        exit 1
    }
fi

# use the venv's own python and pip directly: no 'activate' needed (it only works with 'source' in the same shell)
echo "== installing the Python packages into .venv"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "== one-time setup: your site, SPICE kernels, local Gaia catalog (answer the questions)"
.venv/bin/python pyoccult_setup.py

echo "== starting the web interface (stop with Ctrl-C; later just run: .venv/bin/python pyoccult_gui.py)"
exec .venv/bin/python pyoccult_gui.py
