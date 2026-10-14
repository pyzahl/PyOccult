"""config.py - the run configuration, as attributes of this module (`from pysyzygos import config`; config.LAT, ...).

Your settings are in pysyzygos_config.py in the data folder (pysyzygos.home.HOME), next to sites.py. It is created from
templates/pysyzygos_config.py when missing. The template runs first, then your file, so a setting your (older) file
does not have yet keeps the template's default. Tools may override attributes for one run (pysyzygos/runner.py, GUI);
the file is not changed.
"""
import os, runpy, shutil, sys
from pysyzygos.home import HOME, PKG, legacy_files

TEMPLATE = os.path.join(PKG, "templates", "pysyzygos_config.py")
USER = os.path.join(HOME, "pysyzygos_config.py")

if HOME not in sys.path:
    sys.path.insert(0, HOME)                                      # sites.py, targets.py
if os.path.join(PKG, "templates") not in sys.path:
    sys.path.append(os.path.join(PKG, "templates"))               # sites_example (fallback of older config files)
for _m in legacy_files(HOME):                                      # files of a version before 1.0.0 (PyOccult)
    print(f"renamed {_m} (PyOccult is now PySyzygos)", file=sys.stderr)
if not os.path.isfile(USER):
    shutil.copyfile(TEMPLATE, USER)
    print(f"created {USER} from the template (your run settings; edit it as you like)", file=sys.stderr)

_ns = runpy.run_path(TEMPLATE)
_ns.update(runpy.run_path(USER))
globals().update({k: v for k, v in _ns.items() if not k.startswith("__")})
del _ns
