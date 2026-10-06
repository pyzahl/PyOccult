"""setup.py - one-time setup of everything PyOccult needs locally. Safe to rerun: finished parts are skipped,
an interrupted Gaia build continues where it stopped.

    pyoccult setup              # kernels + local Gaia catalog + bright-star index
    pyoccult setup --source zenodo   # catalog: ready-made copy from Zenodo (G <= 16 or 18), no question
    pyoccult setup --source esa      # catalog: build it from ESA's Gaia files instead
    pyoccult setup --no-gaia    # SPICE kernels only
    pyoccult setup --status     # show what is there
    pyoccult setup --no-geoip   # do not guess your site from your IP address
    pyoccult setup --gmax 16    # a catalog to G 16 instead (own folder gaia_dr3_g16, ~3 GB)
    pyoccult setup --gmax 17 --dir /data/gaia_g17
    pyoccult setup --home ~/PyOccult      # keep all data in this folder from now on (default for installed copies)

  0. Your observing site (sites.py, private): if missing, guessed from your IP address (ipinfo.io), or from a city or
     place name (Open-Meteo geocoding), or typed in; non-interactive runs copy sites_example.py.

  1. SPICE kernels (naif0012.tls, de440.bsp, pck00010.tpc, earth_latest_high_prec.bpc; ~120 MB) into this folder.
  2. Local Gaia DR3 catalog, G <= gaia_local_gmax, into gaia_local_dir (pyoccult_config.py). Needed by search.py
     (corridor mode). Two ways, same result:
       zenodo: download the ready-made copy (doi:10.5281/zenodo.23113337; G <= 18: 8.2 GB, G <= 16: 2.1 GB), check
               its SHA-256 and unpack it (~11 / ~3 GB). Only for G <= 16 and 18. Resumable.
       esa:    build it from ESA's bulk files: 753 GB streamed, ~11 GB kept for G <= 18, about 1.5-2 h at
               1.4 Gbit/s. Any limit. Resumable.
     In a terminal, setup first asks for the limit (Enter = 16; skipped with --gmax), then --source auto (default)
     asks zenodo or esa (Enter = zenodo). Without a terminal: the config's limit, zenodo. auto resumes an interrupted
     esa build, and uses esa for limits Zenodo does not have.
  3. Bright-star index (G <= 15, ~1.3 GB) next to the catalog, for pick.py. ~30 s.
"""
from pyoccult.version import __version__
import argparse, os, shutil, sys

from pyoccult import home
from pyoccult.home import PKG


def own_data(folder):
    """True if folder holds data of your own (not just the files PyOccult creates from its templates)."""
    if not os.path.isdir(folder):
        return False
    example = os.path.join(PKG, "templates", "sites_example.py")
    for n in os.listdir(folder):
        if n in ("__pycache__", "pyoccult_config.py"):
            continue
        if n == "sites.py":
            with open(os.path.join(folder, n)) as f, open(example) as g:
                if f.read() == g.read():
                    continue
        return True
    return False


def choose_home(argv):
    """The data folder for this and all later runs: `--home <folder>` sets it; the first setup of an installed copy
    (no setting, not a checkout) asks for it. Saved in home.POINTER; returns the folder."""
    if "--home" in argv:
        i = argv.index("--home")
        if i + 1 >= len(argv):
            sys.exit("--home needs a folder")
        old, new = home.HOME, home.save(argv[i + 1])
        home.HOME, home.SOURCE = new, "setting"
        print(f"data folder: {new}  (saved in {home.POINTER})")
        if os.path.realpath(old) != os.path.realpath(new) and own_data(old):
            print(f"   your files are still in {old}: move what you want to keep yourself (sites.py, "
                  f"pyoccult_config.py, picks/, favorites/, ...; the Gaia catalog folders can be moved or linked)")
    elif home.SOURCE == "default" and sys.stdin.isatty() and "--status" not in argv:
        print("PyOccult keeps its data in one folder: your sites and settings, the SPICE kernels, the Gaia catalog "
              "(3-11 GB),\nsaved picks, favorites and results.")
        k = input(f"   data folder [Enter = {home.DEFAULT}]: ").strip()
        home.HOME, home.SOURCE = home.save(k or home.DEFAULT), "setting"
        print(f"   data folder: {home.HOME}  (saved in {home.POINTER}; change it later with --home)")
    os.makedirs(home.HOME, exist_ok=True)
    return home.HOME


