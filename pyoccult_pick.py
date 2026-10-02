#!.venv/bin/python3
"""pyoccult_pick.py - find the actual occultation events at your site for all asteroids, OWC-style, and choose the
`targets` list for pyoccult.py from the best of them.

Pipeline
  1. asteroids : JPL SBDB bulk query, full-precision elements (numbered, H < --hmax, or --all), cached as JSON
  2. paths     : every asteroid integrated with the planets over the window (pyoccult_orbits, ~0.01" vs Horizons)
  3. events    : actual Gaia stars (local catalog, bright-star index) along the path, solved for your site
                 (pyoccult_screen); only while the asteroid is up and the Sun is down
  4. detection : the star's magnitude sets the exposure your camera needs (aperture, reference exposure); an event
                 counts if it lasts --frames exposures and --min-dur seconds, and the drop is >= --min-drop.
                 Durations for this use the upper size bound, so H-only sizes are not dismissed too early.
  5. output    : pick_events.csv (all events), a ranked table, and targets.py with the asteroids of the best events.
                 Their size data goes to the shared size cache, so pyoccult.py needs no SBDB lookups for them.
                 pyoccult.py then computes the events exactly (Horizons SPK, exact solver, maps).

Defaults come from pyoccult_config.py (site, window ct/days, reach, altitude limits, pick_* settings).
Needs the kernels and the local Gaia catalog with its bright-star index: python pyoccult_setup.py
"""
import argparse, datetime as dt, json, math, os, sys, tempfile, time, urllib.parse, urllib.request
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyoccult_sbdb                                     # shared per-asteroid size cache

SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
SBDB_FIELDS = ["spkid", "full_name", "H", "G", "diameter", "diameter_sigma", "extent", "albedo", "a", "e", "i", "om",
               "w", "ma", "epoch", "condition_code", "neo", "class"]


# ---------------------------------------------------------------- SBDB
def fetch_sbdb(hmax, cache, max_age_s=None):
    """Bulk SBDB download of numbered asteroids with H < hmax (hmax None: all), full-precision elements. Cached (atomic
    write); reused while it covers hmax, has all SBDB_FIELDS in full precision and is younger than max_age_s (config
    sbdb_max_age_days). Returns (fields, data, fetched)."""
    max_age_s = pyoccult_sbdb.max_age_s() if max_age_s is None else max_age_s
    want = math.inf if hmax is None else hmax
    if cache and os.path.exists(cache):
        with open(cache) as f:
            blob = json.load(f)
        fetched = blob.get("fetched") or os.path.getmtime(cache)
        if (blob.get("hmax", 0) >= want and blob.get("full_prec") and set(SBDB_FIELDS) <= set(blob["fields"])
                and time.time() - fetched < max_age_s):
            return blob["fields"], blob["data"], fetched
    q = dict(fields=",".join(SBDB_FIELDS), **{"sb-kind": "a", "sb-ns": "n", "full-prec": "true"})
    if hmax is not None:
        q["sb-cdata"] = json.dumps({"AND": [f"H|LT|{hmax}"]})
    print(f"Downloading SBDB ({'all numbered' if hmax is None else f'H < {hmax}'}, full precision) ...", file=sys.stderr)
    with urllib.request.urlopen(SBDB_URL + "?" + urllib.parse.urlencode(q), timeout=1200) as r:
        blob = json.load(r)
    blob["hmax"], blob["fetched"], blob["full_prec"] = want, time.time(), True
    if cache:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(cache)), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(blob, f)
        os.replace(tmp, cache)
    return blob["fields"], blob["data"], blob["fetched"]


