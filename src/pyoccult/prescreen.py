"""prescreen.py - a pre-screened target list for the pick: every asteroid that has at least one possible occultation in a
region (or anywhere on the Earth) during a window, built once (e.g. per month) and used by any pick of a site in that
region: `pyoccult pick --prescreen FILE` screens only those asteroids instead of all, otherwise unchanged.

    pyoccult prescreen build --start 2026-11-01 --days 30 --region 35,60,-130,-60    # lat min,max, lon min,max (deg)
    pyoccult prescreen build --start 2026-11-01 --days 30 --around-site 500          # a box 500 km around the site
    pyoccult prescreen build --start 2026-11-01 --days 30 --around-sites 300         # one box around all your sites
    pyoccult prescreen build --start 2026-11-01 --days 30 --global
    pyoccult prescreen list                                                          # the built ones
    pyoccult prescreen show prescreen/<name>.db

Memory and progress: the asteroids go to the worker processes in chunks sized from the free memory (a chunk's numpy
arrays take ~12 x 3 x 8 bytes per asteroid and 10-min time step: 0.29 MB for 7 days, 1.2 MB for 30 days); --max-mem
GB or --mem-frac set the budget, --chunk a fixed size. Fewer workers are used if the budget is too small for them;
chunks shrink when the free memory runs low. After every chunk the events so far are saved in <output>.partial; after
a crash or Ctrl-C the same command resumes there (--fresh starts over).

How (the pick's own parts: SBDB elements, orbits integrated with the planets, the bright-star index, the candidate
scan), but for the whole Earth instead of one site:
  1. per asteroid, the stars (G <= cam_limit, and bright enough for a drop >= min_drop) within Earth radius + its
     radius + reach of its geocentric path: every star whose shadow can touch the Earth;
  2. per candidate, the ground track of the shadow axis (sampled, the Earth's rotation from SPICE every 10 min and
     the spin in between); kept if any sample lies in the region (+ shadow radius + reach) with the star above
     min_alt and the Sun below max_sun_alt there (a region build) - a global build keeps all candidates;
  3. stored in SQLite: the events (asteroid, star, time, geocentric miss, a ground point) and the build settings.
Region: a latitude/longitude box, not a circle. --around-site KM: +-KM/111.2 deg of latitude, +-KM/(111.2 cos(site
lat)) deg of longitude (exactly KM along the site's meridian and parallel; the poleward edge is a little narrower in km,
the equatorward edge wider). --around-sites KM: the box of all sites plus KM, longitude width taken at the poleward
edge (at least KM everywhere), the short way round across the date line. A candidate is kept if its ground track
touches the box widened by its radius + reach (per latitude), so the effective region is the box + 200 km or more.
All limits are loose on purpose (a superset): the pick then applies its exact site screen, so with a pre-screen built
with limits at least as loose as the pick's, it finds the same events, only faster. The orbits are those of the build
date: rebuild after a month or so (orbit updates of poorly known asteroids), as the search uses the current JPL
Horizons orbit for the final prediction anyway.
"""
from pyoccult.version import __version__
import argparse, glob, json, math, os, sqlite3, sys, tempfile, time
import numpy as np

DIR = "prescreen"
OMEGA = 7.2921150e-5                         # Earth's rotation, rad/s (sidereal)


# ---------------------------------------------------------------- region
def region_box(lat_min, lat_max, lon_min, lon_max):
    if not (-90 <= lat_min < lat_max <= 90):
        raise ValueError("region: need lat_min < lat_max within -90..90")
    return dict(lat_min=float(lat_min), lat_max=float(lat_max), lon_min=float(lon_min), lon_max=float(lon_max))


def box_around(lat, lon, km):
    """A lat/lon box reaching km from (lat, lon) in every direction."""
    dlat = km / 111.2
    dlon = min(km / (111.2 * max(math.cos(math.radians(lat)), 0.02)), 180.0)
    return region_box(max(lat - dlat, -90.0), min(lat + dlat, 90.0), lon - dlon, lon + dlon)


