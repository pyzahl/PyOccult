"""sitesfile.py - read and write sites.py (the observing sites, in the data folder; private, not in git).

Used by the GUI's Site tab and by `pysyzygos setup --geoid`. Saving fills every site's `geoid_m` (geoid.fill_all):
the height of mean sea level above the WGS84 ellipsoid there, added to `ele` in pysyzygos_config.py. Comments in an
existing sites.py are not kept.
"""
from pysyzygos.version import __version__
import os, pprint, runpy, time

from pysyzygos.home import PKG


def load_sites(path="sites.py"):
    """(sites dict, default_site) from sites.py, else from the template sites_example.py."""
    if not os.path.isfile(path):
        path = os.path.join(PKG, "templates", "sites_example.py")
    g = runpy.run_path(path)
    return {k: dict(v) for k, v in g["sites"].items()}, g["default_site"]


def save_sites(sites, default_site, by="the PySyzygos GUI", path="sites.py"):
    """Write sites.py atomically, with each site's geoid height filled in (geoid.fill_all)."""
    from pysyzygos import geoid
    geoid.fill_all(sites)
    text = ("# Your observing sites (not in git). Layout and optional keys: see src/pysyzygos/templates/sites_example.py.\n"
            "# pysyzygos_config.py uses `default_site`, or the site named in the environment variable PYSYZYGOS_SITE.\n"
            "# ele: metres above mean sea level (ele_ref 'ellipsoid': above the WGS84 ellipsoid); geoid_m: the geoid's\n"
            "# height above the ellipsoid there (EGM96, filled in when saved).\n"
            f"# Written by {by} on {time.strftime('%Y-%m-%d %H:%M')}.\n\n"
            f"sites = {pprint.pformat(sites, sort_dicts=False, width=110)}\n\ndefault_site = {default_site!r}\n")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
