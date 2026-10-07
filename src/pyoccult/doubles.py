"""doubles.py - close and double stars at an event: neighbours whose light blends with the target star's in the
camera, the drop with that light included, and Gaia's hints that the star itself is double.

Local check (every event, from the local catalog): stars within companion_radius_arcsec of the target star at the
event date. Their light stays when the target star is covered, so the real drop is smaller than the star's own:
    drop = 2.5 log10((F_star + F_comp + F_ast) / (F_comp + F_ast))
Online check (optional, gaia_online_check; one query per run to the Gaia DR3 archive): the same neighbours without
the local catalog's limits (fainter stars, and stars with RUWE >= 1.4 that the catalog leaves out, often unresolved
doubles), and Gaia's flags for the target star: non_single_star (a known binary solution), ipd_frac_multi_peak
(% of scans with two peaks: a resolved close pair), duplicated_source, ruwe.

Record fields: blend_n (neighbours within the radius), blend_sep_arcsec and blend_g (the closest one),
mag_drop_blended, double_hint (text for the report), double_check ("local" or "gaia online"); online also gaia_ruwe,
gaia_nss, gaia_multi_peak, gaia_dup. Reference information: events are flagged, not removed.
"""
from pyoccult.version import __version__
import csv, math, os, tempfile, threading
import numpy as np

DMAG = 5.0                 # neighbours more than this fainter than the star are ignored (< 1 % of its light)
MULTI_PEAK = 2             # ipd_frac_multi_peak above this (%): Gaia saw two peaks, likely a close pair
NOTE_DMAG = 0.1            # a neighbour is noted (double_hint) when it lowers the drop by at least this
GAIA_EPOCH = 2016.0


def _sep_arcsec(ra1, de1, ra2, de2):
    """Angular separation in arcsec (vectorised; degrees in)."""
    r1, d1, r2, d2 = (np.radians(np.asarray(x, float)) for x in (ra1, de1, ra2, de2))
    s = np.sin((d2 - d1) / 2) ** 2 + np.cos(d1) * np.cos(d2) * np.sin((r2 - r1) / 2) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(s, 0, 1)))) * 3600.0


def _propagate(ra, dec, pmra, pmdec, years):
    """Positions at GAIA_EPOCH + years (linear proper motion; missing motion = 0)."""
    pmra, pmdec = np.nan_to_num(np.asarray(pmra, float)), np.nan_to_num(np.asarray(pmdec, float))
    cosd = np.maximum(np.cos(np.radians(np.asarray(dec, float))), 1e-6)
    return (np.asarray(ra, float) + pmra / cosd * years / 3.6e6) % 360.0, np.asarray(dec, float) + pmdec * years / 3.6e6


def companions(stars, star_id, ra, dec, g_star, years, radius_arcsec):
    """[(sep_arcsec, G, source_id)] of the stars (DataFrame with source_id, ra, dec, pmra, pmdec, phot_g_mean_mag;
    Gaia epoch) within radius_arcsec of (ra, dec) at the event (years after 2016.0), not the star itself and not more
    than DMAG fainter; closest first."""
    if stars is None or len(stars) == 0:
        return []
    s = stars[stars["source_id"].astype("int64") != int(star_id)]
    s = s[np.isfinite(s["phot_g_mean_mag"].astype(float)) & (s["phot_g_mean_mag"].astype(float) <= g_star + DMAG)]
    if len(s) == 0:
        return []
    r, d = _propagate(s["ra"], s["dec"], s["pmra"], s["pmdec"], years)
    sep = _sep_arcsec(ra, dec, r, d)
    keep = sep <= radius_arcsec
    out = sorted(zip(sep[keep].tolist(), s["phot_g_mean_mag"].astype(float)[keep].tolist(),
                     s["source_id"].astype("int64")[keep].tolist()))
    return [(round(a, 2), round(b, 2), c) for a, b, c in out]


def blended_drop(m_star, m_ast, comp_mags):
    """Drop (mag) when the star is covered and its neighbours' light (comp_mags) stays."""
    f = lambda m: 10 ** (-0.4 * m)
    f_ast = f(m_ast) if m_ast is not None and np.isfinite(m_ast) else 0.0
    f_comp = sum(f(m) for m in comp_mags)
    if f_ast + f_comp <= 0:
        return float("inf")
    return 2.5 * math.log10((f(m_star) + f_comp + f_ast) / (f_comp + f_ast))