def box_around_all(points, km):
    """A lat/lon box reaching km from every (lat, lon) point (e.g. all sites of sites.py): one pre-screen for them all.
    Longitudes: the shortest arc holding all points (across the date line if that is shorter)."""
    pts = [(float(a), float(b)) for a, b in points]
    if not pts:
        raise ValueError("no points")
    lons = sorted(((b + 180.0) % 360.0) - 180.0 for _, b in pts)
    gaps = [(lons[(i + 1) % len(lons)] - lons[i]) % 360.0 or (360.0 if len(lons) == 1 else 0.0) for i in range(len(lons))]
    i = max(range(len(lons)), key=lambda k: gaps[k])                # the widest gap is outside the box
    west, east = lons[(i + 1) % len(lons)], lons[i]
    lat_lo, lat_hi = min(a for a, _ in pts), max(a for a, _ in pts)
    dlat = km / 111.2
    edge = min(max(abs(lat_lo - dlat), abs(lat_hi + dlat)), 89.9)    # the narrowest degree of longitude in the box
    cos_min = max(math.cos(math.radians(edge)), 0.02)
    dlon = km / (111.2 * cos_min)
    w, e = west - dlon, east + dlon
    if (e - w) % 360.0 >= 360.0 - 1e-9 or (east - west) % 360.0 + 2 * dlon >= 360.0:
        w, e = -180.0, 180.0
    else:
        w, e = ((w + 180.0) % 360.0) - 180.0, ((e + 180.0) % 360.0) - 180.0
    return region_box(max(lat_lo - dlat, -90.0), min(lat_hi + dlat, 90.0), w, e)


def in_box(lat, lon, box, margin_km):
    """Boolean array: (lat, lon) within the box widened by margin_km (longitudes wrap)."""
    dlat = margin_km / 111.2
    ok = (lat >= box["lat_min"] - dlat) & (lat <= box["lat_max"] + dlat)
    dlon = margin_km / (111.2 * np.maximum(np.cos(np.radians(lat)), 0.02))
    width = (box["lon_max"] - box["lon_min"]) % 360.0 or (360.0 if box["lon_max"] != box["lon_min"] else 0.0)
    rel = (lon - box["lon_min"]) % 360.0                         # 0..360 east of the box's west edge
    return ok & ((rel <= width + dlon) | (rel >= 360.0 - dlon))


def contains(meta, lat, lon):
    """Is the site inside the pre-screen's region (or is it global)?"""
    box = meta.get("region")
    if not box:
        return True
    return bool(in_box(np.array([lat]), np.array([lon]), box, 0.0)[0])


# ---------------------------------------------------------------- the build (worker processes, own SPICE each)
_W = {}


def _init(folder, catalog_dir, cam_limit):
    import spiceypy as spice
    from pyoccult import screen as SC, gaia_local as L
    os.chdir(folder)
    SC.load_kernels(spice, folder)
    _W.update(spice=spice, index=L.BrightIndex(catalog_dir, L.index_gmax(cam_limit)))


