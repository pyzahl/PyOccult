#!/usr/bin/env python3
"""pyoccult_pick.py - rank asteroids by how many *usable* occultation events they should give your site,
to choose the `targets` list for pyoccult. Screening only: the real prediction stays with pyoccult.py.

Pipeline
  1. names      : your jpl_asteroids_spice.csv (SPICE ID, Full Name, Primary Designation)
  2. properties : JPL SBDB bulk query (H, G, diameter, albedo, osculating elements, orbit quality), cached as JSON
  3. sky path   : two-body Kepler propagation of each asteroid over the next --days days (daily samples)
  4. yield      : for every day, expected events = star density x sky motion x corridor width, counting only stars
                  that give a detectable drop (brighter than asteroid + 1.25 mag for a 0.3 mag drop, and brighter
                  than the camera limit), only when the object is observable (Sun down and asteroid up for part of the day) and the chord lasts long enough
  5. score      : yearly yield x science weights (poor size, poor orbit, NEO). Prints a table, writes a CSV and a
                  ready-to-paste `targets = [...]` line.

The star density is an analytic Gaia-like model (average counts + galactic-latitude factor), good for ranking, not for
absolute numbers. Replace star_density() with a HEALPix lookup of Gaia counts to tighten it.

Only numpy is required (urllib for the SBDB download).
"""
import argparse, csv, datetime as dt, json, math, os, sys, urllib.parse, urllib.request
import numpy as np

SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
SBDB_FIELDS = ["spkid", "full_name", "H", "G", "diameter", "diameter_sigma", "albedo", "a", "e", "i", "om", "w",
               "ma", "epoch", "condition_code", "neo", "class"]
AU_KM = 149597870.7
OBLIQ = math.radians(23.4392911)
EQ2GAL = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],
                   [0.4941094279, -0.4448296300, 0.7469822445],
                   [-0.8676661490, -0.1980763734, 0.4559837762]])
WEIGHTS = dict(poor_size=1.5,      # no measured diameter (H-based size only)
               poor_orbit=1.3,     # condition code >= 3
               neo=1.5)

# ---------------------------------------------------------------- catalogue and SBDB
def read_names(path):
    """jpl_asteroids_spice.csv -> {number(int): (spkid, full_name)}. The first column is '...ID' (header may be cut)."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd, None)
        for row in rd:
            if len(row) < 3:
                continue
            try:
                spk = int(row[0])
            except ValueError:
                continue
            d = row[2].strip()
            num = int(d) if d.isdigit() else spk - 20000000
            out[num] = (spk, row[1].strip())
    return out


def fetch_sbdb(hmax, cache):
    """Bulk SBDB download of numbered asteroids with H < hmax. Cached; delete the cache to refresh."""
    if cache and os.path.exists(cache):
        with open(cache) as f:
            blob = json.load(f)
        if blob.get("hmax", 0) >= hmax:
            return blob["fields"], blob["data"]
    q = dict(fields=",".join(SBDB_FIELDS), **{"sb-kind": "a", "sb-ns": "n",
             "sb-cdata": json.dumps({"AND": [f"H|LT|{hmax}"]})})
    url = SBDB_URL + "?" + urllib.parse.urlencode(q)
    print(f"Downloading SBDB (H < {hmax}) ...", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=300) as r:
        blob = json.load(r)
    blob["hmax"] = hmax
    if cache:
        with open(cache, "w") as f:
            json.dump(blob, f)
    return blob["fields"], blob["data"]


def to_float(x, default=np.nan):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def build_table(fields, data):
    idx = {k: fields.index(k) for k in fields}
    rows = []
    for r in data:
        g = lambda k: r[idx[k]] if k in idx else None
        a, e = to_float(g("a")), to_float(g("e"))
        if not (a > 0 and 0 <= e < 0.99) or math.isnan(to_float(g("H"))) or math.isnan(to_float(g("epoch"))):
            continue                                   # no bound orbit or missing elements
        rows.append(dict(spkid=int(g("spkid")), name=(g("full_name") or "").strip(), H=to_float(g("H")),
                         G=to_float(g("G"), 0.15) if not math.isnan(to_float(g("G"))) else 0.15,
                         diam=to_float(g("diameter")), albedo=to_float(g("albedo")),
                         a=a, e=e, i=to_float(g("i")), om=to_float(g("om")), w=to_float(g("w")),
                         ma=to_float(g("ma")), epoch=to_float(g("epoch")),
                         cc=to_float(g("condition_code"), 9.0), neo=(g("neo") == "Y"), cls=g("class") or ""))
    return rows


# ---------------------------------------------------------------- geometry
def earth_helio_ecl(jd):
    """Heliocentric ecliptic J2000 position of the Earth (AU), low-precision (~0.01 deg), from the Sun's mean elements."""
    d = np.asarray(jd) - 2451545.0
    L = np.radians(280.460 + 0.9856474 * d)
    g = np.radians(357.528 + 0.9856003 * d)
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    lam -= np.radians(0.01397 * d / 365.25)            # of-date -> J2000 longitude
    R = 1.00014 - 0.01671 * np.cos(g) - 0.00014 * np.cos(2 * g)
    sun = np.stack([R * np.cos(lam), R * np.sin(lam), np.zeros_like(lam)], axis=-1)   # Sun as seen from Earth
    return -sun, R                                      # Earth as seen from the Sun