HOME = choose_home(sys.argv)
os.chdir(HOME)                                                      # kernels, catalogs, sites.py live in the data folder
EXAMPLE = os.path.join(PKG, "templates", "sites_example.py")
from pyoccult import geo

SITES_HINT = """   Edit sites.py and enter your observing site(s), then rerun or just start searching:
     - lat, lon: geodetic degrees, longitude east-positive (west is negative); ele: metres
     - optional view: min_alt, max_sun_alt, reach_km; equipment: aperture_cm, frames, mag_adjust, extinction
       (all keys are explained at the top of pyoccult/templates/sites_example.py in the PyOccult code)
     - default_site names the site used; PYOCCULT_SITE=<name> picks another one for a single run
   sites.py stays private (it is in .gitignore)."""


APPROX = "APPROXIMATE"                       # marker in a generated sites.py: position not yet the exact one


def _get_json(url, timeout=10):
    return geo.get_json(url, timeout)


def _elevation(lat, lon):
    return geo.elevation(lat, lon)


def _ip_guess():
    """(lat, lon, ele, label) from the IP address (ipinfo.io; city level, 10-100 km, wrong behind a VPN), or None."""
    r = geo.ip_location()
    if r is None:
        print("   IP lookup failed")
    return r


def _city(name):
    """Pick a place from Open-Meteo's geocoding: (lat, lon, ele, label) or None."""
    res = geo.places(name)
    if not res:
        print(f"   no place called {name!r} found (or offline)")
        return None
    for i, (lat, lon, ele, label) in enumerate(res, 1):
        print(f"   {i}. {label}: {lat:.4f}, {lon:.4f}, {ele or 0:.0f} m")
    k = input(f"   which one [1-{len(res)}, Enter = 1]: ").strip() or "1"
    if not (k.isdigit() and 1 <= int(k) <= len(res)):
        return None
    return res[int(k) - 1]


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
        f.write(f"""# Your observing sites (not in git). Layout and optional keys: see src/pyoccult/templates/sites_example.py.
# pyoccult_config.py uses `default_site`, or the site named in the environment variable PYOCCULT_SITE.
# Created by setup.py on {date.today()}.

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
    if not os.path.isfile(EXAMPLE):
        sys.exit(f"sites.py and {EXAMPLE} are both missing: reinstall PyOccult (git checkout or pip)")
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
                shutil.copyfile(EXAMPLE, "sites.py")
                break
        print("   wrote sites.py")
        print(SITES_HINT)
        print()
        return True
    shutil.copyfile(EXAMPLE, "sites.py")
    print("WARNING: no sites.py found: created it from the example (site: New York City Hall).")
    print(SITES_HINT)
    print()
    return True


SITES_CREATED = ensure_sites(geoip="--no-geoip" not in sys.argv)   # before the config reads it
from pyoccult import config
from pyoccult import gaia_local as gaia
from pyoccult.kernels import KERNELS, download_kernels


def show_status(d=None):
    print(f"  data folder                  {home.describe()}")
    with open("sites.py") as f:
        example = f.read() == open(EXAMPLE).read() if os.path.isfile(EXAMPLE) else False
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
    found = gaia.find_catalogs(".")
    if len(found) > 1 or (found and found[0][0] != d):
        print("  catalogs found (choose with gaia_local_dir, or PYOCCULT_CATALOG=<folder> for one run):")
        for f, g, ok, gb in found:
            print(f"    {f:18s} G <= {g:g}, {gb:.1f} GB" + ("" if ok else ", INCOMPLETE") + ("   <- in use" if f == d else ""))


def index_limit(d):
    """Bright-star index limit for the pick tool: whole magnitudes >= 15, but never past the catalog's own limit."""
    lim = gaia.index_gmax(getattr(config, "pick_cam_limit", 15.0))
    try:
        import json
        lim = min(lim, json.load(open(os.path.join(d, "catalog.json")))["gmax"])
    except (OSError, ValueError, KeyError):
        pass
    return float(lim)


ZENODO_GB = {16.0: 2.1, 18.0: 8.2}                  # download sizes, for the question only


def catalog_source(source, d, gmax, st):
    """'zenodo' or 'esa' for building catalog d (status st) to G <= gmax; source is the --source option."""
    if source == "zenodo" and gmax not in gaia.ZENODO_GMAX:
        sys.exit(f"   Zenodo has catalogs for G <= 16 and 18 only, not {gmax:g}: use --source esa")
    if source != "auto":
        return source
    if gmax not in gaia.ZENODO_GMAX:
        print(f"   no ready-made catalog for G <= {gmax:g} on Zenodo (16 and 18 only): building from ESA's files")
        return "esa"
    if st["done"]:
        print(f"   resuming the ESA build ({st['done']}/{st['total']} files done); --source zenodo downloads instead")
        return "esa"
    if not sys.stdin.isatty():
        return "zenodo"
    gb = ZENODO_GB.get(gmax, 0)
    k = input(f"   [Enter] download the ready-made catalog from Zenodo ({gb:g} GB), or [b]uild it from ESA's files "
              f"(753 GB streamed, 1.5-2 h): ").strip().lower()
    return "esa" if k.startswith("b") else "zenodo"


def ask_gmax(default):
    """Ask for the catalog's magnitude limit (terminal only). Returns a float G."""
    print("   Faintest star (Gaia G) kept in the local catalog; fainter stars are never searched:")
    print(f"     16   ~3 GB on disk;  ready-made on Zenodo ({ZENODO_GB[16.0]:g} GB download); enough for most telescopes")
    print(f"     18   ~11 GB on disk; ready-made on Zenodo ({ZENODO_GB[18.0]:g} GB download); for large apertures")
    print("     other limits are built from ESA's files (753 GB streamed, 1.5-2 h)")
    while True:
        k = input(f"   limit [Enter = {default:g}]: ").strip()
        try:
            g = float(k) if k else default
        except ValueError:
            continue
        if 6.0 <= g <= 21.0:
            return g
        print("   a Gaia G between 6 and 21, please")


def catalog_target(gmax_arg, dir_arg):
    """(folder, gmax) for the Gaia build: --gmax / --dir, else the config. One folder holds one limit: a folder named
    gaia_dr3_g<N> is used only for G <= N, any other limit goes to its own gaia_dr3_g<gmax> (unless --dir)."""
    import re
    cfg_dir = getattr(config, "gaia_local_dir", None) or "gaia_dr3_g16"
    cfg_gmax = float(getattr(config, "gaia_local_gmax", 16.0))
    gmax = cfg_gmax if gmax_arg is None else float(gmax_arg)
    m = re.fullmatch(r"gaia_dr3_g(\d+(?:\.\d+)?)", os.path.basename(os.path.normpath(cfg_dir)))
    fits = float(m.group(1)) == gmax if m else gmax == cfg_gmax
    d = dir_arg or (cfg_dir if fits else f"gaia_dr3_g{gmax:g}")
    return d, gmax


def network_failure(e, d, source):
    """Message for a failed catalog step (no traceback): what failed, the likely cause, how to go on."""
    other = {"zenodo": "--source esa (build from ESA's files)", "esa": "--source zenodo (ready-made, G <= 16 or 18)"}
    return (f"\n   catalog step failed: {type(e).__name__}: {str(e)[:300]}\n"
            f"   Likely: offline, the server is down, or a proxy/firewall blocks the address (see urls.py).\n"
            f"   - behind a proxy: export https_proxy=http://<proxy>:<port>  (and HTTPS_PROXY), then rerun\n"
            f"   - rerun later: setup resumes, files already in {d} are kept\n"
            + (f"   - or try the other source: pyoccult setup {other[source]}\n" if source in other else "")
            + "   - or copy a finished catalog folder from another computer (gaia_dr3_g16 / gaia_dr3_g18)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"PyOccult {__version__}")
    ap.add_argument("--no-gaia", action="store_true", help="kernels only")
    ap.add_argument("--status", action="store_true", help="only show what is installed")
    ap.add_argument("--no-geoip", action="store_true", help="do not guess the site from the IP address")
    ap.add_argument("--workers", type=int, default=6, help="parallel Gaia downloads")
    ap.add_argument("--gmax", type=float, help="faintest Gaia G kept in the local catalog (default: config "
                                               "gaia_local_gmax, 16); a new limit needs its own folder")
    ap.add_argument("--dir", help="catalog folder (default: config gaia_local_dir, or gaia_dr3_g<gmax> for another --gmax)")
    ap.add_argument("--source", choices=["auto", "zenodo", "esa"], default="auto",
                    help="catalog from Zenodo (ready-made, G <= 16 or 18) or built from ESA's files; auto asks")
    ap.add_argument("--keep-archive", action="store_true", help="keep the downloaded Zenodo .tar.xz")
    ap.add_argument("--home", metavar="FOLDER", help="use FOLDER as the data folder from now on (saved as a setting; "
                                                     "files are not moved)")
    a = ap.parse_args()
    if a.status:
        show_status(catalog_target(a.gmax, a.dir)[0] if (a.gmax is not None or a.dir) else None)
        sys.exit(0)
    print("1. SPICE kernels")
    if not download_kernels(config.earth_pck_max_age):
        sys.exit("kernel download failed (see above); rerun setup when the address is reachable, or copy the kernel "
                 "files (*.tls, *.bsp, *.tpc, *.bpc) from another computer into this folder")
    d = None
    if not a.no_gaia:
        d, gmax = catalog_target(a.gmax, a.dir)
        st = gaia.status(d)
        if not st["complete"] and a.gmax is None and sys.stdin.isatty():   # new catalog: ask its limit first
            print("2. local Gaia catalog")
            ask = st["gmax"] if st["total"] else (gmax if gmax in gaia.ZENODO_GMAX else 16.0)
            d, gmax = catalog_target(ask_gmax(ask), a.dir)
            st = gaia.status(d)
            print(f"   G <= {gmax:g} in {d}")
        else:
            print(f"2. local Gaia catalog G <= {gmax:g} in {d}")
            if not st["complete"] and a.gmax is None and not sys.stdin.isatty():
                print(f"   note: no terminal (background run), so no questions: catalog limit G <= {gmax:g} from "
                      f"pyoccult_config.py; give --gmax (and --source) to choose")
        if st["total"] and abs(st.get("gmax", gmax) - gmax) > 1e-9:
            what = (f"a {'complete' if st['complete'] else 'half-built'} catalog with G <= {st['gmax']:g} "
                    f"({st['done']}/{st['total']} files, {st['gb']:.1f} GB)")
            if not sys.stdin.isatty():
                sys.exit(f"   {d} already holds {what}. Delete that folder, or use --dir for G <= {gmax:g}")
            k = input(f"   {d} already holds {what}.\n   [d]elete it and install G <= {gmax:g} there, "
                      f"or [Enter] cancel: ").strip().lower()
            if k != "d":
                sys.exit(f"   cancelled; use --dir <folder> to install G <= {gmax:g} elsewhere")
            shutil.rmtree(d)
            print(f"   deleted {d}")
            st = gaia.status(d)
        src = None
        try:
            if st["complete"]:
                print("   complete")
            elif (src := catalog_source(a.source, d, gmax, st)) == "zenodo":
                gaia.fetch_zenodo(d, gmax, a.keep_archive)
            else:
                gaia.build(d, gmax, a.workers)
            if not gaia.status(d)["complete"]:
                sys.exit(f"\n   catalog {d} is not complete yet: rerun setup to resume (nothing is lost)")
            print("3. bright-star index")
            gaia.BrightIndex(d, index_limit(d))
            print("   ok")
        except (OSError, RuntimeError, ValueError, KeyError) as e:  # network (requests' errors are OSErrors), disk
            sys.exit(network_failure(e, d, src if gmax in gaia.ZENODO_GMAX else None))
        if d != getattr(config, "gaia_local_dir", None) or gmax != float(getattr(config, "gaia_local_gmax", 16.0)):
            print(f"\n   To search with this catalog, set in pyoccult_config.py:\n"
                  f"       gaia_local_dir = \"{d}\"\n       gaia_local_gmax = {gmax:g}")
    print()
    show_status(d)
    if not a.no_gaia:
        print("\n  Another catalog later: pyoccult setup --gmax 16   (or 18, or any limit via ESA); "
              "it goes into its own folder\n  gaia_dr3_g<limit>, and the GUI's catalog selector lists it.")


if __name__ == "__main__":
    sys.exit(main())