def build_chunk(spice, rows, et0, et1, index, opt, step_s=600.0, n_track=41):
    """The pre-screen events of these asteroids (pick.build_rows dicts). opt: cam_limit, min_drop, reach_km,
    max_sun_alt, min_alt, region (box dict or None = global)."""
    import pandas as pd
    from pyoccult import orbits as O, screen as SC
    from pyoccult.corridor import find_candidates, propagate_linear, pad_for_pm, _unit, EARTH_R_KM, GAIA_EPOCH_YEAR
    ets = np.arange(et0, et1 + step_s, step_s)
    sun = np.asarray(spice.spkpos("10", ets, "J2000", "LT+S", "399")[0])
    sun_u = sun / np.linalg.norm(sun, axis=1, keepdims=True)
    sun_bary = np.asarray(spice.spkpos("10", ets, "J2000", "NONE", "0")[0]) / O.AU_KM
    rot = np.array([spice.pxform("J2000", "ITRF93", float(t)) for t in ets])        # (T,3,3)
    pad = pad_for_pm(1500.0, ets)
    years = 2000.0 + ets.mean() / (365.25 * 86400.0) - GAIA_EPOCH_YEAR
    dm_drop = SC.drop_cut(opt["min_drop"]) if opt["min_drop"] > 0 else 99.0
    box = opt.get("region")
    sin_alt, sin_sun = math.sin(math.radians(opt["min_alt"])), math.sin(math.radians(opt["max_sun_alt"]))
    el = {k: np.array([r[k] for r in rows], float) for k in ("a", "e", "i", "om", "w", "ma", "epoch")}
    r_b, v_b = O.propagate(spice, el, ets)
    g = O.astrometric(spice, r_b, v_b, ets)                                           # (n,T,3) km
    delta = np.linalg.norm(g, axis=2)
    U = g / delta[..., None]
    helio = r_b - sun_bary[None]
    rh = np.linalg.norm(helio, axis=2)
    cos_ph = np.sum(helio * g, 2) / (rh * delta)
    speed = np.zeros_like(delta)
    speed[:, 1:] = np.linalg.norm(np.diff(U, axis=1), axis=2) / step_s * delta[:, 1:]
    speed[:, 0] = speed[:, 1]
    out = []
    for k, row in enumerate(rows):
        m_ast = SC.hg_mag(row["H"], row["G"], rh[k], delta[k] / O.AU_KM, cos_ph[k])
        cap = min(opt["cam_limit"], float(m_ast.max()) + dm_drop)
        r_max = row["D_max_km"] / 2
        margin = EARTH_R_KM + r_max + opt["reach_km"]
        w = np.degrees(margin / delta[k]) + pad / 3600.0
        stars = index.near_path(U[k], w, cap)
        if len(stars) == 0:
            continue
        sdf = pd.DataFrame({c: stars[c].astype(float) for c in ("ra", "dec", "pmra", "pmdec", "phot_g_mean_mag")})
        sdf["source_id"] = stars["source_id"]
        cands = find_candidates(sdf, dict(ets=ets, u=U[k], delta_km=delta[k], step_s=step_s), margin,
                                block_cells=SCAN_CELLS)
        if len(cands) == 0:
            continue
        ra, de = propagate_linear(sdf.iloc[cands.star.to_numpy()], years)
        sdir = _unit(ra, de)                                                         # (c,3)
        tc = cands.et_guess.to_numpy()
        keep, where = np.ones(len(cands), bool), np.full((len(cands), 4), np.nan)    # lat, lon, sun alt, star alt
        if box is not None:
            v = np.maximum(speed[k][cands.j.to_numpy()], 0.3)
            for b0 in range(0, len(tc), CAND_BLOCK):                                 # bounded memory per block
                sl = slice(b0, b0 + CAND_BLOCK)
                keep[sl], where[sl] = _ground_track(g[k], ets, tc[sl], v[sl], sdir[sl], rot, sun_u, margin, r_max,
                                                    box, opt["reach_km"], sin_alt, sin_sun, step_s, n_track)
        js = cands.j.to_numpy()
        for q in np.where(keep)[0]:
            out.append((int(row["number"]), int(sdf.source_id.iloc[cands.star.iloc[q]]), float(tc[q]),
                        float(sdf.phot_g_mean_mag.iloc[cands.star.iloc[q]]), float(m_ast[js[q]]),
                        float(cands.d_km.iloc[q]), *[None if not np.isfinite(x) else float(x) for x in where[q]]))
    return out


def _ground_track(gk, ets, tc, v, sdir, rot, sun_u, margin, r_max, box, reach_km, sin_alt, sin_sun, step_s, n_track):
    """keep (c,) and where (c,4: lat, lon, sun alt, star alt) for candidates at times tc: the ground track of the
    shadow axis, +-(Earth radius + margin) of along-track motion around closest approach."""
    from pyoccult import screen as SC
    from pyoccult.corridor import EARTH_R_KM
    half = np.minimum(1.3 * margin / v, 6 * 3600.0)
    tau = tc[:, None] + half[:, None] * np.linspace(-1, 1, n_track)[None, :]       # (c,s)
    tau = np.clip(tau, ets[0], ets[-1])
    gs = SC._interp(gk, ets, tau.ravel()).reshape(len(tc), n_track, 3)
    ex, ny = SC._plane(sdir)
    px, py = np.einsum("csx,cx->cs", gs, ex), np.einsum("csx,cx->cs", gs, ny)
    rho = np.hypot(px, py)
    R = EARTH_R_KM
    on = rho < R + r_max + reach_km
    depth = np.sqrt(np.maximum(R * R - rho * rho, 0.0))                           # towards the star (day side of it)
    scale = np.where(rho > R, R / np.maximum(rho, 1e-9), 1.0)                     # off the limb: the nearest limb point
    s = (px * scale)[..., None] * ex[:, None, :] + (py * scale)[..., None] * ny[:, None, :] \
        + depth[..., None] * sdir[:, None, :]                                      # (c,s,3) J2000, km
    up = s / np.linalg.norm(s, axis=2, keepdims=True)
    star_up = np.einsum("csx,cx->cs", up, sdir)
    i = np.clip(np.round((tau - ets[0]) / step_s).astype(int), 0, len(ets) - 1)
    sun_up = np.einsum("csx,csx->cs", up, sun_u[i])
    ang = OMEGA * (tau - ets[i])                                                  # spin since the grid time
    itrf = np.einsum("csij,csj->csi", rot[i], s)
    ca, sa = np.cos(ang), np.sin(ang)
    x, y = ca * itrf[..., 0] + sa * itrf[..., 1], -sa * itrf[..., 0] + ca * itrf[..., 1]
    lat = np.degrees(np.arcsin(np.clip(itrf[..., 2] / R, -1, 1)))
    lon = np.degrees(np.arctan2(y, x))
    ok = on & (star_up > sin_alt) & (sun_up < sin_sun) & in_box(lat, lon, box, r_max + reach_km)
    first = np.argmax(ok, axis=1)
    c_ = np.arange(len(tc))
    where = np.stack([lat[c_, first], lon[c_, first], np.degrees(np.arcsin(np.clip(sun_up[c_, first], -1, 1))),
                      np.degrees(np.arcsin(np.clip(star_up[c_, first], -1, 1)))], 1)
    return ok.any(axis=1), where


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS events (number INTEGER, star INTEGER, et REAL, g REAL, m_ast REAL, geo_miss_km REAL,
    lat REAL, lon REAL, sun_alt REAL, star_alt REAL);