def kepler_helio_ecl(el, jd):
    """Two-body heliocentric ecliptic J2000 positions (AU). el: dict of arrays (N); jd: (T,). Returns (N,T,3), r (N,T)."""
    a, e = el["a"][:, None], el["e"][:, None]
    n = 0.98560767 / el["a"] ** 1.5                     # deg/day (Gaussian k)
    M = np.radians((el["ma"][:, None] + n[:, None] * (jd[None, :] - el["epoch"][:, None])) % 360.0)
    E = M + e * np.sin(M)
    for _ in range(12):                                 # Newton
        E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
    xp, yp = a * (np.cos(E) - e), a * np.sqrt(1 - e ** 2) * np.sin(E)
    i, om, w = (np.radians(el[k])[:, None] for k in ("i", "om", "w"))
    cO, sO, ci, si, cw, sw = np.cos(om), np.sin(om), np.cos(i), np.sin(i), np.cos(w), np.sin(w)
    x = (cO * cw - sO * sw * ci) * xp + (-cO * sw - sO * cw * ci) * yp
    y = (sO * cw + cO * sw * ci) * xp + (-sO * sw + cO * cw * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    pos = np.stack([x, y, z], axis=-1)
    return pos, np.linalg.norm(pos, axis=-1)


def ecl_to_eq(v):
    c, s = math.cos(OBLIQ), math.sin(OBLIQ)
    return np.stack([v[..., 0], v[..., 1] * c - v[..., 2] * s, v[..., 1] * s + v[..., 2] * c], axis=-1)


# ---------------------------------------------------------------- brightness, size, stars
def apparent_mag(H, G, r, delta, R, ):
    cosa = np.clip((r ** 2 + delta ** 2 - R ** 2) / (2 * r * delta), -1, 1)
    half = np.tan(np.arccos(cosa) / 2)
    phi1, phi2 = np.exp(-3.33 * half ** 0.63), np.exp(-1.87 * half ** 1.22)
    return H + 5 * np.log10(r * delta) - 2.5 * np.log10((1 - G) * phi1 + G * phi2)


def diameter_km(diam, albedo, H):
    """Measured diameter when SBDB has one, else H-based with albedo (measured or 0.14)."""
    p = np.where(np.isnan(albedo), 0.14, albedo)
    est = 1329.0 / np.sqrt(p) * 10 ** (-H / 5.0)
    return np.where(np.isnan(diam), est, diam), np.isnan(diam)


# average Gaia G cumulative counts per deg^2 (rounded, whole sky), interpolated in log-log
_G = np.array([8.0, 11.5, 14.0, 17.0, 18.0, 20.0])
_N = np.array([1.0, 60.0, 580.0, 9200.0, 15700.0, 34000.0])
_gb = np.radians(np.linspace(-90, 90, 3601))
_f = 0.3 + 4.0 * np.exp(-np.abs(np.degrees(_gb)) / 10.0)            # galactic-latitude shape
_NORM = np.sum(_f * np.cos(_gb)) / np.sum(np.cos(_gb))               # sky average -> 1


def star_density(b_deg, mag):
    """Approximate stars per deg^2 brighter than `mag` (Gaia G) at galactic latitude b. Arrays broadcast."""
    avg = 10 ** np.interp(np.asarray(mag, float), _G, np.log10(_N))
    f = (0.3 + 4.0 * np.exp(-np.abs(b_deg) / 10.0)) / _NORM
    return avg * f


# ---------------------------------------------------------------- yield
def dark_fraction(sun_eq, ast_eq, lat_deg, min_alt, max_sun_alt, n=24):
    """Fraction of a day (uniform in local solar time) when the Sun is below max_sun_alt and the asteroid above min_alt.
    sun_eq, ast_eq: unit vectors (..., 3) in J2000 equatorial; broadcast over leading axes."""
    phi = math.radians(lat_deg)
    ds = np.arcsin(np.clip(sun_eq[..., 2], -1, 1))
    da = np.arcsin(np.clip(ast_eq[..., 2], -1, 1))
    ra_s = np.arctan2(sun_eq[..., 1], sun_eq[..., 0])
    ra_a = np.arctan2(ast_eq[..., 1], ast_eq[..., 0])
    h = np.linspace(0, 2 * np.pi, n, endpoint=False)                     # Sun hour angle through the day
    hs = h.reshape((1,) * ds.ndim + (n,))
    sin_alt_s = np.sin(phi) * np.sin(ds)[..., None] + np.cos(phi) * np.cos(ds)[..., None] * np.cos(hs)
    ha_a = hs - (ra_a - ra_s)[..., None]                                 # asteroid hour angle = Sun's minus RA difference
    sin_alt_a = np.sin(phi) * np.sin(da)[..., None] + np.cos(phi) * np.cos(da)[..., None] * np.cos(ha_a)
    ok = (sin_alt_s < math.sin(math.radians(max_sun_alt))) & (sin_alt_a > math.sin(math.radians(min_alt)))
    return ok.mean(axis=-1)


def screen(rows, jd0, days, site, opt, chunk=1000):
    """Return per-asteroid dicts with yearly expected usable events."""
    jd = jd0 + np.arange(days + 1, dtype=float)
    earth, R = earth_helio_ecl(jd)                       # (T,3), (T,)
    lat = site["lat"]
    out = []
    for s in range(0, len(rows), chunk):
        part = rows[s:s + chunk]
        el = {k: np.array([r[k] for r in part]) for k in ("a", "e", "i", "om", "w", "ma", "epoch")}
        pos, r = kepler_helio_ecl(el, jd)                # (N,T,3)
        geo = pos - earth[None, :, :]
        delta = np.linalg.norm(geo, axis=-1)
        H = np.array([p["H"] for p in part])[:, None]
        G = np.array([p["G"] for p in part])[:, None]
        D, est = diameter_km(np.array([p["diam"] for p in part]), np.array([p["albedo"] for p in part]), H[:, 0])
        m_ast = apparent_mag(H, G, r, delta, R[None, :])
        u = geo / delta[..., None]
        ueq = ecl_to_eq(u)
        dec = np.degrees(np.arcsin(np.clip(ueq[..., 2], -1, 1)))
        b = np.degrees(np.arcsin(np.clip(ueq @ EQ2GAL[2], -1, 1)))
        # sky motion per day between consecutive samples
        mot = np.degrees(np.arccos(np.clip(np.sum(u[:, :-1] * u[:, 1:], axis=-1), -1, 1)))
        sl = slice(0, -1)
        width = np.degrees((2 * site["reach_km"] + D[:, None]) / (delta[:, sl] * AU_KM))
        v_kms = np.radians(mot) / 86400.0 * delta[:, sl] * AU_KM          # shadow speed ~ sky motion x distance
        dur = D[:, None] / np.maximum(v_kms, 1e-6)                        # central-chord duration, s
        # usable stars: drop >= min_drop needs F*/Fa >= 10^(0.4 dm)-1  ->  m* <= m_ast + dm_cut
        dm_cut = -2.5 * math.log10(10 ** (0.4 * opt["min_drop"]) - 1.0)
        m_cut = np.minimum(m_ast[:, sl] + dm_cut, opt["cam_limit"])
        dens = star_density(b[:, sl], m_cut)
        sun_eq = ecl_to_eq(-earth / np.linalg.norm(earth, axis=-1, keepdims=True))[None, :-1, :]
        dark = dark_fraction(sun_eq, ueq[:, sl], lat, site["min_alt"], opt["max_sun_alt"])
        ok = (dur >= opt["min_dur"]) * dark                                 # weight in [0, 1]
        ev = (ok * dens * mot * width).sum(axis=1) * 365.25 / days
        for k, p in enumerate(part):
            out.append(dict(p, D=float(D[k]), D_est=bool(est[k]), events_yr=float(ev[k]),
                            m_ast_min=float(m_ast[k].min()), obs_days=float(ok[k].sum()),
                            speed_deg_day=float(mot[k].mean())))
    return out


def score(c):
    w = 1.0
    if c["D_est"]:
        w *= WEIGHTS["poor_size"]
    if c["cc"] >= 3:
        w *= WEIGHTS["poor_orbit"]
    if c["neo"]:
        w *= WEIGHTS["neo"]
    return c["events_yr"] * w


# ---------------------------------------------------------------- main
def write_targets(path, top, a):
    """Write an importable module:  from targets import targets, target_names"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# generated by pyoccult_pick.py on {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC\n")
        f.write(f"# site lat {a.lat}, window {a.days} d from {a.start or 'today'}, min drop {a.min_drop}, "
                f"camera limit G {a.cam_limit}, min duration {a.min_dur} s\n")
        f.write("# rank order: best first.  ev/yr = estimated usable events per year (relative, not absolute)\n\n")
        f.write("targets = [\n")
        for c in top:
            f.write(f"    {str(c['number'])!r},   # {c['name']:<28} H {c['H']:4.1f}  D {c['D']:6.1f} km"
                    f"{'~' if c['D_est'] else ' '}  ev/yr {c['events_yr']:6.2f}\n")
        f.write("]\n\n")
        f.write("target_names = {\n")
        for c in top:
            f.write(f"    {str(c['number'])!r}: {c['name']!r},\n")
        f.write("}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default="jpl_asteroids_spice.csv")
    ap.add_argument("--sbdb-cache", default="sbdb_cache.json")
    ap.add_argument("--hmax", type=float, default=14.0, help="download/consider asteroids with H below this")
    ap.add_argument("--start", help="UTC date YYYY-MM-DD (default: today)")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--lat", type=float); ap.add_argument("--reach", type=float, help="max_shadow_dist km (default from config)")
    ap.add_argument("--min-alt", type=float, help="MIN_STAR_ALT (default from config)")
    ap.add_argument("--min-drop", type=float, default=0.3, help="smallest useful magnitude drop")
    ap.add_argument("--cam-limit", type=float, default=16.0, help="faintest star your camera records, G mag")
    ap.add_argument("--min-dur", type=float, default=0.5, help="shortest central-chord duration worth targeting, s")
    ap.add_argument("--max-sun-alt", type=float, help="Sun must be below this, deg (default: config MAX_SUN_ALT or -6)")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("-o", "--output", default="pick_candidates.csv")
    ap.add_argument("--targets-file", default="targets.py", help="importable Python file with the top --top targets ('' to skip)")
    a = ap.parse_args(argv)

    cfg = {}
    try:
        sys.path.insert(0, os.getcwd())
        import pyoccult_config as C
        cfg = dict(lat=C.LAT, reach=C.max_shadow_dist, min_alt=C.MIN_STAR_ALT, sun=C.MAX_SUN_ALT)
    except Exception:
        pass
    site = dict(lat=a.lat if a.lat is not None else cfg.get("lat"),
                reach_km=a.reach if a.reach is not None else cfg.get("reach", 200.0),
                min_alt=a.min_alt if a.min_alt is not None else cfg.get("min_alt", 10.0))
    if site["lat"] is None:
        ap.error("need --lat (no pyoccult_config.py found)")

    names = read_names(a.catalog) if os.path.exists(a.catalog) else {}
    fields, data = fetch_sbdb(a.hmax, a.sbdb_cache)
    rows = [r for r in build_table(fields, data) if r["H"] < a.hmax]
    d0 = dt.datetime.strptime(a.start, "%Y-%m-%d") if a.start else dt.datetime.utcnow()
    jd0 = (d0 - dt.datetime(2000, 1, 1, 12)).total_seconds() / 86400.0 + 2451545.0
    print(f"{len(rows)} asteroids, {a.days} days from JD {jd0:.1f}; site lat {site['lat']:.2f}, reach {site['reach_km']:.0f} km",
          file=sys.stderr)

    opt = dict(min_drop=a.min_drop, cam_limit=a.cam_limit, min_dur=a.min_dur,
               max_sun_alt=a.max_sun_alt if a.max_sun_alt is not None else cfg.get("sun", -6.0))
    cand = screen(rows, jd0, a.days, site, opt)
    for c in cand:
        c["number"] = c["spkid"] - 20000000 if c["spkid"] >= 20000000 else c["spkid"] - 2000000
        c["in_catalog"] = c["number"] in names
        c["score"] = score(c)
    cand.sort(key=lambda c: -c["score"])

    cols = ["number", "name", "H", "D", "D_est", "cc", "neo", "cls", "m_ast_min", "obs_days", "speed_deg_day",
            "events_yr", "score", "in_catalog"]
    with open(a.output, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for c in cand:
            w.writerow([f"{c[k]:.4g}" if isinstance(c[k], float) else c[k] for k in cols])
    print(f"{'#':>7} {'name':<26} {'H':>5} {'D km':>7} {'cc':>3} {'mmin':>5} {'ev/yr':>6} {'score':>6}")
    for c in cand[:a.top]:
        print(f"{c['number']:>7} {c['name'][:26]:<26} {c['H']:5.1f} {c['D']:6.1f}{'~' if c['D_est'] else ' '} "
              f"{c['cc']:3.0f} {c['m_ast_min']:5.1f} {c['events_yr']:6.2f} {c['score']:6.2f}")
    if a.targets_file:
        write_targets(a.targets_file, cand[:a.top], a)
    print("\ntargets = [" + ", ".join(f"'{c['number']}'" for c in cand[:a.top]) + "]")
    print(f"\nfull table: {a.output}   (~ = diameter estimated from H)")
    if a.targets_file:
        print(f"importable list: {a.targets_file}   ->   from targets import targets")


if __name__ == "__main__":
    main()
