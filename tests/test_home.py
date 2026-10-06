"""The data folder (pyoccult.home): order of the rules, the system settings folder, the saved setting."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pyoccult import home as H

tmp = tempfile.mkdtemp()
pointer = os.path.join(tmp, "cfg", "pyoccult", "home")
checkout = os.path.join(tmp, "proj")
pkg = os.path.join(checkout, "src", "pyoccult")
os.makedirs(pkg)
installed = os.path.join(tmp, "site-packages", "pyoccult")
os.makedirs(installed)
default = os.path.join(tmp, "PyOccult")

# installed copy, nothing set: the default
assert H.resolve({}, pointer, installed, default) == (default, "default")
# a checkout (pyproject.toml two levels up): its project folder
open(os.path.join(checkout, "pyproject.toml"), "w").close()
assert H.resolve({}, pointer, pkg, default) == (checkout, "checkout")
# a saved setting wins over the checkout; save() creates the folder and the settings file
chosen = H.save(os.path.join(tmp, "data"), pointer)
assert os.path.isdir(chosen) and open(pointer).read().strip() == chosen
assert H.resolve({}, pointer, pkg, default) == (chosen, "setting")
assert H.resolve({}, pointer, installed, default) == (chosen, "setting")
# the environment variable wins over everything (one run)
assert H.resolve({"PYOCCULT_HOME": os.path.join(tmp, "x")}, pointer, pkg, default) == (os.path.join(tmp, "x"), "env")
# an empty settings file counts as no setting
open(pointer, "w").close()
assert H.resolve({}, pointer, installed, default) == (default, "default")

# the system's settings folder
assert H.config_dir("linux", {}).endswith(os.path.join(".config", "pyoccult"))
assert H.config_dir("linux", {"XDG_CONFIG_HOME": "/xdg"}) == os.path.join("/xdg", "pyoccult")
assert H.config_dir("darwin", {}).endswith(os.path.join("Library", "Application Support", "PyOccult"))
assert H.config_dir("win32", {"APPDATA": "C:\\Users\\u\\AppData\\Roaming"}).endswith("PyOccult")
assert "setting in" in H.describe(chosen, "setting") and "checkout" in H.describe(checkout, "checkout")
print("HOME TESTS PASSED")
