"""pathcheck.py - a favorite's geodetic shadow path, fresh, and its comparison with Occult's path listing.

    pysyzygos path-check run <key>                    # our path now: the search for this event only (today's orbit,
                                                      # this code), its path file and orbit files into the favorite
    pysyzygos path-check export <key> [--step 1.45]   # our path as a text table in Occult's layout
    pysyzygos path-check compare <key> <listing.txt>  # compare with Occult's listing: Markdown + CSV
    pysyzygos path-check keep <key>                   # also into owc_refs/occult_paths/ (private), with an index line

Files go to favorites/<key>/pathcheck/: path.npz (debug_save_paths of the search), the asteroid's SPK files (so a later
comparison uses the same orbit), meta.json (version, orbit solution, run time), our listing, Occult's listing as
given, compare_<stamp>.md / .csv. The method is that of VERIFICATION.md section 3: our path at exactly Occult's times
(paths.shadow_path, with each ground point's own light time), across / along the track, and in the fundamental plane
against the shadow axis as each point sees it (SPICE spkcpo), with a least-squares fit (constant offset; constant +
Earth rotation as a check). Both should be computed on the same day: the orbit changes.
"""
from pysyzygos.version import __version__
import argparse, calendar, glob, json, math, os, re, shutil, subprocess, sys, time
import numpy as np

DIRNAME = "pathcheck"
C_KMS = 299792.458
OMEGA_EARTH = 7.2921150e-5                                  # rad/s
SAMPLE_FRACTIONS = np.linspace(0.0, 1.0, 11)                # the rows shown in the report: start to end
ROUNDING_M = 31.0                                           # Occult's listing: whole arcseconds, ~31 m in latitude


# ----------------------------------------------------------------------------------------------- Occult's listing
def dms(tok):
    """['-15', '40', '42'] or ['-0', '59', '6'] -> degrees (the sign on the first token, also for -0)."""
    neg = tok[0].startswith("-")
    v = abs(float(tok[0])) + float(tok[1]) / 60.0 + float(tok[2]) / 3600.0
    return -v if neg else v


def parse_listing(text):
    """Rows of an Occult path listing (centre, UT, star alt/az, Sun alt, path limits 1/2, error limits 1/2): list of
    dicts lon, lat, sec (UT seconds of the day), star_alt, star_az, sun_alt, l1, l2, e1, e2 (lon, lat pairs). Signs
    stand apart for short degrees ("- 9 57 38"); header and other lines are skipped. Also returns the title line."""
    rows, title = [], ""
    for line in text.splitlines():
        if not title and line.strip().lower().startswith("occultation of"):
            title = line.strip()
        t = line.split()
        merged, i = [], 0
        while i < len(t):
            if t[i] == "-" and i + 1 < len(t):
                merged.append("-" + t[i + 1]); i += 2
            else:
                merged.append(t[i]); i += 1
        if len(merged) < 20 or not re.fullmatch(r"-?\d+", merged[0]):
            continue
        try:
            lon, lat = dms(merged[0:3]), dms(merged[3:6])
            h, m, s = int(merged[6]), int(merged[7]), float(merged[8])
            star_alt, star_az, sun_alt = float(merged[9]), float(merged[10]), float(merged[11])
            lim = [dms(merged[12 + 3 * k: 15 + 3 * k]) for k in range(8)]
        except (ValueError, IndexError):
            continue
        rows.append(dict(lon=lon, lat=lat, sec=h * 3600 + m * 60 + s, star_alt=star_alt, star_az=star_az,
                         sun_alt=sun_alt, l1=(lim[0], lim[1]), l2=(lim[2], lim[3]), e1=(lim[4], lim[5]),
                         e2=(lim[6], lim[7])))
    return rows, title


