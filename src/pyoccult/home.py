"""home.py - where PyOccult's code and your data live.

PKG: the package folder (code, templates, the logo, data/ne_110m_earth.json).
HOME: the data folder: sites.py, pyoccult_config.py, SPICE kernels, Gaia catalogs, picks/, favorites/, maps/,
hits_log.csv, ... Every tool runs with HOME as its working folder, so relative paths in the configuration (map_dir,
gaia_local_dir, picks_dir) are relative to it. HOME is, first match:
  1. "env":      the environment variable PYOCCULT_HOME (one run, tests, several setups side by side);
  2. "setting":  the folder saved in the settings file POINTER (`pyoccult setup --home <folder>`, or setup's question
                 on the first run of an installed copy):
                   Linux    ~/.config/pyoccult/home  (or $XDG_CONFIG_HOME/pyoccult/home)
                   macOS    ~/Library/Application Support/PyOccult/home
                   Windows  %APPDATA%\\PyOccult\\home
  3. "checkout": the project folder (the one with pyproject.toml) when PyOccult runs from a source checkout (git clone
                 + `pip install -e .`, `uv run`), so a clone keeps its data in its own folder;
  4. "default":  DEFAULT, ~/PyOccult (an installed copy without a setting yet).
SOURCE tells which one applied.
"""
import os, sys

PKG = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(os.path.expanduser("~"), "PyOccult")


def config_dir(platform=sys.platform, environ=os.environ):
    """The system's folder for PyOccult's own settings (only the data-folder setting lives there)."""
    if platform.startswith("win"):
        return os.path.join(environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming"), "PyOccult")
    if platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "PyOccult")
    return os.path.join(environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"), "pyoccult")


POINTER = os.path.join(config_dir(), "home")


def resolve(environ=os.environ, pointer=POINTER, pkg=PKG, default=DEFAULT):
    """(data folder, source) by the rules above."""
    env = environ.get("PYOCCULT_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env)), "env"
    try:
        with open(pointer, encoding="utf-8") as f:
            saved = f.read().strip()
        if saved:
            return os.path.abspath(os.path.expanduser(saved)), "setting"
    except OSError:
        pass
    checkout = os.path.dirname(os.path.dirname(pkg))                   # <project>/src/pyoccult -> <project>
    if os.path.isfile(os.path.join(checkout, "pyproject.toml")):
        return checkout, "checkout"
    return default, "default"


def save(folder, pointer=POINTER):
    """Remember folder as the data folder (writes the settings file, creates the folder). Returns its full path."""
    folder = os.path.abspath(os.path.expanduser(folder))
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.dirname(pointer), exist_ok=True)
    tmp = pointer + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(folder + "\n")
    os.replace(tmp, pointer)
    return folder


def describe(home=None, source=None):
    """'~/PyOccult (setting in ~/.config/pyoccult/home)': the data folder and why, for status lines."""
    home, source = (home, source) if home else (HOME, SOURCE)
    why = {"env": "environment variable PYOCCULT_HOME", "setting": f"setting in {POINTER}",
           "checkout": "project folder of this checkout", "default": "default for an installed copy"}[source]
    return f"{home} ({why})"


HOME, SOURCE = resolve()
