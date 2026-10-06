"""home.py - where PyOccult's code and your data live.

PKG: the package folder (code, templates, the logo, data/ne_110m_earth.json).
HOME: the data folder: sites.py, pyoccult_config.py, SPICE kernels, Gaia catalogs, picks/, favorites/, maps/,
hits_log.csv, ... Every tool runs with HOME as its working folder, so relative paths in the configuration (map_dir,
gaia_local_dir, picks_dir) are relative to it. HOME is
  1. the environment variable PYOCCULT_HOME, if set;
  2. the project folder (the one with pyproject.toml) when PyOccult runs from a source checkout (git clone,
     `pip install -e .`, `uv run`), so an existing install keeps its data where it is;
  3. else the current folder.
"""
import os

PKG = os.path.dirname(os.path.abspath(__file__))


def _find_home():
    env = os.environ.get("PYOCCULT_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    checkout = os.path.dirname(os.path.dirname(PKG))                   # <project>/src/pyoccult -> <project>
    if os.path.isfile(os.path.join(checkout, "pyproject.toml")):
        return checkout
    return os.getcwd()


HOME = _find_home()