def parse_header(text):
    """Optional facts from Occult's plot header pasted with the listing: orbit ("JPL#1016"), the star's astrometric
    RA/Dec ("RA = 5 20 54.7283", "Dec = 40 53 5.373"), the asteroid's diameter ("Dia = 5.0"). Missing ones are None."""
    out = dict(jpl=None, star_ra=None, star_dec=None, dia_km=None)
    if m := re.search(r"JPL#\s*(\d+)", text):
        out["jpl"] = m[1]
    if m := re.search(r"\bRA\s*=?\s*(\d+)\s+(\d+)\s+([\d.]+)", text):
        out["star_ra"] = 15.0 * (int(m[1]) + int(m[2]) / 60.0 + float(m[3]) / 3600.0)
    if m := re.search(r"\bDec\s*=?\s*([+-]?)\s*(\d+)\s+(\d+)\s+([\d.]+)", text):
        v = int(m[2]) + int(m[3]) / 60.0 + float(m[4]) / 3600.0
        out["star_dec"] = -v if m[1] == "-" else v
    if m := re.search(r"Dia\s*=\s*([\d.]+)\s*(?:\+-|±)?", text):
        out["dia_km"] = float(m[1])
    return out


def fmt_dms(v, width=3):
    """Degrees -> Occult's '- 15 40 42' (sign apart, degrees right-aligned, whole seconds)."""
    sign = "-" if v < 0 else " "
    a = round(abs(v) * 3600.0)
    d, rest = divmod(a, 3600)
    m, s = divmod(rest, 60)
    return f"{sign}{d:{width}d} {m:2d} {s:2d}"


def fmt_ut(sec):
    h, rest = divmod(sec, 3600.0)
    m, s = divmod(rest, 60.0)
    return f"{int(h):2d} {int(m):2d} {s:5.2f}"


# ----------------------------------------------------------------------------------------------- the comparison math
def fit_plane(px, py, dvx, dvy, drx, dry):
    """Least squares of the plane offsets (km, per point) for (a) a constant offset and (b) a constant offset plus an
    Earth-rotation angle (partials drx, dry per radian). Returns {"const": (cx, cy, rms_km, max_km),
    "rot": (cx, cy, angle_rad, rms_km, max_km, s_cx, s_cy, s_angle)}; dvx/dvy (the shadow's motion) are kept for the
    direction of the offset."""
    n = len(px)
    y = np.column_stack([px, py]).reshape(-1)
    ex, ey = np.tile([1.0, 0.0], n), np.tile([0.0, 1.0], n)
    out = {}
    A = np.column_stack([ex, ey])
    sol, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ sol
    out["const"] = (sol[0], sol[1], float(np.sqrt(np.mean(res ** 2))), float(np.abs(res).max()))
    A = np.column_stack([ex, ey, np.column_stack([drx, dry]).reshape(-1)])
    sol, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ sol
    rms = float(np.sqrt(np.mean(res ** 2)))
    sig = np.sqrt(rms ** 2 * np.diag(np.linalg.inv(A.T @ A)))
    out["rot"] = (sol[0], sol[1], sol[2], rms, float(np.abs(res).max()), sig[0], sig[1], sig[2])
    return out


def sample_rows(rows):
    """Indices of the rows shown in the report: SAMPLE_FRACTIONS of the way through the listing."""
    n = len(rows)
    return sorted({int(round(f * (n - 1))) for f in SAMPLE_FRACTIONS}) if n else []


def summary(points):
    """Statistics of the compared points (dicts with across, along, dt, star_alt): all and star above 20 deg."""
    out = {}
    for label, sel in (("all", [p for p in points]), ("alt20", [p for p in points if p["star_alt"] >= 20])):
        if not sel:
            continue
        a = np.array([[p["across"], p["along"], p["dt"], p["dist"]] for p in sel])
        out[label] = dict(n=len(sel), across_min=a[:, 0].min(), across_max=a[:, 0].max(), across_mean=a[:, 0].mean(),
                          along_mean=a[:, 1].mean(), dt_min=a[:, 2].min(), dt_max=a[:, 2].max(),
                          dt_mean=a[:, 2].mean(), dist_max=a[:, 3].max())
    return out


