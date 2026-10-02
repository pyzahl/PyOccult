#!.venv/bin/python3
"""pyoccult_setup.py - one-time setup of everything PyOccult needs locally. Safe to rerun: finished parts are skipped,
an interrupted Gaia build continues where it stopped.

    python pyoccult_setup.py              # kernels + local Gaia catalog + bright-star index
    python pyoccult_setup.py --no-gaia    # SPICE kernels only
    python pyoccult_setup.py --status     # show what is there
    python pyoccult_setup.py --no-geoip   # do not guess your site from your IP address
    python pyoccult_setup.py --gmax 16    # a catalog to G 16 instead (own folder gaia_dr3_g16, ~3 GB)
    python pyoccult_setup.py --gmax 17 --dir /data/gaia_g17

  0. Your observing site (sites.py, private): if missing, guessed from your IP address (ipinfo.io), or from a city or
     place name (Open-Meteo geocoding), or typed in; non-interactive runs copy sites_example.py.

  1. SPICE kernels (naif0012.tls, de440.bsp, pck00010.tpc, earth_latest_high_prec.bpc; ~120 MB) into this folder.
  2. Local Gaia DR3 catalog, G <= gaia_local_gmax, into gaia_local_dir (pyoccult_config.py). Streams ESA's bulk files:
     753 GB download, ~11 GB kept for G <= 18, about 1.5-2 h at 1.4 Gbit/s. Needed by pyoccult.py (corridor mode).
  3. Bright-star index (G <= 15, ~1.3 GB) next to the catalog, for pyoccult_pick.py. ~30 s.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))                 # kernels live next to the scripts

SITES_HINT = """   Edit sites.py and enter your observing site(s), then rerun or just start searching:
     - lat, lon: geodetic degrees, longitude east-positive (west is negative); ele: metres
     - optional view: min_alt, max_sun_alt, reach_km; equipment: aperture_cm, frames, mag_adjust, extinction
       (all keys are explained at the top of sites_example.py)
     - default_site names the site used; PYOCCULT_SITE=<name> picks another one for a single run
   sites.py stays private (it is in .gitignore)."""


APPROX = "APPROXIMATE"                       # marker in a generated sites.py: position not yet the exact one


def _get_json(url, timeout=10):
    import json, urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "PyOccult-setup"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _elevation(lat, lon):
    """Ground elevation (m) from Open-Meteo, or None."""
    try:
        return float(_get_json(f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}")["elevation"][0])
    except Exception:
        return None


def _ip_guess():
    """(lat, lon, ele, label) from the IP address (ipinfo.io; city level, 10-100 km, wrong behind a VPN), or None."""
    try:
        d = _get_json("https://ipinfo.io/json")
        lat, lon = (float(x) for x in d["loc"].split(","))
        return lat, lon, _elevation(lat, lon), ", ".join(x for x in (d.get("city"), d.get("region"), d.get("country")) if x)
    except Exception as ex:
        print(f"   IP lookup failed ({str(ex)[:80]})")
        return None


def _city(name):
    """Pick a place from Open-Meteo's geocoding: (lat, lon, ele, label) or None."""
    import urllib.parse
    try:
        res = _get_json("https://geocoding-api.open-meteo.com/v1/search?"
                        + urllib.parse.urlencode(dict(name=name, count=5))).get("results", [])
    except Exception as ex:
        print(f"   place lookup failed ({str(ex)[:80]})")
        return None
    if not res:
        print(f"   no place called {name!r} found")
        return None
    for i, r in enumerate(res, 1):
        print(f"   {i}. {r['name']}, {r.get('admin1', '')}, {r.get('country', '')}: "
              f"{r['latitude']:.4f}, {r['longitude']:.4f}, {r.get('elevation', 0):.0f} m")
    k = input(f"   which one [1-{len(res)}, Enter = 1]: ").strip() or "1"
    if not (k.isdigit() and 1 <= int(k) <= len(res)):
        return None
    r = res[int(k) - 1]
    return (r["latitude"], r["longitude"], r.get("elevation"),
            ", ".join(x for x in (r["name"], r.get("admin1"), r.get("country")) if x))


