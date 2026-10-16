"""sysinfo.py - what data PySyzygos has and uses: time and Earth orientation, star catalogs, asteroid data, results.

    pysyzygos info            # as text
    pysyzygos info --json     # for the GUI's System tab (it runs this as its own process: SPICE stays out of the GUI)

Reads the files in the data folder and the cache; only the kernels' coverage needs SPICE (kernels loaded here).
"""
from pysyzygos.version import __version__
import glob, json, os, re, sys, time


def _gb(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{n / 1e3:.0f} kB"


def _age(t):
    d = (time.time() - t) / 86400.0
    return f"{d:.0f} days ago" if d >= 1.5 else f"{d * 24:.0f} h ago"


def _size(paths):
    return sum(os.path.getsize(p) for p in paths if os.path.isfile(p))


def time_earth():
    """[(label, value)]: leap seconds, Earth orientation (measured / predicted), the planetary ephemeris."""
    from pysyzygos import kernels as K
    out = []
    lsk = K.lsk_file(".")
    try:
        text = open(lsk, encoding="latin-1").read()
        last = re.findall(r"@(\d{4}-[A-Z]{3}-\d{1,2})", text)[-1]
        dat = re.findall(r"DELTET/DELTA_AT\s*=\s*\(\s*([\s\S]*?)\)", text)
        n = re.findall(r"(\d+),\s*@", dat[0]) if dat else []
        out.append(("Leap seconds", f"{os.path.basename(lsk)}: last {last.title()}, TAI-UTC {n[-1] if n else '?'} s; "
                    f"NAIF checked {_age(os.path.getmtime(K.LSK_MARKER))}" if os.path.isfile(K.LSK_MARKER) else
                    f"{os.path.basename(lsk)}: last {last.title()}, TAI-UTC {n[-1] if n else '?'} s"))
    except (OSError, IndexError):
        out.append(("Leap seconds", f"{os.path.basename(lsk)}: missing"))
    try:
        import spiceypy as spice
        spice.furnsh(lsk)
        if os.path.isfile(K.EARTH_PCK):
            d = K.pck_comment_dates(K.EARTH_PCK)
            a, b = K.pck_span(spice, K.EARTH_PCK)
            out.append(("Earth orientation", f"{K.EARTH_PCK} of {(d['created'] or '?')[:10]} "
                        f"(downloaded {_age(os.path.getmtime(K.EARTH_PCK))}): measured to {d['last_datum'] or '?'}, "
                        f"predicted to {spice.et2utc(b, 'ISOC', 0)[:10]}; valid from {spice.et2utc(a, 'ISOC', 0)[:10]}"))
        else:
            out.append(("Earth orientation", f"{K.EARTH_PCK} missing: pysyzygos setup"))
        h = K.historic_earth_pck(".")
        if h:
            a, b = K.pck_span(spice, h)
            out.append(("Earth orientation before 2000", f"{os.path.basename(h)}: {spice.et2utc(a, 'ISOC', 0)[:10]} "
                        f"to {spice.et2utc(b, 'ISOC', 0)[:10]} (the newer file rules where both cover)"))
        else:
            out.append(("Earth orientation before 2000", "not downloaded (fetched by a search before 2000)"))
        if os.path.isfile("de440.bsp"):
            cov = spice.spkcov("de440.bsp", 3, spice.cell_double(200) if hasattr(spice, "cell_double")
                               else spice.stypes.SPICEDOUBLE_CELL(200))
            a, b = spice.wnfetd(cov, 0)
            out.append(("Planets (DE440)", f"de440.bsp: {spice.et2utc(a, 'ISOC', 0)[:10]} to "
                        f"{spice.et2utc(b, 'ISOC', 0)[:10]}, {_gb(os.path.getsize('de440.bsp'))}"))
    except Exception as e:                                          # no SPICE: show what the files say
        out.append(("Kernel coverage", f"not read ({str(e)[:80]})"))
    return out


def stars(in_use=None):
    """[(label, value)]: each local Gaia catalog (the one in use marked), supplements, indexes, extra star data."""
    from pysyzygos import gaia_local as GL, starrv, geoid
    out = []
    for d in sorted(glob.glob("gaia_dr3_*")):
        if not os.path.isfile(os.path.join(d, "catalog.json")):
            continue
        st = GL.status(d)
        files = [f for f in glob.glob(os.path.join(d, "*.npy")) if f.count(".") == 1 and "bright" not in f]
        try:
            import numpy as np
            n = sum(np.load(f, mmap_mode="r").shape[0] for f in files)
        except Exception:
            n = None
        mark = "  ← in use" if in_use and os.path.basename(os.path.normpath(in_use)) == d else ""
        out.append((f"Catalog {d}{mark}", f"G ≤ {st.get('gmax', '?')}, {n / 1e6:.1f} M stars, "
                    f"{_gb(_size(files))}, {st['done']}/{st['total']} files" + ("" if st["complete"] else " (incomplete)")
                    if n is not None else f"{st['done']}/{st['total']} files"))
        sd = GL.supplement_dir(d)
        if os.path.isfile(os.path.join(sd, "catalog.json")):
            m = json.load(open(os.path.join(sd, "catalog.json")))
            sfiles = [f for f in glob.glob(os.path.join(sd, "*.npy")) if f.count(".") == 1 and "bright" not in f]
            px = m.get("pm_xmatch") or {}
            pm = (f"; 2-parameter stars with a proper motion: {px.get('ucac5', 0) + px.get('ucac4', 0)} of "
                  f"{px.get('two_param', '?')} (UCAC5 {px.get('ucac5', 0)}, UCAC4 {px.get('ucac4', 0)})" if px else
                  "; 2-parameter stars without proper motions (pysyzygos gaia supplement-pm)")
            out.append((f"  supplement", f"high-RUWE and 2-parameter stars, G ≤ {m.get('gmax', '?')}, {_gb(_size(sfiles))}{pm}"))
        idx = sorted(glob.glob(os.path.join(d, "bright_G*.v2.npy")))
        if idx:
            gs = [re.search(r"bright_G([\d.]+)\.v2", f)[1] for f in idx]
            out.append(("  star indexes (pick)", ", ".join(
                f"G ≤ {g.rstrip('0').rstrip('.')} ({_gb(os.path.getsize(f))})" for g, f in zip(gs, idx))))
    n_rv = len(starrv._load())
    out.append(("Radial velocities", f"{n_rv} fast nearby stars (data/gaia_dr3_rv_fast.npy)" if n_rv else "table missing"))
    out.append(("Geoid (site heights)", "EGM96, 0.5 deg grid" if os.path.isfile(geoid.GRID) else "grid missing"))
    return out


def asteroids(cache_path):
    """[(label, value)]: the pick's asteroid list, size data and orbit files in the cache, offline copies, picks,
    pre-screens."""
    from pysyzygos import offline, sbdb
    out = []
    lst = os.path.join(cache_path, "PySyzygos_sbdb_cache.json")
    if os.path.isfile(lst):
        try:
            with open(lst) as f:
                b = json.load(f)
            age_d = (time.time() - (b.get("fetched") or 0)) / 86400.0
            max_d = sbdb.max_age_s() / 86400.0
            lim = "all numbered" if (b.get("hmax") or 0) > 99 else f"H < {b.get('hmax'):g}"
            out.append(("Asteroid list (SBDB, cache)", f"{len(b.get('data', []))} asteroids ({lim}) from "
                        f"{time.strftime('%Y-%m-%d', time.gmtime(b.get('fetched') or 0))} ({age_d:.0f} days old; "
                        f"{'renewed by the next pick' if age_d >= max_d else f'renewed after {max_d:.0f} days'}), "
                        f"{_gb(os.path.getsize(lst))}"))
        except (OSError, ValueError):
            out.append(("Asteroid list (SBDB, cache)", "unreadable"))
    else:
        out.append(("Asteroid list (SBDB, cache)", f"none in {cache_path} (the next pick downloads it)"))
    out.append(("Size data (SBDB, cache)", f"{len(sbdb.load(cache_path))} asteroids"))
    spk = glob.glob(os.path.join(cache_path, "PySyzygos_asteroid_*.bsp"))
    out.append(("Orbit files (Horizons, cache)", f"{len(spk)} files, {_gb(_size(spk))} (from searches since the "
                f"cache was last emptied; {cache_path})"))
    st = offline.status()
    s = st["sbdb"]
    out.append(("Offline copies", ("on" if st["enabled"] else "off") +
                (f": list from {time.strftime('%Y-%m-%d', time.gmtime(s['fetched']))} ({s.get('count')} asteroids), "
                 if s and s.get("fetched") else ": no list, ") +
                f"{st['orbits']} orbit files ({st['orbits_mb']:.1f} MB); copies of past picks and searches"))
    picks = sorted(glob.glob(os.path.join("picks", "*.csv")), key=os.path.getmtime)
    out.append(("Saved picks", f"{len(picks)}" + (f", newest {os.path.basename(picks[-1])}" if picks else "")))
    pre = sorted(glob.glob(os.path.join("prescreen", "*.db")) + glob.glob(os.path.join("prescreen", "*.global.npy")))
    out.append(("Pre-screens", ", ".join(os.path.basename(p).replace(".global.npy", " (whole Earth)").replace(".db", "")
                                         for p in pre) or "none"))
    return out


def results(results_db="pysyzygos.db"):
    out = []
    if os.path.isfile(results_db):
        try:
            import sqlite3
            con = sqlite3.connect(results_db)
            n_ev = con.execute("select count(*) from events").fetchone()[0]
            n_run = con.execute("select count(*) from runs").fetchone()[0]
            n_fav = con.execute("select count(*) from favorites").fetchone()[0]
            con.close()
            out.append(("Results database", f"{results_db}: {n_run} runs, {n_ev} events, {n_fav} favorites, "
                        f"{_gb(os.path.getsize(results_db))}"))
        except Exception as e:
            out.append(("Results database", f"{results_db}: not readable ({str(e)[:60]})"))
    else:
        out.append(("Results database", "none yet"))
    return out


def summary():
    from pysyzygos import config
    in_use = os.environ.get("PYSYZYGOS_CATALOG") or getattr(config, "gaia_local_dir", None)
    return [("Time and Earth", time_earth()), ("Stars", stars(in_use)),
            ("Asteroids", asteroids(config.cache_path)), ("Results", results(getattr(config, "results_db", "pysyzygos.db")))]


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    s = summary()
    if "--json" in a:
        print(json.dumps(s))
        return
    for group, rows in s:
        print(group)
        for k, v in rows:
            print(f"  {k:32s} {v}")


if __name__ == "__main__":
    main()