def verdict(stats, fit, mas_per_km, speed_kms):
    """One line: across within the listing's rounding or not, the time difference, the plane offset."""
    s = stats.get("alt20") or stats["all"]
    acr = max(abs(s["across_min"]), abs(s["across_max"])) * 1000.0
    cx, cy, rms, _ = fit["const"]
    off = math.hypot(cx, cy)
    across = (f"across the track within the listing's rounding (largest {acr:.0f} m, rounding ~{ROUNDING_M:.0f} m)"
              if acr <= 1.5 * ROUNDING_M else f"across the track up to {acr:.0f} m (rounding ~{ROUNDING_M:.0f} m)")
    return (f"{across}; along the track Occult {'later' if s['dt_mean'] < 0 else 'earlier'} by "
            f"{abs(s['dt_mean']) * 1000:.0f} ms (mean); offset in the fundamental plane {off * 1000:.0f} m "
            f"({off * mas_per_km:.2f} mas), {rms * 1000:.0f} m rms around it")


def markdown(meta, title, header, points, stats, fit, mas_per_km, speed_kms, our_dia_km):
    """The report (Markdown), laid out like VERIFICATION.md section 3."""
    hms = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"
    L = [f"# Path check: {meta['target_name']} on {meta['best_utc'][:10]}", "",
         f"Occult: *{title or 'listing without a title line'}*. PySyzygos {meta['version']}, run "
         f"{meta['run_utc']} UTC, orbit {meta.get('orbit') or 'unknown'}. {len(points)} points compared.", "",
         "| | Occult | PySyzygos |", "|---|---|---|",
         f"| Orbit | {('JPL#' + header['jpl']) if header.get('jpl') else '(not given)'} | {meta.get('orbit') or '?'} |",
         f"| Star | {('RA %.6f, Dec %.6f (printed astrometric)' % (header['star_ra'], header['star_dec'])) if header.get('star_ra') is not None else '(not given)'} "
         f"| Gaia DR3 {meta['star']}, RA {meta['star_ra']:.6f}, Dec {meta['star_dec']:.6f} (with parallax, deflection) |",
         f"| Diameter | {('%.2f km' % header['dia_km']) if header.get('dia_km') else '(not given)'} | {our_dia_km:.2f} km |",
         ""]
    ours_id = re.search(r"\d+", str(meta.get("orbit") or ""))
    if header.get("jpl") and ours_id and header["jpl"] != ours_id[0]:
        L += [f"**Different orbit solutions** (Occult JPL#{header['jpl']}, PySyzygos {meta['orbit']}): differences "
              f"below then include the orbit.", ""]
    L += ["Occult minus PySyzygos at Occult's times; across: positive to the left of the shadow's motion; plane: the "
          "point minus the shadow axis as that point sees it (x east, y north).", "",
          "| UT | Star alt | Across (km) | Along (km) | Along (s) | Path width Occult / ours (km) | Plane x, y (km) | (mas) |",
          "|---|---|---|---|---|---|---|---|"]
    for i in sample_rows(points):
        p = points[i]
        L.append(f"| {hms(p['utc'])} | {p['star_alt']:.0f} | {p['across']:+.3f} | {p['along']:+.3f} | {p['dt']:+.3f} | "
                 f"{p['w_occ']:.2f} / {p['w_our']:.2f} | {p['px']:+.3f}, {p['py']:+.3f} | "
                 f"{p['px'] * mas_per_km:+.2f}, {p['py'] * mas_per_km:+.2f} |")
    L.append("")
    for key, label in (("all", "All points"), ("alt20", "Star above 20 deg")):
        if key in stats:
            s = stats[key]
            L.append(f"- **{label}** ({s['n']}): across {s['across_min']:+.3f} to {s['across_max']:+.3f} km "
                     f"(mean {s['across_mean']:+.3f}); along {s['dt_min']:+.3f} to {s['dt_max']:+.3f} s "
                     f"(mean {s['dt_mean']:+.3f} s); largest distance {s['dist_max']:.3f} km.")
    cx, cy, rms, mx = fit["const"]
    rx, ry, ang, rrms, rmx, scx, scy, sang = fit["rot"]
    L += ["", "| Fit in the fundamental plane | Result | rms (max) |", "|---|---|---|",
          f"| constant offset | x {cx:+.3f} km ({cx * mas_per_km:+.2f} mas), y {cy:+.3f} km ({cy * mas_per_km:+.2f} mas) "
          f"| {rms * 1000:.0f} m ({mx * 1000:.0f} m) |",
          f"| + Earth rotation (check) | x {rx:+.3f}, y {ry:+.3f} km, rotation = UT1 {ang / OMEGA_EARTH * 1000:+.0f} "
          f"+- {sang / OMEGA_EARTH * 1000:.0f} ms | {rrms * 1000:.0f} m ({rmx * 1000:.0f} m) |", "",
          f"Shadow speed in the plane {speed_kms:.2f} km/s; 1 km = {mas_per_km:.3f} mas at the target.", "",
          f"**Result:** {verdict(stats, fit, mas_per_km, speed_kms)}.", ""]
    return "\n".join(L)