def _manual():
    """lat, lon, ele typed in (ele empty: looked up). (lat, lon, ele, label) or None."""
    try:
        lat = float(input("   latitude, deg (north positive): "))
        lon = float(input("   longitude, deg (east positive, west negative): "))
        e = input("   elevation, m (Enter: look it up): ").strip()
    except ValueError:
        print("   not a number")
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 360):
        print("   out of range")
        return None
    return lat, (lon + 180) % 360 - 180, float(e) if e else _elevation(lat, lon), "entered by hand"


def _write_sites(lat, lon, ele, label, approx):
    from datetime import date
    note = (f"  # {APPROX} ({label}): replace with your exact position" if approx else f"  # {label}")
    with open("sites.py", "w") as f:
        f.write(f"""# Your observing sites (not in git). Layout and optional keys: see sites_example.py.
# pyoccult_config.py uses `default_site`, or the site named in the environment variable PYOCCULT_SITE.
# Created by pyoccult_setup.py on {date.today()}.

sites = {{
    "home": dict(lat={lat:.5f}, lon={lon:.5f}, ele={ele or 0:.0f}, name="Home",{note}
                 aperture_cm=25, min_alt=10),
}}

default_site = "home"
""")


def ensure_sites(geoip=True):
    """Create sites.py if the user has none yet (never overwrites). Interactive: guess the site from the IP address,
    or ask for a place name or lat/lon/ele; otherwise copy sites_example.py. True if just created."""
    if os.path.isfile("sites.py"):
        return False
    if not os.path.isfile("sites_example.py"):
        sys.exit("sites.py and sites_example.py are both missing: restore sites_example.py from git")
    if sys.stdin.isatty():
        print("No sites.py yet: let us set up your observing site.")
        guess = None
        if geoip:
            print("   looking up your approximate location from your IP address (ipinfo.io) ...")
            guess = _ip_guess()
        while True:
            if guess:
                lat, lon, ele, label = guess
                print(f"   {label}: {lat:.4f}, {lon:.4f}, {ele or 0:.0f} m")
                k = input("   [Enter] use it, [c]ity or place name, [m]anual lat/lon/ele, [s]kip (example site): ")
            else:
                k = input("   [c]ity or place name, [m]anual lat/lon/ele, [s]kip (example site): ")
            k = k.strip().lower()
            if guess and k == "":
                _write_sites(*guess, approx=guess[3] != "entered by hand")
                break
            if k.startswith("c"):
                guess = _city(input("   city or place: ").strip()) or guess
            elif k.startswith("m"):
                guess = _manual() or guess
            elif k.startswith("s"):
                shutil.copyfile("sites_example.py", "sites.py")
                break
        print("   wrote sites.py")
        print(SITES_HINT)
        print()
        return True
    shutil.copyfile("sites_example.py", "sites.py")
    print("WARNING: no sites.py found: created it from sites_example.py (example site: New York City Hall).")
    print(SITES_HINT)
    print()
    return True


SITES_CREATED = ensure_sites(geoip="--no-geoip" not in sys.argv)   # before the config reads it
import pyoccult_config as config
import pyoccult_gaia_local as gaia
from pyoccult_kernels import KERNELS, download_kernels