def to_float(x, default=float("nan")):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def build_rows(fields, data, hmax):
    """Asteroid dicts for the screen. Sizes follow pyoccult.get_asteroid_size: measured diameter (upper bound +3 sigma,
    15 % if no sigma) or, from H, albedo 0.14 nominal and 0.05 upper bound."""
    rows = []
    for r in data:
        d = dict(zip(fields, r))
        H, a, e = to_float(d["H"]), to_float(d["a"]), to_float(d["e"])
        if math.isnan(H) or not (a > 0 and 0 <= e < 0.99) or math.isnan(to_float(d["epoch"])):
            continue                                                       # no bound orbit or missing elements
        if hmax is not None and H >= hmax:
            continue
        spk = int(d["spkid"])
        D = to_float(d["diameter"])
        if D > 0:
            Dmax, est = D + 3 * to_float(d["diameter_sigma"], 0.15 * D), False
        else:
            Dp = lambda p: 1329.0 / math.sqrt(p) * 10 ** (-H / 5)
            D, Dmax, est = Dp(0.14), Dp(0.05), True
        G = to_float(d["G"])
        rows.append(dict(number=spk - 20000000 if spk >= 20000000 else spk - 2000000, spkid=spk,
                         name=(d["full_name"] or "").strip(), H=H, G=0.15 if math.isnan(G) else G, D_km=D, D_max_km=Dmax,
                         D_est=est, cc=to_float(d["condition_code"], 9.0), neo=d.get("neo") == "Y",
                         **{k: to_float(d[k]) for k in ("a", "e", "i", "om", "w", "ma", "epoch")}))
    return rows


# ---------------------------------------------------------------- screening (worker processes, own SPICE each)
_W = {}


def _init(folder, catalog_dir, cam_limit, lat, lon, ele):
    import spiceypy as spice
    import pyoccult_screen as SC, pyoccult_gaia_local as L
    os.chdir(folder)
    SC.load_kernels(spice, folder)
    _W.update(spice=spice, SC=SC, index=L.BrightIndex(catalog_dir, cam_limit), site=SC.Site(spice, lat, lon, ele))


def _screen_chunk(args):
    rows, et0, et1, opt = args
    return _W["SC"].screen(_W["spice"], rows, et0, et1, _W["site"], _W["index"], opt, chunk=max(len(rows), 1)), len(rows)


def run_screen(rows, et0, et1, opt, site_args, workers, chunk=2000):
    folder = os.path.dirname(os.path.abspath(__file__))
    jobs = [(rows[i:i + chunk], et0, et1, opt) for i in range(0, len(rows), chunk)]
    events, done, t0 = [], 0, time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(folder, *site_args)) as ex:
        for ev, n in ex.map(_screen_chunk, jobs):
            events += ev
            done += n
            el = time.time() - t0
            print(f"  {done}/{len(rows)} asteroids, {len(events)} events, {el:.0f} s, "
                  f"ETA {el / done * (len(rows) - done):.0f} s", file=sys.stderr, flush=True)
    return events