# ----------------------------------------------------------------------------------------------- files
def fav_dir(key, folder=None):
    from pysyzygos import favorites
    return os.path.join(folder or favorites.DIR, key, DIRNAME)


def entry_of(key, folder=None):
    from pysyzygos import favorites
    for e in favorites.load(folder or favorites.DIR):
        if e["key"] == key:
            return e
    raise SystemExit(f"no favorite {key!r} (pysyzygos favorites lists them)")


def _orbit_id(target):
    """JPL's current orbit solution for an asteroid ("JPL#1016, 2026-10-14"), or None (bodies, offline)."""
    if ":" in str(target):
        return None
    try:
        from pysyzygos import geo, urls as U
        o = geo.get_json(f"{U.URL_JPL_SBDB_API}?sstr={target}", timeout=20).get("orbit", {})
        return f"JPL#{o.get('orbit_id')}, {str(o.get('soln_date', ''))[:10]}"
    except Exception:
        return None


# ----------------------------------------------------------------------------------------------- run
def run(key, folder=None):
    """Our path now: the search for this event only (target, star, site and time of the favorite; +-1 h; relaxed
    limits; debug_save_paths), as a separate process (search.py sets up SPICE at import). Writes path.npz, the SPK files
    used and meta.json into the favorite's pathcheck folder; returns that folder."""
    from pysyzygos import config, geoid, home
    e = entry_of(key, folder)
    r, site = e["record"], e.get("site") or {}
    out = os.path.abspath(fav_dir(key, folder))
    work = os.path.join(out, "run")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    t = time.strptime(r["best_utc"][:19], "%Y-%m-%dT%H:%M:%S")
    t0 = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(calendar.timegm(t) - 3600))
    lat, lon = float(site.get("lat", config.LAT)), float(site.get("lon", config.LON))
    ele = float(site.get("ele", 0.0))
    if site.get("ele_ref") != "ellipsoid":
        ele += float(site.get("geoid_m") if site.get("geoid_m") is not None else geoid.height(lat, lon))
    mag = float(r.get("mag") or 15.0)
    ov = dict(ct=t0, days=2.0 / 24.0, targets=[str(r["target_id"])], targets_source="list", LAT=lat, LON=lon, ELE=ele,
              MIN_STAR_ALT=-90.0, MAX_SUN_ALT=90.0, max_shadow_dist=1e5, MAG_MIN=mag + 0.5, min_mag_drop=0.0,
              pick_min_dur_s=0.0, debug_save_paths=True, write_maps=True, write_globes=False, map_dir=work,
              results_db=os.path.join(work, "check.db"), hits_output_cvs_file=os.path.join(work, "hits.csv"),
              results_new_series=True, gaia_online_check=False)
    env = dict(os.environ, PYSYZYGOS_HOME=home.HOME)
    print(f"path-check: search for {r.get('target_name', r['target_id'])} around {r['best_utc']} (fresh orbit)", flush=True)
    rc = subprocess.run([sys.executable, "-u", "-m", "pysyzygos", "run", "search", json.dumps(ov)], env=env).returncode
    if rc != 0:
        raise SystemExit(f"the search ended with code {rc}")
    found = []
    for f in glob.glob(os.path.join(work, "*_path.npz")):
        z = np.load(f, allow_pickle=False)
        if str(z["star"]) == str(r.get("star")):
            found.append((abs(_et_of(z) - _utc_sec(r["best_utc"])), f))
    if not found:
        raise SystemExit("the search did not find this event again (other star or time): see its output above")
    best = min(found)[1]
    shutil.copyfile(best, os.path.join(out, "path.npz"))
    tid = str(r["target_id"])
    from pysyzygos.report import file_id
    pats = [f"PySyzygos_asteroid_{tid}_*.bsp", f"PySyzygos_body_{file_id(tid)}*.bsp"]
    for old in glob.glob(os.path.join(out, "*.bsp")):
        os.remove(old)
    for p in pats:
        for f in glob.glob(os.path.join(config.cache_path, p)):
            shutil.copyfile(f, os.path.join(out, os.path.basename(f)))
    z = np.load(os.path.join(out, "path.npz"), allow_pickle=False)
    meta = dict(key=key, target_id=tid, target_name=str(z["target_name"]), star=str(z["star"]),
                best_utc=str(z["best_utc"]), version=str(z["version"]), run_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
                orbit=_orbit_id(tid))
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    shutil.rmtree(work, ignore_errors=True)
    print(f"path-check: our path saved in {out} (PySyzygos {meta['version']}, orbit {meta['orbit']})")
    return out