def show_status(d=None):
    with open("sites.py") as f:
        example = f.read() == open("sites_example.py").read() if os.path.isfile("sites_example.py") else False
    print(f"  site {config.site_name!r:26s} {config.LAT:.4f} {config.LON:.4f}, {config.ELE:g} m, "
          f"{config.pick_aperture_cm:g} cm, stars G <= {config.MAG_MIN:g}" + ("   <- example site" if example else ""))
    if example:
        print("  WARNING: sites.py is still the example; enter your own site" + (" (see above)" if SITES_CREATED else ":"))
        if not SITES_CREATED:
            print(SITES_HINT)
    elif APPROX in open("sites.py").read():
        print("  WARNING: the site position in sites.py is approximate (from your IP address or a place name);"
              " replace it with your exact position (GPS, map) before observing.")
    for k in KERNELS:
        print(f"  {k:28s} {'ok' if os.path.isfile(k) else 'missing'}")
    d = d or getattr(config, "gaia_local_dir", None)
    if not d:
        print("  local Gaia catalog            gaia_local_dir not set in pyoccult_config.py")
        return
    st = gaia.status(d)
    print(f"  local Gaia catalog {d:12s}  {st['done']}/{st['total'] or '?'} files, {st['gb']:.1f} GB"
          + (" (complete)" if st["complete"] else ""))
    gmax = index_limit(d)
    have = os.path.isfile(os.path.join(d, f"bright_G{gmax:.1f}.v2.npy"))
    print(f"  bright-star index G <= {gmax:<5g}  {'ok' if have else 'missing'}")


def index_limit(d):
    """Bright-star index limit for the pick tool: whole magnitudes >= 15, but never past the catalog's own limit."""
    lim = gaia.index_gmax(getattr(config, "pick_cam_limit", 15.0))
    try:
        import json
        lim = min(lim, json.load(open(os.path.join(d, "catalog.json")))["gmax"])
    except (OSError, ValueError, KeyError):
        pass
    return float(lim)


def catalog_target(gmax_arg, dir_arg):
    """(folder, gmax) for the Gaia build: --gmax / --dir, else the config. A limit other than the config's goes to its
    own folder (gaia_dr3_g<gmax>) unless --dir is given: one folder holds one limit."""
    cfg_dir = getattr(config, "gaia_local_dir", None) or "gaia_dr3_g18"
    cfg_gmax = float(getattr(config, "gaia_local_gmax", 18.0))
    gmax = cfg_gmax if gmax_arg is None else float(gmax_arg)
    d = dir_arg or (cfg_dir if gmax == cfg_gmax else f"gaia_dr3_g{gmax:g}")
    return d, gmax


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-gaia", action="store_true", help="kernels only")
    ap.add_argument("--status", action="store_true", help="only show what is installed")
    ap.add_argument("--no-geoip", action="store_true", help="do not guess the site from the IP address")
    ap.add_argument("--workers", type=int, default=6, help="parallel Gaia downloads")
    ap.add_argument("--gmax", type=float, help="faintest Gaia G kept in the local catalog (default: config "
                                               "gaia_local_gmax, 18); a new limit needs its own folder")
    ap.add_argument("--dir", help="catalog folder (default: config gaia_local_dir, or gaia_dr3_g<gmax> for another --gmax)")
    a = ap.parse_args()
    if a.status:
        show_status(catalog_target(a.gmax, a.dir)[0] if (a.gmax is not None or a.dir) else None)
        sys.exit(0)
    print("1. SPICE kernels")
    if not download_kernels(config.earth_pck_max_age):
        sys.exit("kernel download failed")
    d = None
    if not a.no_gaia:
        d, gmax = catalog_target(a.gmax, a.dir)
        print(f"2. local Gaia catalog G <= {gmax:g} in {d}")
        st = gaia.status(d)
        if st["total"] and abs(st.get("gmax", gmax) - gmax) > 1e-9:
            sys.exit(f"   {d} already holds a catalog with G <= {st['gmax']:g}; use another --dir for G <= {gmax:g}")
        if st["complete"]:
            print("   complete")
        else:
            gaia.build(d, gmax, a.workers)
        print("3. bright-star index")
        gaia.BrightIndex(d, index_limit(d))
        print("   ok")
        if d != getattr(config, "gaia_local_dir", None) or gmax != float(getattr(config, "gaia_local_gmax", 18.0)):
            print(f"\n   To search with this catalog, set in pyoccult_config.py:\n"
                  f"       gaia_local_dir = \"{d}\"\n       gaia_local_gmax = {gmax:g}")
    print()
    show_status(d)