def fields(comps, m_star, m_ast, source="local", flags=None):
    """The record fields (module doc) from the neighbours list and, online, Gaia's flags of the star."""
    flags = flags or {}
    hints = []
    if flags.get("gaia_nss"):
        hints.append(f"Gaia: non-single star (NSS {int(flags['gaia_nss'])})")
    if (flags.get("gaia_multi_peak") or 0) > MULTI_PEAK:
        hints.append(f"Gaia: two peaks in {int(flags['gaia_multi_peak'])} % of scans (close pair?)")
    if flags.get("gaia_dup"):
        hints.append("Gaia: duplicated source")
    blended = blended_drop(m_star, m_ast, [c[1] for c in comps]) if comps else float("nan")
    if comps and blended_drop(m_star, m_ast, []) - blended >= NOTE_DMAG:
        sep, g, _ = comps[0]
        more = f" (+{len(comps) - 1} more)" if len(comps) > 1 else ""
        hints.append(f"companion G {g:.1f} at {sep:.1f}″{more}: drop {blended_drop(m_star, m_ast, [c[1] for c in comps]):.2f} mag "
                     "with its light")
    out = dict(blend_n=len(comps), blend_sep_arcsec=comps[0][0] if comps else np.nan,
               blend_g=comps[0][1] if comps else np.nan,
               mag_drop_blended=blended if comps else np.nan,
               double_hint="; ".join(hints), double_check=source)
    out.update(flags)
    return out


# ---------------------------------------------------------------- online check (Gaia archive, network only)
ARCHIVE_COLS = "source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, ruwe, non_single_star, ipd_frac_multi_peak, " \
               "duplicated_source"


def query_text(points, radius_arcsec):
    """One ADQL query for all events: circles around each (ra, dec) at the Gaia epoch, padded for proper motion."""
    r = (radius_arcsec + 3.0) / 3600.0
    circles = " OR ".join(f"1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.7f}, {de:.7f}, {r:.6f}))"
                          for ra, de in points)
    return f"SELECT {ARCHIVE_COLS} FROM gaiadr3.gaia_source WHERE {circles}"


def fetch_online(points, radius_arcsec, timeout_s=120):
    """DataFrame of archive stars around the points, or None (offline, slow, failed). Asynchronous job (the
    synchronous one silently truncates at 2000 rows); waited for at most timeout_s in a daemon thread."""
    box = {}

    def work():
        try:
            from astroquery.gaia import Gaia
            box["t"] = Gaia.launch_job_async(query_text(points, radius_arcsec), verbose=False).get_results()
        except Exception as ex:                                   # network, archive or astroquery trouble
            box["err"] = ex
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout_s)
    if "t" not in box:
        print(f"* Gaia online check skipped: {box.get('err', f'no answer within {timeout_s} s')}")
        return None
    df = box["t"].to_pandas()
    df.columns = [c.lower() for c in df.columns]
    return df


def online_fields(records, radius_arcsec, archive):
    """Per record (dicts with star, star_ra, star_dec, mag, m_ast, best_et): the fields from the archive stars."""
    out = []
    for r in records:
        years = 2000.0 + float(r["best_et"]) / (365.25 * 86400) - GAIA_EPOCH
        sid = int(r["star"])
        me = archive[archive["source_id"].astype("int64") == sid]
        flags = {}
        if len(me):
            m = me.iloc[0]
            g = lambda k: None if m[k] is None or (isinstance(m[k], float) and not np.isfinite(m[k])) else m[k]
            flags = dict(gaia_ruwe=g("ruwe"), gaia_nss=int(g("non_single_star") or 0),
                         gaia_multi_peak=int(g("ipd_frac_multi_peak") or 0), gaia_dup=bool(g("duplicated_source")))
        comps = companions(archive, sid, float(r["star_ra"]), float(r["star_dec"]), float(r["mag"]), years,
                           radius_arcsec)
        out.append(fields(comps, float(r["mag"]), r.get("m_ast"), "gaia online", flags))
    return out


def update_hits_csv(path, records, updates):
    """Set the fields in updates (one dict per record) in the rows of path that hold these records (same target and
    time); other rows and values stay as written. Atomic. Returns the number of rows updated."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return 0
    head = rows[0]
    for k in (k for u in updates for k in u):
        if k not in head:
            head.append(k)
    col = {k: i for i, k in enumerate(head)}
    key = {(str(r["target_id"]), str(r["best_utc"])): u for r, u in zip(records, updates)}
    n = 0
    for row in rows[1:]:
        row += [""] * (len(head) - len(row))
        u = key.get((row[col["target_id"]], row[col["best_utc"]]))
        if u:
            for k, v in u.items():
                row[col[k]] = "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else str(v)
            n += 1
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    with os.fdopen(fd, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    os.replace(tmp, path)
    return n