def _utc_sec(utc):
    return calendar.timegm(time.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S")) + (float("0" + utc[19:]) if utc[19:20] == "." else 0.0)


def _et_of(z):
    return _utc_sec(str(z["best_utc"]))


# ----------------------------------------------------------------------------------------------- SPICE side
def _load(out):
    """Kernels, the saved SPK files and the path file of a pathcheck folder: (spice, z, tid)."""
    import spiceypy as spice
    from pysyzygos import screen
    p = os.path.join(out, "path.npz")
    if not os.path.isfile(p):
        raise SystemExit(f"no path in {out}: run `pysyzygos path-check run <key>` first")
    screen.load_kernels(spice)
    spks = sorted(glob.glob(os.path.join(out, "*.bsp")))
    if not spks:
        raise SystemExit(f"no orbit file in {out}: run `pysyzygos path-check run <key>` again")
    for f in spks:
        spice.furnsh(f)
    z = np.load(p, allow_pickle=False)
    tid = str(z["target_id"])
    if ":" in tid:
        raise SystemExit("planets and moons are not supported by path-check yet")
    spice.boddef(tid, int(spice.spkobj(spks[-1])[0]))
    return spice, z, tid


def _ecef(lon, lat, h_km=0.0):
    from pysyzygos import earth
    lo, la = math.radians(lon), math.radians(lat)
    e2 = earth.F * (2 - earth.F)
    n = earth.A_KM / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return np.array([(n + h_km) * math.cos(la) * math.cos(lo), (n + h_km) * math.cos(la) * math.sin(lo),
                     (n * (1 - e2) + h_km) * math.sin(la)])


def compare(out, listing_text, header_text=""):
    """Our path (pathcheck folder `out`) at Occult's times against its listing. Returns (markdown, points, stats, fit)."""
    from pysyzygos import paths
    rows, title = parse_listing(listing_text)
    if not rows:
        raise SystemExit("no rows recognised in the listing (Occult's 'predicted path' table is expected)")
    header = parse_header(header_text + "\n" + listing_text)
    spice, z, tid = _load(out)
    meta = json.load(open(os.path.join(out, "meta.json")))
    meta.update(star_ra=float(z["star_ra"]), star_dec=float(z["star_dec"]))
    star_dir, r_km, s3 = z["star_dir"], float(z["r_km"]), float(z["sigma3_km"])
    x_ax, y_ax, z_ax = paths.plane_basis(star_dir)
    et0 = spice.str2et(str(z["best_utc"])[:10] + " 00:00:00 UTC")

    def ours(et):
        p = paths.shadow_path(tid, star_dir, et, r_km, s3, half_span=0.0, step=1.0)
        g = lambda k: (p[k][0][1], p[k][0][2]) if p[k] else None
        return g("center"), g("edge_plus"), g("edge_minus")

    points = []
    for r in rows:
        et = et0 + r["sec"]
        c0, ep, em = ours(et)
        c1, _, _ = ours(et + 0.5)
        if c0 is None or c1 is None:
            continue
        P, P1, Q = _ecef(*c0), _ecef(*c1), _ecef(r["lon"], r["lat"])
        v = (P1 - P) / 0.5
        speed = float(np.linalg.norm(v))
        u = v / speed
        n = np.cross(P / np.linalg.norm(P), u)
        d = Q - P
        w_occ = float(np.linalg.norm(_ecef(*r["l1"]) - _ecef(*r["l2"])))
        w_our = float(np.linalg.norm(_ecef(*ep) - _ecef(*em))) if ep and em else float("nan")
        # the fundamental plane: Occult's point minus the shadow axis as that point sees it (light time from the point)
        rel = np.asarray(spice.spkcpo(tid, et, "J2000", "OBSERVER", "CN", Q, "399", "ITRF93")[0][:3])
        a0 = np.asarray(spice.spkpos(tid, et - 0.5, "J2000", "CN", "399")[0])
        a1 = np.asarray(spice.spkpos(tid, et + 0.5, "J2000", "CN", "399")[0])
        rot = spice.pxform("ITRF93", "J2000", et) @ np.cross([0.0, 0.0, 1.0], Q)
        points.append(dict(utc=r["sec"], star_alt=r["star_alt"], across=float(d @ n), along=float(d @ u),
                           dt=float(d @ u) / speed, dist=float(np.linalg.norm(d)), w_occ=w_occ, w_our=w_our,
                           px=float(-(rel @ x_ax)), py=float(-(rel @ y_ax)),
                           dvx=float(-((a1 - a0) @ x_ax)), dvy=float(-((a1 - a0) @ y_ax)),
                           drx=float(rot @ x_ax), dry=float(rot @ y_ax), dist_target=float(np.linalg.norm(rel))))
    if len(points) < 3:
        raise SystemExit("fewer than 3 of Occult's points lie on our path's time span (other event or date?)")
    A = lambda k: np.array([p[k] for p in points])
    fit = fit_plane(A("px"), A("py"), A("dvx"), A("dvy"), A("drx"), A("dry"))
    stats = summary(points)
    mas_per_km = 206264806.247 / float(np.mean(A("dist_target")))
    speed = float(np.hypot(A("dvx").mean(), A("dvy").mean()))
    md = markdown(meta, title, header, points, stats, fit, mas_per_km, speed, 2 * r_km)
    return md, points, stats, fit


def export(out, step=1.45):
    """Our path (pathcheck folder `out`) as a text table in Occult's layout: centre, UT, star alt/az, Sun alt, the
    shadow limits and the 1-sigma limits, every `step` seconds while the centre is on the Earth."""
    from pysyzygos import paths
    spice, z, tid = _load(out)
    star_dir, r_km, s3 = z["star_dir"], float(z["r_km"]), float(z["sigma3_km"])
    p = paths.shadow_path(tid, star_dir, float(z["best_et"]), r_km, s3, step=step)
    by = {k: {round(e, 3): (lo, la) for e, lo, la, _ in v} for k, v in p.items()}
    meta = json.load(open(os.path.join(out, "meta.json")))
    L = [f"Occultation of Gaia DR3 {z['star']} by {z['target_name']} on {str(z['best_utc'])[:10]}, WGS84 height 0 "
         f"(PySyzygos {z['version']}, orbit {meta.get('orbit')}, run {meta.get('run_utc')} UTC)", "",
         "                   Centre                Star  Star  Sun|      Path Limit 1   |      Path Limit 2   |"
         "     Error Limit 1   |     Error Limit 2   |",
         "  E. Longitude    Latitude      U.T.      Alt   Az   Alt| Longitude   Latitude| Longitude   Latitude|"
         " Longitude   Latitude| Longitude   Latitude|",
         "      o  '  \"     o  '  \"    h  m  s       o     o     o|   o  '  \"    o  '  \"|   o  '  \"    o  '  \"|"
         "   o  '  \"    o  '  \"|   o  '  \"    o  '  \"|", ""]
    day0 = spice.str2et(str(z["best_utc"])[:10] + " 00:00:00 UTC")
    for et, lon, lat, _ in p["center"]:
        k = round(et, 3)
        R = spice.pxform("J2000", "ITRF93", et)
        Pg = _ecef(lon, lat)
        up = Pg / np.linalg.norm(Pg)
        east = np.cross([0.0, 0.0, 1.0], up); east /= np.linalg.norm(east)
        north = np.cross(up, east)
        s = R @ star_dir
        sun = R @ np.asarray(spice.spkpos("SUN", et, "J2000", "LT+S", "399")[0])
        sun = sun / np.linalg.norm(sun)
        alt = math.degrees(math.asin(float(s @ up)))
        az = math.degrees(math.atan2(float(s @ east), float(s @ north))) % 360.0
        sun_alt = math.degrees(math.asin(float(sun @ up)))
        part = lambda name: (" " + fmt_dms(by[name][k][0]) + " " + fmt_dms(by[name][k][1], 2)) if k in by[name] else \
            "        ....          ...."
        L.append(f"  {fmt_dms(lon)} {fmt_dms(lat, 2)}   {fmt_ut(et - day0)}   {alt:3.0f}   {az:3.0f}   {sun_alt:3.0f}"
                 + part("edge_plus") + part("edge_minus") + part("sigma1_plus") + part("sigma1_minus"))
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------- command
def main(argv=None):
    ap = argparse.ArgumentParser(prog="pysyzygos path-check", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"PySyzygos {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run").add_argument("key")
    q = sub.add_parser("export"); q.add_argument("key"); q.add_argument("--step", type=float, default=1.45)
    q = sub.add_parser("compare"); q.add_argument("key"); q.add_argument("listing")
    q.add_argument("--header", help="a text file with Occult's plot header (orbit, star RA/Dec, diameter)")
    sub.add_parser("keep").add_argument("key")
    a = ap.parse_args(argv)
    out = fav_dir(a.key)
    stamp = time.strftime("%Y%m%dT%H%M", time.gmtime())
    if a.cmd == "run":
        run(a.key)
    elif a.cmd == "export":
        text = export(out, a.step)
        path = os.path.join(out, f"pysyzygos_path_{stamp}.txt")
        open(path, "w", encoding="utf-8").write(text)
        print(f"wrote {path}")
    elif a.cmd == "compare":
        listing = open(a.listing, encoding="utf-8", errors="replace").read()
        header = open(a.header, encoding="utf-8", errors="replace").read() if a.header else ""
        md, points, stats, fit = compare(out, listing, header)
        shutil.copyfile(a.listing, os.path.join(out, f"occult_{stamp}.txt")) if os.path.abspath(a.listing) != \
            os.path.abspath(os.path.join(out, f"occult_{stamp}.txt")) else None
        mdp = os.path.join(out, f"compare_{stamp}.md")
        open(mdp, "w", encoding="utf-8").write(md)
        import csv
        with open(os.path.join(out, f"compare_{stamp}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(points[0])); w.writeheader(); w.writerows(points)
        print(md)
        print(f"wrote {mdp}")
    elif a.cmd == "keep":
        dest = os.path.join("owc_refs", "occult_paths")
        os.makedirs(dest, exist_ok=True)
        files = sorted(glob.glob(os.path.join(out, "compare_*.md")))
        if not files:
            raise SystemExit("no comparison yet: pysyzygos path-check compare <key> <listing>")
        md = files[-1]
        st = os.path.basename(md)[len("compare_"):-len(".md")]
        for f in (md, md[:-3] + ".csv", os.path.join(out, f"occult_{st}.txt")):
            if os.path.isfile(f):
                shutil.copyfile(f, os.path.join(dest, f"{a.key}_{os.path.basename(f)}"))
        line = next((l for l in open(md, encoding="utf-8") if l.startswith("**Result:**")), "").strip()
        with open(os.path.join(dest, "index.md"), "a", encoding="utf-8") as f:
            f.write(f"- {a.key} ({st}): {line[len('**Result:** '):]}\n")
        print(f"kept in {dest} (index.md)")


if __name__ == "__main__":
    main()
