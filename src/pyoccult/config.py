"""config.py - the run configuration, as attributes of this module (`from pyoccult import config`; config.LAT, ...).

Your settings are in pyoccult_config.py in the data folder (pyoccult.home.HOME), next to sites.py. It is created from
templates/pyoccult_config.py when missing. The template runs first, then your file, so a setting your (older) file
does not have yet keeps the template's default. Tools may override attributes for one run (pyoccult/runner.py, GUI);
the file is not changed.
"""
import os, runpy, shutil, sys
from pyoccult.home import HOME, PKG

TEMPLATE = os.path.join(PKG, "templates", "pyoccult_config.py")
USER = os.path.join(HOME, "pyoccult_config.py")

if HOME not in sys.path:
    sys.path.insert(0, HOME)                                      # sites.py, targets.py
if os.path.join(PKG, "templates") not in sys.path:
    sys.path.append(os.path.join(PKG, "templates"))               # sites_example (fallback of older config files)
if not os.path.isfile(USER):
    shutil.copyfile(TEMPLATE, USER)
    print(f"created {USER} from the template (your run settings; edit it as you like)", file=sys.stderr)

_ns = runpy.run_path(TEMPLATE)
_ns.update(runpy.run_path(USER))
globals().update({k: v for k, v in _ns.items() if not k.startswith("__")})
del _ns