CREATE INDEX IF NOT EXISTS events_number ON events (number);
CREATE INDEX IF NOT EXISTS events_et ON events (et);
"""


# ---------------------------------------------------------------- memory: the chunk plan
CAND_BLOCK = 4096                 # candidates per ground-track block (bounds the per-asteroid transient, ~50 MB)
SCAN_CELLS = 4e6                  # stars x time steps per candidate-scan block (~30 B each: ~120 MB; corridor's 2.5e7: 730 MB)
BYTES_PER_STEP = 12 * 3 * 8       # per asteroid and time step: the (n,T,3) float64 arrays of a chunk (measured ~10)
CHUNK_FIXED = 120e6               # per chunk on top: one scan block, star lists, one ground-track block (measured ~60 MB)
WORKER_BASE = 600e6               # a worker before its first chunk: Python, numpy/pandas, SPICE kernels, index offsets
MIN_CHUNK, MAX_CHUNK = 100, 2000  # MAX_CHUNK also sets how often progress is saved


def _meminfo():
    """{name: bytes} of /proc/meminfo (Linux), else {}."""
    try:
        with open("/proc/meminfo") as f:
            return {k: int(v.split()[0]) * 1024 for k, v in (ln.split(":", 1) for ln in f) if v.split()}
    except (OSError, ValueError):
        return {}


def mem_status():
    """(available, total, swap used) in bytes; None where the system does not tell (non-Linux: available = half of
    the physical memory)."""
    m = _meminfo()
    if m:
        return m.get("MemAvailable"), m.get("MemTotal"), m.get("SwapTotal", 0) - m.get("SwapFree", 0)
    total = None
    try:
        total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        pass
    if total is None and sys.platform == "win32":
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                       [(n, ctypes.c_ulonglong) for n in ("tot", "avail", "tpf", "apf", "tv", "av", "aev")]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            return ms.avail, ms.tot, None
    return (total // 2 if total else None), total, None


def peak_rss():
    """Peak resident memory of this process (bytes), None if unknown."""
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r if sys.platform == "darwin" else r * 1024
    except (ImportError, OSError):
        return None


def rss_anon():
    """Resident memory of this process that is not file-backed (bytes; Linux), None if unknown: the worker's own
    arrays, without the pages of the memory-mapped star index (counted in peak_rss, but the system can drop them)."""
    try:
        with open("/proc/self/status") as f:
            for ln in f:
                if ln.startswith("RssAnon:"):
                    return int(ln.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return None


def chunk_bytes(n, steps):
    """Estimated peak of one chunk of n asteroids over this many time steps (numpy arrays of build_chunk)."""
    return n * steps * BYTES_PER_STEP + CHUNK_FIXED


def plan_chunks(n_rows, steps, workers, budget):
    """(workers, chunk): the largest chunk (<= MAX_CHUNK) that keeps workers x (base + chunk) within budget bytes;
    fewer workers if even MIN_CHUNK does not fit; at least ~4 chunks per worker for an even load."""
    per_ast = steps * BYTES_PER_STEP
    w = max(1, workers)
    while True:
        chunk = int((budget / w - WORKER_BASE - CHUNK_FIXED) // per_ast)
        if chunk >= MIN_CHUNK or w == 1:
            break
        w -= 1
    chunk = max(MIN_CHUNK, min(chunk, MAX_CHUNK, -(-n_rows // (4 * w)) if n_rows else MAX_CHUNK))
    return w, chunk


def _gb(x):
    return "?" if x is None else f"{x / 1e9:.1f} GB"


def _hms(s):
    s = int(max(s, 0))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def _chunk_job(args):
    rows, et0, et1, opt = args
    t = time.time()
    ev = build_chunk(_W["spice"], rows, et0, et1, _W["index"], opt)
    return ev, [int(r["number"]) for r in rows], peak_rss(), rss_anon(), time.time() - t


# ---------------------------------------------------------------- the build driver (checkpointed)
def _settings(start, days, region, cam_limit, hmax, min_drop, reach_km, max_sun_alt, min_alt, catalog):
    return dict(start=start, days=days, region=region, cam_limit=cam_limit, hmax=hmax, min_drop=min_drop,
                reach_km=reach_km, max_sun_alt=max_sun_alt, min_alt=min_alt, catalog=os.path.basename(str(catalog)))


def open_partial(path, settings, fresh=False):
    """The progress file of a build (SQLite: events so far, done asteroid numbers, the settings). An existing one
    with the same settings is resumed; with other settings it is refused unless fresh (then it starts over)."""
    if fresh and os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA + "CREATE TABLE IF NOT EXISTS done (number INTEGER PRIMARY KEY);")
    row = con.execute("SELECT value FROM meta WHERE key = 'settings'").fetchone()
    if row is None:
        con.execute("INSERT INTO meta VALUES ('settings', ?)", (json.dumps(settings),))
        con.commit()
    elif json.loads(row[0]) != json.loads(json.dumps(settings)):
        con.close()
        raise RuntimeError(f"{path} is a partial build with other settings ({row[0]}); "
                           f"use --fresh to discard it, or rerun with those settings to resume it")
    return con


def build(start, days, region, cam_limit=16.0, hmax=17.0, min_drop=0.1, reach_km=200.0, max_sun_alt=0.0,
          min_alt=0.0, workers=4, out=None, catalog=None, sbdb_cache=None, name=None, chunk=None, mp_start="spawn",
          max_mem=None, mem_frac=0.6, fresh=False):
    """Build a pre-screen and write it to out (SQLite). Progress is saved after every chunk in out + '.partial'; a
    rerun with the same settings resumes there. Chunk size and workers follow the free memory (max_mem bytes or
    mem_frac of the available memory) unless chunk is given. Returns (path, n_events, n_asteroids)."""
    import gc, multiprocessing
    from concurrent.futures import ProcessPoolExecutor, FIRST_COMPLETED, wait
    import spiceypy as spice
    from pyoccult.home import HOME
    from pyoccult import pick as P, screen as SC, gaia_local as L
    say = lambda *a: print(*a, file=sys.stderr, flush=True)
    fields, data, fetched = P.fetch_sbdb(hmax, sbdb_cache or os.path.join(tempfile.gettempdir(), "PyOccult_sbdb_cache.json"))
    rows = P.build_rows(fields, data, hmax)
    del fields, data
    gc.collect()
    SC.load_kernels(spice, HOME)
    et0 = spice.str2et(f"{start}T00:00:00")
    et1 = et0 + days * 86400.0
    opt = dict(cam_limit=cam_limit, min_drop=min_drop, reach_km=reach_km, max_sun_alt=max_sun_alt, min_alt=min_alt,
               region=region)
    L.BrightIndex(catalog, L.index_gmax(cam_limit))                 # build a missing index here, once
    name = name or ("global" if region is None else "region")
    out = out or os.path.join(DIR, f"{name}__{start}_{days:g}d_G{cam_limit:g}.db")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    partial = out + ".partial"
    settings = _settings(start, days, region, cam_limit, hmax, min_drop, reach_km, max_sun_alt, min_alt, catalog)
    con = open_partial(partial, settings, fresh)
    done_nums = {r[0] for r in con.execute("SELECT number FROM done")}
    n_events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    todo = [r for r in rows if int(r["number"]) not in done_nums]
    say(f"pre-screen {name}: {len(rows)} asteroids, {start} + {days:g} d, G <= {cam_limit:g}, reach {reach_km:g} km, "
        f"region {region or 'global'}")
    if done_nums:
        say(f"  resuming {partial}: {len(done_nums)} asteroids done, {n_events} events so far, {len(todo)} to go")

    # the chunk plan from the memory model and the free memory
    steps = int(round((et1 - et0) / 600.0)) + 1
    avail, total, swap = mem_status()
    budget = max_mem if max_mem else (avail * mem_frac if avail else 4e9)
    if chunk:
        w = workers
    else:
        w, chunk = plan_chunks(len(todo), steps, workers, budget)
    say(f"  memory: available {_gb(avail)} of {_gb(total)}, swap used {_gb(swap)}, this process {_gb(peak_rss())}; "
        f"budget {_gb(budget)} ({'--max-mem' if max_mem else f'{mem_frac:.0%} of available'})")
    say(f"  numpy per asteroid: {steps} time steps x {BYTES_PER_STEP} B = {steps * BYTES_PER_STEP / 1e6:.2f} MB; "
        f"chunk {chunk} -> ~{_gb(chunk_bytes(chunk, steps))} + worker base ~{_gb(WORKER_BASE)}")
    say(f"  plan: {w} worker(s){f' (of {workers} asked, memory)' if w < workers else ''} x chunk {chunk} "
        f"= ~{_gb(w * (WORKER_BASE + chunk_bytes(chunk, steps)))} peak, "
        f"{-(-len(todo) // chunk) if todo else 0} chunks, progress saved after each")

    import signal

    def _term(*_):
        raise KeyboardInterrupt("terminated")
    try:
        signal.signal(signal.SIGTERM, _term)                     # GUI Stop: save and stop like Ctrl-C
    except ValueError:                                           # not the main thread
        pass
    t0, n_done = time.time(), 0
    pos, pending, wpeak, wbase = 0, {}, 0, 0
    P.single_thread_workers()
    ex = ProcessPoolExecutor(max_workers=w, mp_context=multiprocessing.get_context(mp_start),
                             initializer=_init, initargs=(HOME, catalog, cam_limit))
    try:
        while pos < len(todo) or pending:
            # keep w + 1 chunks in flight; smaller chunks, or a pause, when the free memory runs low
            while pos < len(todo) and len(pending) < w + 1:
                a_now = mem_status()[0]
                if a_now is not None and a_now < 2 * chunk_bytes(chunk, steps) and chunk > MIN_CHUNK:
                    chunk = max(MIN_CHUNK, chunk // 2)
                    say(f"  low memory ({_gb(a_now)} available): chunk now {chunk}")
                if a_now is not None and a_now < chunk_bytes(chunk, steps) and pending:
                    break                                                     # wait for a running chunk first
                job = todo[pos:pos + chunk]
                pending[ex.submit(_chunk_job, (job, et0, et1, opt))] = len(job)
                pos += len(job)
            fin, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            for f in fin:
                pending.pop(f)
                ev, nums, wp, wa, dt = f.result()
                with con:
                    con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)", ev)
                    con.executemany("INSERT OR IGNORE INTO done VALUES (?)", [(x,) for x in nums])
                n_done += len(nums)
                n_events += len(ev)
                wpeak, wbase = max(wpeak, wp or 0), max(wbase, wa or 0)
                el = time.time() - t0
                rate = n_done / el
                a_now, _, sw = mem_status()
                say(f"  {len(done_nums) + n_done}/{len(rows)} asteroids ({(len(done_nums) + n_done) / len(rows):.1%}), "
                    f"{n_events} events | chunk {len(nums)} in {dt:.0f} s, {rate:.0f} ast/s, elapsed {_hms(el)}, "
                    f"ETA {_hms((len(todo) - n_done) / rate)} | mem available {_gb(a_now)}, swap used {_gb(sw)}, "
                    f"worker peak RSS {_gb(wpeak)} (incl. mapped index pages), own after chunk {_gb(wbase or None)}; "
                    f"est chunk ~{_gb(chunk_bytes(len(nums), steps))}")
    except BaseException as e:
        try:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)          # a second Stop must not break the cleanup
        except ValueError:
            pass
        procs = list((getattr(ex, "_processes", None) or {}).values())
        ex.shutdown(wait=False, cancel_futures=True)
        for p in procs:                                            # running chunks are lost anyway: end them now,
            if p.is_alive():                                       # not after minutes (and never leave orphans that
                p.terminate()                                      # hold the GUI's output pipe open)
        for p in procs:
            p.join(5)
        con.close()
        say(f"pre-screen stopped ({type(e).__name__}: {e}); {len(done_nums) + n_done} of {len(rows)} asteroids saved in "
            f"{partial} - rerun the same command to resume")
        raise
    ex.shutdown()
    meta = dict(name=name, start=start, days=days, et0=et0, et1=et1, region=region, cam_limit=cam_limit,
                hmax=hmax, min_drop=min_drop, reach_km=reach_km, max_sun_alt=max_sun_alt, min_alt=min_alt,
                asteroids_screened=len(rows), sbdb_fetched=fetched, built=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                build_s=round(time.time() - t0), catalog=os.path.basename(str(catalog)), version=__version__,
                resumed=bool(done_nums))
    with con:
        con.execute("DELETE FROM meta")
        con.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in meta.items()])
        con.execute("DROP TABLE done")
    con.execute("VACUUM")
    n_ev, n_ast = con.execute("SELECT COUNT(*), COUNT(DISTINCT number) FROM events").fetchone()
    con.close()
    os.replace(partial, out)
    say(f"pre-screen written: {out}: {n_ev} events of {n_ast} asteroids (of {len(rows)}), {_hms(time.time() - t0)}")
    return out, n_ev, n_ast


# ---------------------------------------------------------------- use
def read_meta(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {k: json.loads(v) for k, v in con.execute("SELECT key, value FROM meta")}
    finally:
        con.close()


def numbers(path, et0, et1):
    """The asteroid numbers with pre-screen events between et0 and et1."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {int(r[0]) for r in con.execute("SELECT DISTINCT number FROM events WHERE et BETWEEN ? AND ?",
                                               (et0 - 3600.0, et1 + 3600.0))}
    finally:
        con.close()