# ---------------------------------------------------------------- output
def write_targets(path, best, a):
    """Write an importable module:  from targets import targets, target_names"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# generated by pyoccult_pick.py on {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC\n")
        f.write(f"# events {a.start} + {a.days:g} d, site lat {a.lat}, reach {a.reach:g} km, G <= {a.cam_limit:g}, "
                f"{a.aperture:g} cm aperture, {a.frames} frames, min duration {a.min_dur:g} s, min drop {a.min_drop:g}\n")
        f.write(f"# order: best event first (sorted by {a.sort}); comment = that event\n\n")
        f.write("targets = [\n")
        for e in best:
            f.write(f"    {str(e['number'])!r},   # {e['name'][:28]:<28} {e['utc'][:16]}  G {e['star_mag']:5.2f}  "
                    f"drop {e['drop']:5.2f}  dur {e['dur_s']:4.2f} s  miss {e['miss_km']:5.1f} km\n")
        f.write("]\n\ntarget_names = {\n")
        for e in best:
            f.write(f"    {str(e['number'])!r}: {e['name']!r},\n")
        f.write("}\n")


SORT_KEYS = {"mag": ["star_mag", "et"], "date": ["et"], "frames": ["n_frames"], "drop": ["drop"]}
SORT_ASC = {"mag": True, "date": True, "frames": False, "drop": False}


def main(argv=None):
    cfg = {}
    try:
        sys.path.insert(0, os.getcwd())
        import pyoccult_config as C
        g = lambda k, d: getattr(C, k, d)
        cfg = dict(lat=C.LAT, lon=C.LON, ele=C.ELE, reach=C.max_shadow_dist, min_alt=C.MIN_STAR_ALT,
                   sun=C.MAX_SUN_ALT, cache=C.cache_path, start=str(C.ct)[:10], days=C.days,
                   catalog=g("gaia_local_dir", "gaia_dr3_g18"), min_drop=g("min_mag_drop", 0.1),
                   cam_limit=g("pick_cam_limit", 15.0), aperture=g("pick_aperture_cm", 25.0),
                   ref_mag=g("pick_ref_mag", 12.5), ref_exp=g("pick_ref_exp_s", 0.08),
                   frames=g("pick_frames", 4), min_dur=g("pick_min_dur_s", 0.4), hmax=g("pick_hmax", 17.0))
    except (ImportError, AttributeError) as ex:
        print(f"note: pyoccult_config.py not usable ({ex}); give the site on the command line", file=sys.stderr)
    c = lambda k, d=None: cfg.get(k, d)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=c("start"), help="UTC date YYYY-MM-DD (default: config ct, else today)")
    ap.add_argument("--days", type=float, default=c("days", 30), help="window length (default: config days)")
    ap.add_argument("--hmax", type=float, default=c("hmax", 17.0), help="asteroids with H below this (default 17)")
    ap.add_argument("--all", action="store_true", help="exhaustive: all numbered asteroids, any H (~900k, slower)")
    ap.add_argument("--lat", type=float, default=c("lat"))
    ap.add_argument("--lon", type=float, default=c("lon"), help="east-positive degrees")
    ap.add_argument("--ele", type=float, default=c("ele", 0.0), help="site height, m")
    ap.add_argument("--reach", type=float, default=c("reach", 20.0), help="km you can travel from the site (max_shadow_dist)")
    ap.add_argument("--min-alt", type=float, default=c("min_alt", 10.0), help="minimum star altitude, deg")
    ap.add_argument("--max-sun-alt", type=float, default=c("sun", -6.0), help="Sun must be below this, deg")
    ap.add_argument("--min-drop", type=float, default=c("min_drop", 0.1), help="smallest useful magnitude drop")
    ap.add_argument("--cam-limit", type=float, default=c("cam_limit", 15.0), help="faintest star, G (bright-star index)")
    ap.add_argument("--aperture", type=float, default=c("aperture", 25.0), help="telescope aperture, cm")
    ap.add_argument("--ref-mag", type=float, default=c("ref_mag", 12.5), help="exposure calibration: a star of this G ...")
    ap.add_argument("--ref-exp", type=float, default=c("ref_exp", 0.08), help="... needs this exposure (s) at 25 cm")
    ap.add_argument("--frames", type=int, default=c("frames", 4), help="exposures the event must last (detection frames)")
    ap.add_argument("--min-dur", type=float, default=c("min_dur", 0.4), help="shortest event, s")
    ap.add_argument("--sort", choices=sorted(SORT_KEYS), default="mag", help="ranking (default: brightest star first)")
    ap.add_argument("--top", type=int, default=40, help="asteroids written to targets.py (best events first)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2), help="parallel processes")
    ap.add_argument("--catalog", default=c("catalog", "gaia_dr3_g18"), help="local Gaia catalog folder")
    ap.add_argument("--sbdb-cache", help="SBDB download cache (default: <config cache_path>/PyOccult_sbdb_cache.json)")
    ap.add_argument("-o", "--output", default="pick_events.csv")
    ap.add_argument("--targets-file", default="targets.py", help="importable targets list ('' to skip)")
    a = ap.parse_args(argv)
    if a.lat is None or a.lon is None:
        ap.error("need --lat and --lon (no pyoccult_config.py found)")
    a.start = a.start or dt.datetime.utcnow().strftime("%Y-%m-%d")
    if a.sbdb_cache is None:
        a.sbdb_cache = os.path.join(c("cache") or tempfile.gettempdir(), "PyOccult_sbdb_cache.json")

    hmax = None if a.all else a.hmax
    fields, data, fetched = fetch_sbdb(hmax, a.sbdb_cache)
    rows = build_rows(fields, data, hmax)
    import spiceypy as spice
    import pyoccult_screen as SC
    SC.load_kernels(spice, os.path.dirname(os.path.abspath(__file__)))
    et0 = spice.str2et(a.start + "T00:00:00")
    et1 = et0 + a.days * 86400.0
    opt = dict(reach_km=a.reach, min_alt=a.min_alt, max_sun_alt=a.max_sun_alt, min_drop=a.min_drop,
               min_dur=a.min_dur, cam_limit=a.cam_limit, aperture=a.aperture, ref_aperture=25.0,
               ref_mag=a.ref_mag, ref_exp=a.ref_exp, frames=a.frames)
    print(f"{len(rows)} asteroids, {a.start} + {a.days:g} d, site {a.lat:.4f} {a.lon:.4f}, reach {a.reach:g} km, "
          f"G <= {a.cam_limit:g}, {a.workers} workers", file=sys.stderr)
    t0 = time.time()
    ev = run_screen(rows, et0, et1, opt, (a.catalog, a.cam_limit, a.lat, a.lon, a.ele), a.workers)
    print(f"screened in {time.time() - t0:.0f} s: {len(ev)} events", file=sys.stderr)

    E = pd.DataFrame(ev)
    if E.empty:
        print("no events found")
        return 0
    E["utc"] = [spice.et2utc(x, "ISOC", 0) for x in E.et]
    E = E.sort_values(SORT_KEYS[a.sort], ascending=SORT_ASC[a.sort]).reset_index(drop=True)
    cols = ["number", "name", "utc", "star", "star_mag", "drop", "dur_s", "dur_max_s", "n_frames", "exposure_s",
            "miss_km", "inside", "star_alt", "sun_alt", "m_ast", "D_km", "D_est", "speed_kms", "cc", "star_ra",
            "star_dec", "et"]
    E[cols].to_csv(a.output, index=False, float_format="%.6g")
    print(f"{'#':>7} {'name':<26} {'UT':<19} {'G':>5} {'drop':>5} {'dur':>5}  {'frm':>5} {'miss':>6} {'alt':>4}")
    for e in E.head(max(a.top, 20)).itertuples():
        print(f"{e.number:>7} {e.name[:26]:<26} {e.utc[:19]:<19} {e.star_mag:5.2f} {e.drop:5.2f} "
              f"{e.dur_s:5.2f}{'~' if e.D_est else ' '}{e.n_frames:6.1f} {e.miss_km:6.1f} {e.star_alt:4.0f}")
    best = E.drop_duplicates("number").head(a.top).to_dict("records")
    if a.targets_file:
        write_targets(a.targets_file, best, a)
    raw = {int(r[fields.index("spkid")]): dict(zip(fields, r)) for r in data}
    n_put = pyoccult_sbdb.put({str(e["number"]): pyoccult_sbdb.entry_from_bulk(raw[int(e["spkid"])], fetched)
                               for e in best if int(e["spkid"]) in raw}, c("cache"))
    print(f"\nall events: {a.output}   (~ = diameter from H; dur is nominal, detection uses the upper size bound)")
    if a.targets_file:
        print(f"targets of the best {len(best)} events: {a.targets_file}   ->   from targets import targets")
    print(f"size data of {n_put} targets -> {pyoccult_sbdb.cache_file(c('cache'))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