def check(meta, et0, et1, lat, lon, opt):
    """Problems (list of str) using this pre-screen for a pick: window, region, and limits tighter than the pick's
    (then the pick could miss events the full screen finds)."""
    out = []
    if et0 < meta["et0"] - 1 or et1 > meta["et1"] + 1:
        out.append(f"window not covered (pre-screen {meta['start']} + {meta['days']:g} d)")
    if not contains(meta, lat, lon):
        out.append("site outside the pre-screen's region")
    for k, label, worse in (("cam_limit", "star limit", lambda p, b: p > b + 1e-9),
                            ("reach_km", "reach", lambda p, b: p > b + 1e-9),
                            ("min_drop", "minimum drop", lambda p, b: p < b - 1e-9),
                            ("max_sun_alt", "Sun limit", lambda p, b: p > b + 1e-9),
                            ("min_alt", "minimum altitude", lambda p, b: p < b - 1e-9)):
        if k in opt and worse(opt[k], meta[k]):
            out.append(f"{label} {opt[k]:g} beyond the pre-screen's {meta[k]:g}")
    if opt.get("hmax_all") or (meta.get("hmax") is not None and opt.get("hmax") is not None and opt["hmax"] > meta["hmax"]):
        out.append(f"H limit beyond the pre-screen's ({meta.get('hmax')})")
    return out


def age_days(meta):
    """Days since the build (orbits of that day: rebuild after a few weeks)."""
    try:
        import calendar
        return (time.time() - calendar.timegm(time.strptime(meta["built"][:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
    except (KeyError, ValueError, TypeError):
        return None


def counts(path):
    """(events, asteroids) of a pre-screen file."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*), COUNT(DISTINCT number) FROM events").fetchone()
    finally:
        con.close()


def best_fit(et0, et1, lat, lon, opt, folder=DIR):
    """The pre-screen to use for a pick: (path, meta) of the newest build that fits (check() empty), or (None, None);
    plus [(path, meta, problems)] of the others, for the message."""
    fits, other = [], []
    for p, m in list_files(folder):
        bad = check(m, et0, et1, lat, lon, opt)
        (other.append((p, m, bad)) if bad else fits.append((p, m)))
    if not fits:
        return None, None, other
    p, m = max(fits, key=lambda x: (x[1].get("built", ""), -x[1]["days"]))
    return p, m, other


def list_files(folder=DIR):
    out = []
    for p in sorted(glob.glob(os.path.join(folder, "*.db"))):
        try:
            out.append((p, read_meta(p)))
        except sqlite3.Error:
            continue
    return out


def describe(path, meta=None):
    m = meta or read_meta(path)
    reg = m.get("region")
    where = "global" if not reg else (f"lat {reg['lat_min']:.1f}..{reg['lat_max']:.1f}, "
                                      f"lon {reg['lon_min']:.1f}..{reg['lon_max']:.1f}")
    return (f"{m.get('name', '?')}: {m['start']} + {m['days']:g} d, {where}, G <= {m['cam_limit']:g}, "
            f"reach {m['reach_km']:g} km, H < {m.get('hmax')}, built {m.get('built', '?')[:16]}")


def main(argv=None):
    cfg = {}
    try:
        from pyoccult import config as C
        g = lambda k, d: getattr(C, k, d)
        cfg = dict(sites=[(v["lat"], v["lon"]) for v in getattr(C, "sites", {}).values() if "lat" in v],
                   lat=C.LAT, lon=C.LON, site=g("site_name", None), catalog=g("gaia_local_dir", "gaia_dr3_g16"),
                   cache=C.cache_path, hmax=g("pick_hmax", 17.0), cam_limit=g("pick_cam_limit", 16.0))
    except (ImportError, AttributeError):
        pass
    c = lambda k, d=None: cfg.get(k, d)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"PyOccult {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build a pre-screen")
    b.add_argument("--start", required=True, help="UTC date YYYY-MM-DD")
    b.add_argument("--days", type=float, default=30.0)
    where = b.add_mutually_exclusive_group(required=True)
    where.add_argument("--region", help="lat_min,lat_max,lon_min,lon_max in degrees (lon east-positive)")
    where.add_argument("--around-site", type=float, metavar="KM", help="a box this far around the configured site")
    where.add_argument("--around-sites", type=float, metavar="KM",
                       help="one box this far around all sites of sites.py (one pre-screen for all of them)")
    where.add_argument("--global", dest="glob", action="store_true", help="the whole Earth (no region test)")
    b.add_argument("--name", help="name of the pre-screen (default: region / site name / global)")
    b.add_argument("--cam-limit", type=float, default=max(float(c("cam_limit", 16.0)), 16.0), help="faintest star, G")
    b.add_argument("--hmax", type=float, default=c("hmax", 17.0))
    b.add_argument("--all", action="store_true", help="all numbered asteroids, any H")
    b.add_argument("--min-drop", type=float, default=0.1)
    b.add_argument("--reach", type=float, default=200.0, help="largest reach (km) a pick will use")
    b.add_argument("--max-sun-alt", type=float, default=0.0, help="loosest Sun limit a pick will use (deg)")
    b.add_argument("--min-alt", type=float, default=0.0, help="lowest star altitude a pick will use (deg)")
    b.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    b.add_argument("--catalog", default=c("catalog"))
    b.add_argument("--chunk", type=int, help="asteroids per chunk (default: from the free memory)")
    b.add_argument("--max-mem", type=float, metavar="GB", help="memory budget for all workers (default: --mem-frac of "
                   "the available memory)")
    b.add_argument("--mem-frac", type=float, default=0.6, help="share of the available memory to use (default 0.6)")
    b.add_argument("--fresh", action="store_true", help="discard a partial build of this name instead of resuming it")
    b.add_argument("-o", "--output")
    sub.add_parser("list", help="the pre-screens in prescreen/")
    s = sub.add_parser("show", help="settings and numbers of one pre-screen")
    s.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for p, m in list_files():
            n_ev, n_ast = counts(p)
            age = age_days(m)
            print(f"{p}\n    {describe(p, m)}\n    {n_ast} asteroids, {n_ev} events"
                  + (f", {age:.0f} days old" if age is not None else ""))
        return 0
    if a.cmd == "show":
        m = read_meta(a.file)
        con = sqlite3.connect(f"file:{a.file}?mode=ro", uri=True)
        n_ev, n_ast = con.execute("SELECT COUNT(*), COUNT(DISTINCT number) FROM events").fetchone()
        print(describe(a.file, m))
        print(f"{n_ev} events of {n_ast} asteroids (of {m.get('asteroids_screened')} screened), build {m.get('build_s')} s")
        return 0
    if a.glob:
        region, name = None, a.name or "global"
    elif a.around_sites is not None:
        if not c("sites"):
            ap.error("--around-sites needs sites in sites.py")
        region, name = box_around_all(c("sites"), a.around_sites), a.name or f"sites_{a.around_sites:g}km"
    elif a.region:
        region, name = region_box(*[float(x) for x in a.region.split(",")]), a.name or "region"
    else:
        if c("lat") is None:
            ap.error("--around-site needs a configured site")
        region, name = box_around(c("lat"), c("lon"), a.around_site), a.name or f"{c('site') or 'site'}_{a.around_site:g}km"
    try:
        _build_cli(a, c, region, name)
    except KeyboardInterrupt:
        return 130
    except RuntimeError as e:
        print(f"pre-screen: {e}", file=sys.stderr)
        return 2
    return 0


def _build_cli(a, c, region, name):
    build(a.start, a.days, region, a.cam_limit, None if a.all else a.hmax, a.min_drop, a.reach, a.max_sun_alt,
          a.min_alt, a.workers, a.output, a.catalog, os.path.join(c("cache") or tempfile.gettempdir(),
                                                                  "PyOccult_sbdb_cache.json"), name,
          a.chunk, max_mem=a.max_mem * 1e9 if a.max_mem else None, mem_frac=a.mem_frac, fresh=a.fresh)


if __name__ == "__main__":
    sys.exit(main())
