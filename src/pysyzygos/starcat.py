"""starcat.py - the local star catalog, format 2 (since 1.3.0): all Gaia stars to a G limit in one catalog, sorted by
sky cell and magnitude, with the optional data in separate files of the same row order.

Why a new format: the first format (gaia_local.py) kept 40 bytes per star in 3386 files (one per ESA source file),
the high-RUWE and 2-parameter stars in a separate supplement, and the pick needed a copy of all stars sorted by cell
(bright_G16.0.v2.npy: as large as the catalog). Here one sort order serves every lookup (searches, picks, pre-screens,
previews), positions take 8 instead of 16 bytes, and what is not needed for finding events (Gaia's errors and flags,
colours) is optional:

    core      31 B/star   source_id, position, parallax, proper motion, G, flags (kind, duplicated, non-single star)
    quality   20 B/star   RUWE, errors and correlations (the star's error ellipse), NSS, multi-peak: what the online
                          check fetched per event, so a search without network has it too
    extras    10 B/star   BP and RP magnitudes (colour), radial velocity, Teff: for a star-size model later

G <= 16: 78 M stars (70 M with 5/6-parameter astrometry and RUWE < 1.4, 8 M high-RUWE or 2-parameter, flagged):
core 2.4 GB, + quality 1.6 GB, + extras 0.8 GB.

    pysyzygos catalog build --dir gaia_dr3_g16 --gmax 16     # from ESA's files (753 GB streamed, ~2 h; resumable)
    pysyzygos catalog fetch --dir gaia_dr3_g16              # ready-made G <= 16 from Zenodo (core + --groups)
    pysyzygos catalog add quality | remove extras           # optional parts, any time (System tab: checkboxes)
    pysyzygos catalog status | xmatch | pack

Layout of a catalog folder:
    catalog.json     format 2, release, gmax, cell size, stars, build id, groups present, cuts (written last: done)
    offsets.npy      int64, n_cells + 1: the rows of each 0.25 deg cell (cell = dec band * 1440 + ra band)
    core.npy         CORE rows, sorted by cell, then G
    hpm.npy          int64 rows of the stars with proper motion > HIGH_PM_MAS (they can leave a search strip's pad)
    quality.npy, extras.npy    optional, the same rows; each with <group>.json (build id, stars) so a later download
                               cannot be joined to another build
Network only for building and downloads; reading needs numpy (and pandas for DataFrames).
"""
from pysyzygos.version import __version__
from pysyzygos import urls as U
import argparse, json, math, os, secrets, shutil, subprocess, sys, tempfile, time
import numpy as np

FORMAT = 2
RELEASE = "Gaia DR3"
CELL = 0.25                                                    # deg
N_RA, N_DEC = int(round(360 / CELL)), int(round(180 / CELL))
N_CELLS = N_RA * N_DEC
SCALE = CELL / 2.0 ** 32                                       # deg per position step (0.0002 mas)
G_MMAG_NONE = 0xFFFF
CORR_NONE = -128
HIGH_PM_MAS = 1500.0                                           # as gaia_local (the corridor pm pad)
RUWE_MAX = 1.4
KIND_MAIN, KIND_RUWE, KIND_2P, KIND_2P_UCAC5, KIND_2P_UCAC4 = 0, 1, 2, 3, 4    # as gaia_local
FLAG_KIND, FLAG_DUP, FLAG_NSS = 0x07, 0x08, 0x10

CORE = np.dtype([("source_id", "<i8"), ("dra", "<u4"), ("ddec", "<u4"), ("parallax", "<f4"), ("pmra", "<f4"),
                 ("pmdec", "<f4"), ("g", "<u2"), ("flags", "u1")])
CORR_COLS = ("ra_dec_corr", "ra_pmra_corr", "ra_pmdec_corr", "dec_pmra_corr", "dec_pmdec_corr", "pmra_pmdec_corr")
ERR_COLS = ("ra_error", "dec_error", "parallax_error", "pmra_error", "pmdec_error")
QUALITY = np.dtype([("ruwe", "<f2")] + [(c, "<f2") for c in ERR_COLS] + [(c, "i1") for c in CORR_COLS]
                   + [("nss", "u1"), ("multi_peak", "u1")])
EXTRAS = np.dtype([("bp", "<u2"), ("rp", "<u2"), ("rv", "<f2"), ("rv_error", "<f2"), ("teff", "<f2")])
GROUPS = {"quality": QUALITY, "extras": EXTRAS}
GROUP_TEXT = {"core": "positions, motions, G, flags (needed)",
              "quality": "RUWE, Gaia's errors and flags (error ellipse, double-star hints without network)",
              "extras": "BP/RP colour, radial velocity, Teff (for a star-size model later)"}
PART = np.dtype(CORE.descr + QUALITY.descr + EXTRAS.descr + [("cell", "<u4")])
CSV_COLS = ["source_id", "ra", "dec", "parallax", "pmra", "pmdec", "phot_g_mean_mag", "ruwe", *ERR_COLS, *CORR_COLS,
            "non_single_star", "ipd_frac_multi_peak", "duplicated_source", "phot_bp_mean_mag", "phot_rp_mean_mag",
            "radial_velocity", "radial_velocity_error", "teff_gspphot"]
# common output layout of near_path (as gaia_local.COMMON_DTYPE: the pick screen's star rows)
ROWS = np.dtype([("source_id", "<i8"), ("ra", "<f8"), ("dec", "<f8"), ("parallax", "<f4"), ("pmra", "<f4"),
                 ("pmdec", "<f4"), ("phot_g_mean_mag", "<f4"), ("ruwe", "<f4"), ("kind", "u1")])
ZENODO_STEM = {16.0: "gaia_dr3_g16_v2"}                        # archives <stem>_<group>.tar.xz on the catalog record
# the published archives (build d242c96ed70f63b3, 2026-10-16): size and SHA-256, so a mirror's copy is checked without
# Zenodo; a newer build on Zenodo (another checksum there) is taken from Zenodo's .sha256 instead
ARCHIVE_SHA256 = {
    "gaia_dr3_g16_v2_core.tar.xz": (2034082136, "6d1dfc8e4cba430ed0e4f840a8f0a23e648ceac1b82868b56990932fd618ece4"),
    "gaia_dr3_g16_v2_quality.tar.xz": (None, "55e82c33b2f0882515801f47d53785b18608c17ab448bd1e25519f5dda13142b"),
    "gaia_dr3_g16_v2_extras.tar.xz": (None, "1262480f747c207fc868727e6f110da63f62d64f3f57a96dc91ad87a9f38ba10"),
}


# ----------------------------------------------------------------------------------------------- encoding
def cell_of(ra_deg, dec_deg):
    di = np.clip(np.floor((np.asarray(dec_deg, float) + 90.0) / CELL), 0, N_DEC - 1).astype(np.int64)
    ri = (np.floor((np.asarray(ra_deg, float) % 360.0) / CELL).astype(np.int64)) % N_RA
    return di * N_RA + ri


def encode(ra_deg, dec_deg):
    """(cell, dra, ddec): the cell and the position inside it in steps of SCALE."""
    ra, dec = np.asarray(ra_deg, float) % 360.0, np.asarray(dec_deg, float)
    cell = cell_of(ra, dec)
    q = lambda x: np.clip(np.floor(x / SCALE + 0.5), 0, 2 ** 32 - 1).astype(np.uint32)
    return cell, q(ra - (cell % N_RA) * CELL), q(dec + 90.0 - (cell // N_RA) * CELL)


def decode(cell, dra, ddec):
    cell = np.asarray(cell, np.int64)
    return ((cell % N_RA) * CELL + np.asarray(dra, float) * SCALE,
            (cell // N_RA) * CELL - 90.0 + np.asarray(ddec, float) * SCALE)


def _mmag(m):
    m = np.asarray(m, float)
    return np.where(np.isfinite(m), np.clip(np.round(m * 1000.0), 0, G_MMAG_NONE - 1), G_MMAG_NONE).astype(np.uint16)


def _mag(u):
    u = np.asarray(u)
    return np.where(u == G_MMAG_NONE, np.nan, u / 1000.0)


def _corr(c):
    c = np.asarray(c, float)
    return np.where(np.isfinite(c), np.clip(np.round(c * 127.0), -127, 127), CORR_NONE).astype(np.int8)


def _uncorr(i):
    i = np.asarray(i)
    return np.where(i == CORR_NONE, np.nan, i / 127.0)


def kind_of(flags):
    return np.asarray(flags) & FLAG_KIND


# ----------------------------------------------------------------------------------------------- build
def part_rows(df, gmax):
    """PART rows of a Gaia source table (DataFrame with CSV_COLS): every star with G <= gmax and a position; kind
    main (5/6-parameter, RUWE < RUWE_MAX), RUWE (5/6-parameter, RUWE >= RUWE_MAX) or 2-parameter (no parallax/pm:
    stored 0, a cross-match may add a proper motion later)."""
    df = df[(df.phot_g_mean_mag <= gmax) & df.ra.notna() & df.dec.notna()]
    out = np.zeros(len(df), PART)
    col = lambda c: df[c].to_numpy(dtype=float, na_value=np.nan)
    cell, out["dra"], out["ddec"] = encode(col("ra"), col("dec"))
    out["cell"] = cell
    out["source_id"] = df.source_id.to_numpy(np.int64)
    two_p = np.isnan(col("pmra")) | np.isnan(col("parallax"))
    for c in ("parallax", "pmra", "pmdec"):
        out[c] = np.nan_to_num(col(c))
    out["g"] = _mmag(col("phot_g_mean_mag"))
    ruwe = col("ruwe")
    kind = np.where(two_p, KIND_2P, np.where(ruwe < RUWE_MAX, KIND_MAIN, KIND_RUWE))
    dup = df.duplicated_source.astype(str).str.strip().str.lower().isin(("true", "1", "t")).to_numpy()
    nss = np.nan_to_num(col("non_single_star")).astype(np.int64)
    out["flags"] = kind | np.where(dup, FLAG_DUP, 0) | np.where(nss > 0, FLAG_NSS, 0)
    out["ruwe"] = ruwe
    for c in ERR_COLS:
        out[c] = col(c)
    for c in CORR_COLS:
        out[c] = _corr(col(c))
    out["nss"] = np.clip(nss, 0, 255)
    out["multi_peak"] = np.clip(np.nan_to_num(col("ipd_frac_multi_peak")), 0, 255)
    out["bp"], out["rp"] = _mmag(col("phot_bp_mean_mag")), _mmag(col("phot_rp_mean_mag"))
    out["rv"], out["rv_error"], out["teff"] = col("radial_velocity"), col("radial_velocity_error"), col("teff_gspphot")
    return out


def process_file(name, parts_dir, gmax):
    """Download one ESA source file, keep its stars as PART rows in parts_dir/<stem>.npy (written last: done).
    Returns (name, stars in, stars kept, seconds)."""
    import pandas as pd
    from pysyzygos import gaia_local as GL
    stem = name[:-len(".csv.gz")]
    final = os.path.join(parts_dir, stem + ".npy")
    if os.path.isfile(final):
        return name, None, None, 0.0
    t0 = time.time()
    fd, gz = tempfile.mkstemp(dir=parts_dir, suffix=".csv.gz.tmp")
    os.close(fd)
    try:
        GL._download(name, gz)
        df = pd.read_csv(gz, compression="gzip", comment="#", na_values=["null"], usecols=CSV_COLS)
    finally:
        os.remove(gz)
    arr = part_rows(df, gmax)
    GL._save_atomic(final, arr)
    return name, len(df), len(arr), time.time() - t0


def _write_json(path, obj):
    from pysyzygos import gaia_local as GL
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1)
    GL.replace_file(tmp, path)


def build(out_dir, gmax=16.0, workers=6, groups=("quality", "extras"), files=None, keep_parts=False):
    """Build (or resume) a format-2 catalog in out_dir from ESA's Gaia files: 1) each source file -> parts/<stem>.npy
    (resumable), 2) merge into cell order, sorted by G in each cell (low memory: memory-mapped output), 3) catalog.json.
    files: [(name, size)] instead of ESA's listing (tests). Returns status(out_dir)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from pysyzygos import gaia_local as GL
    if is_format2(out_dir):
        print(f"{out_dir}: complete")
        return status(out_dir)
    if os.path.isfile(os.path.join(out_dir, "catalog.json")):
        sys.exit(f"{out_dir} holds a catalog of the old format; build the new one elsewhere (setup --upgrade-catalog "
                 f"does it next to it and swaps)")
    parts = os.path.join(out_dir, "parts")
    os.makedirs(parts, exist_ok=True)
    bpath = os.path.join(out_dir, "build.json")
    if files is None:
        print("listing ESA's Gaia DR3 files ...", flush=True)
        files = GL.list_files()
    if os.path.isfile(bpath):
        b = json.load(open(bpath))
        if abs(b["gmax"] - gmax) > 1e-9:
            sys.exit(f"{out_dir} holds a partial build with G <= {b['gmax']:g}; use another folder")
    _write_json(bpath, dict(format=FORMAT, gmax=gmax, groups=list(groups), source=U.URL_GAIA_DR3_FILES,
                            files=[n for n, _ in files], started=time.strftime("%Y-%m-%d %H:%M:%S")))
    for t in os.listdir(parts):
        if t.endswith(".tmp"):
            os.remove(os.path.join(parts, t))
    todo = [n for n, _ in files if not os.path.isfile(os.path.join(parts, n[:-len(".csv.gz")] + ".npy"))]
    gb = sum(s for n, s in files if n in set(todo)) / 1e9
    print(f"{len(files)} source files, {len(todo)} to do ({gb:.0f} GB to download), G <= {gmax:g}, {workers} workers",
          flush=True)
    done, kept, seen, failed = 0, 0, 0, []
    if todo:
        ex = ProcessPoolExecutor(max_workers=workers) if workers > 0 else None
        futs = {ex.submit(process_file, n, parts, gmax): n for n in todo} if ex else {}
        prog = GL.Progress("ESA build", len(todo), fmt=lambda x: f"{x:.0f} files", rate=lambda r: f"{r * 60:.1f} files/min")
        prog(0, " (first files take a minute or two)", force=True)
        stream = ((n, None) for n in todo) if ex is None else ((futs[f], f) for f in as_completed(futs))
        try:
            for name, fut in stream:
                try:
                    _, n_in, n_keep, _ = process_file(name, parts, gmax) if fut is None else fut.result()
                except Exception as e:                   # this file failed after its retries: a rerun resumes it
                    failed.append(name)
                    print(f"\n   failed: {name}: {str(e)[:160]}", flush=True)
                    if len(failed) >= max(3, workers) and done == len(failed) - 1:
                        raise RuntimeError(f"the first {len(failed)} Gaia files all failed to download from "
                                           f"{U.URL_GAIA_DR3_FILES}: offline, server down, or blocked by a proxy or "
                                           f"firewall. Last error: {str(e)[:200]}") from None
                    continue
                finally:
                    done += 1
                if n_in is not None:
                    seen, kept = seen + n_in, kept + n_keep
                prog(done, f", {kept / 1e6:.1f} M of {seen / 1e6:.1f} M stars kept", force=done == len(todo))
        finally:
            if ex is not None:
                ex.shutdown(cancel_futures=True)
        prog.finish(f"{done - len(failed)} files, {kept / 1e6:.1f} M stars kept")
    if failed:
        print(f"{len(failed)} files failed (network); rerun to fetch just those (it resumes)")
        return status(out_dir)
    merge(out_dir, gmax, groups, [os.path.join(parts, n[:-len(".csv.gz")] + ".npy") for n, _ in files],
          source=U.URL_GAIA_DR3_FILES)
    if not keep_parts:
        shutil.rmtree(parts, ignore_errors=True)
        os.remove(bpath)
    return status(out_dir)


def merge(out_dir, gmax, groups, part_files, source="", block=4_000_000):
    """Parts -> core.npy (+ groups), offsets.npy, hpm.npy, catalog.json. Peak memory: one part or one block."""
    from pysyzygos import gaia_local as GL
    t0 = time.time()
    counts = np.zeros(N_CELLS, np.int64)
    prog = GL.Progress("merge", 2 * len(part_files), fmt=lambda x: f"{x:.0f} file reads", rate=lambda r: f"{r:.0f} files/s")
    for i, f in enumerate(part_files, 1):
        counts += np.bincount(np.load(f, mmap_mode="r")["cell"], minlength=N_CELLS)
        prog(i)
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    n = int(offsets[-1])
    names = ["core"] + [g for g in GROUPS if g in groups]
    dts = dict(core=CORE, **GROUPS)
    tmp = {g: os.path.join(out_dir, f"{g}.npy.tmp") for g in names}
    outs = {g: np.lib.format.open_memmap(tmp[g], mode="w+", dtype=dts[g], shape=(n,)) for g in names}
    cursor = offsets[:-1].copy()
    for i, f in enumerate(part_files, 1):
        a = np.load(f)
        cell = a["cell"].astype(np.int64)
        order = np.argsort(cell, kind="stable")
        a, cell = a[order], cell[order]
        pos = cursor[cell] + (np.arange(len(cell)) - np.searchsorted(cell, cell, side="left"))
        for g in names:
            sub = np.zeros(len(a), dts[g])
            for k in dts[g].names:
                sub[k] = a[k]
            outs[g][pos] = sub
        cursor += np.bincount(cell, minlength=N_CELLS)
        prog(len(part_files) + i)
    prog.finish("read; sorting by G within cells")
    hpm, i = [], 0
    while i < n:                                                   # sort each cell by G, a block of cells at a time
        j = int(offsets[np.searchsorted(offsets, i + block, side="right") - 1])
        if j <= i:
            j = int(offsets[np.searchsorted(offsets, i, side="right")])
        c = np.searchsorted(offsets, np.arange(i, j), side="right") - 1
        blk = np.array(outs["core"][i:j])
        order = np.lexsort((blk["source_id"], blk["g"], c))
        outs["core"][i:j] = blk[order]
        for g in names[1:]:
            outs[g][i:j] = np.array(outs[g][i:j])[order]
        b = blk[order]
        pm = np.hypot(b["pmra"].astype(float), b["pmdec"].astype(float))
        hpm.append(i + np.where(pm > HIGH_PM_MAS)[0])
        i = j
    for g in names:
        outs[g].flush()
    outs = blk = b = None                                          # unmapped before the renames (Windows)
    build_id = secrets.token_hex(8)
    _save(os.path.join(out_dir, "offsets.npy"), offsets)
    _save(os.path.join(out_dir, "hpm.npy"), np.concatenate(hpm) if hpm else np.zeros(0, np.int64))
    for g in names:
        GL.replace_file(tmp[g], os.path.join(out_dir, f"{g}.npy"))
        if g != "core":
            _write_json(os.path.join(out_dir, f"{g}.json"), dict(group=g, build_id=build_id, n_stars=n))
    _write_json(os.path.join(out_dir, "catalog.json"), dict(
        format=FORMAT, release=RELEASE, gmax=float(gmax), cell_deg=CELL, n_stars=n, build_id=build_id,
        groups=names, ruwe_max=RUWE_MAX, high_pm_mas=HIGH_PM_MAS, source=source, version=__version__,
        created=time.strftime("%Y-%m-%d %H:%M:%S"),
        contents=f"all stars G <= {gmax:g} with a position; kinds {KIND_MAIN} main, {KIND_RUWE} RUWE >= {RUWE_MAX}, "
                 f"{KIND_2P} 2-parameter (no parallax/pm, stored 0), {KIND_2P_UCAC5}/{KIND_2P_UCAC4} 2-parameter "
                 f"with a UCAC5/UCAC4 proper motion"))
    print(f"catalog: {n / 1e6:.1f} M stars in {time.time() - t0:.0f} s -> {out_dir}", flush=True)


def _save(path, arr):
    from pysyzygos import gaia_local as GL
    GL._save_atomic(path, arr)


def xmatch(out_dir, chunk=50000, log=print, fetch=None):
    """Proper motions for the 2-parameter stars (Gaia has none): UCAC5, then UCAC4 via CDS XMatch, as
    gaia_local.supplement_pm. Written into core.npy in place (pmra/pmdec, kind 3/4) and, if present, quality.npy (the
    UCAC proper-motion errors as pmra_error/pmdec_error). fetch(rows, cat) stands in for the XMatch call (tests).
    Recorded in catalog.json (pm_xmatch); a rerun only looks at stars still without. Returns the counts."""
    import pandas as pd
    from pysyzygos import gaia_local as GL
    man = _manifest(out_dir)
    core = np.load(os.path.join(out_dir, "core.npy"), mmap_mode="r+")
    offsets = np.load(os.path.join(out_dir, "offsets.npy"))
    rows = np.where(kind_of(core["flags"]) == KIND_2P)[0]
    c = core[rows]
    ra, dec = decode(np.searchsorted(offsets, rows, side="right") - 1, c["dra"], c["ddec"])
    todo = pd.DataFrame(dict(source_id=c["source_id"], ra=ra, dec=dec, g=_mag(c["g"]), row=rows))
    log(f"   {len(todo)} 2-parameter stars: proper motions from UCAC5, then UCAC4 (CDS XMatch, {chunk} per request)")
    fetch = fetch or GL._xmatch
    found = {}
    for cat, pick, kind in (("vizier:I/340/ucac5", GL.pick_ucac5, KIND_2P_UCAC5),
                            ("vizier:I/322A/out", GL.pick_ucac4, KIND_2P_UCAC4)):
        left = todo[~todo.source_id.isin(found)]
        for i in range(0, len(left), chunk):
            p = pick(fetch(left.iloc[i:i + chunk], cat))
            for sid, pa, pd_, pe in zip(p.source_id.astype("int64"), p.pmra, p.pmdec, p.pm_error):
                found[int(sid)] = (float(pa), float(pd_), float(pe), kind)
            log(f"   {cat.split(':')[1]}: {min(i + chunk, len(left))}/{len(left)} stars, {len(found)} with a proper motion")
    qpath = os.path.join(out_dir, "quality.npy")
    q = np.load(qpath, mmap_mode="r+") if os.path.isfile(qpath) else None
    if found:
        by_sid = dict(zip(todo.source_id.tolist(), todo.row.tolist()))
        r = np.array([by_sid[s] for s in found], np.int64)
        v = np.array(list(found.values()), float)                  # pmra, pmdec, pm_error, kind
        order = np.argsort(r)
        r, v = r[order], v[order]
        core["pmra"][r], core["pmdec"][r] = v[:, 0], v[:, 1]
        core["flags"][r] = (core["flags"][r] & np.uint8(0xFF ^ FLAG_KIND)) | v[:, 3].astype(np.uint8)
        if q is not None:
            q["pmra_error"][r] = q["pmdec_error"][r] = v[:, 2]
    core.flush()
    if q is not None:
        q.flush()
    k = kind_of(core["flags"])
    n5, n4, n0 = int((k == KIND_2P_UCAC5).sum()), int((k == KIND_2P_UCAC4).sum()), int((k == KIND_2P).sum())
    core = q = None
    man["pm_xmatch"] = dict(two_param=n5 + n4 + n0, ucac5=n5, ucac4=n4, none=n0, date=time.strftime("%Y-%m-%d"),
                            method="CDS XMatch: UCAC5 (Gaia DR1 2015.0 pos <= 0.2\", dG <= 0.5), then UCAC4 "
                                   "(pos at 2016 <= 0.5\", dmag <= 1)")
    _write_json(os.path.join(out_dir, "catalog.json"), man)
    log(f"   proper motions: {n5} from UCAC5, {n4} from UCAC4, {n0} still without (of {n5 + n4 + n0})")
    return man["pm_xmatch"]


# ----------------------------------------------------------------------------------------------- folder state
def _manifest(d):
    with open(os.path.join(d, "catalog.json")) as f:
        return json.load(f)


def is_format2(d):
    try:
        return _manifest(d).get("format") == FORMAT and os.path.isfile(os.path.join(d, "core.npy"))
    except (OSError, ValueError):
        return False


def group_ok(d, g, man=None):
    """Is the optional group g present and from the same build as the core?"""
    man = man or _manifest(d)
    try:
        with open(os.path.join(d, f"{g}.json")) as f:
            m = json.load(f)
    except (OSError, ValueError):
        return False
    return (m.get("build_id") == man.get("build_id") and m.get("n_stars") == man.get("n_stars")
            and os.path.isfile(os.path.join(d, f"{g}.npy")))


def groups_present(d):
    man = _manifest(d)
    return ["core"] + [g for g in GROUPS if group_ok(d, g, man)]


def group_bytes(d, g):
    return sum(os.path.getsize(os.path.join(d, f)) for f in (
        ("core.npy", "offsets.npy", "hpm.npy") if g == "core" else (f"{g}.npy",)) if os.path.isfile(os.path.join(d, f)))


def status(d):
    """As gaia_local.status: total/done (1/1 when complete), gb, complete, gmax; plus format, n_stars, groups."""
    if is_format2(d):
        man = _manifest(d)
        gs = groups_present(d)
        return dict(total=1, done=1, gb=sum(group_bytes(d, g) for g in gs) / 1e9, complete=True, gmax=man["gmax"],
                    format=FORMAT, n_stars=man["n_stars"], groups=gs, pm_xmatch=man.get("pm_xmatch"))
    b = os.path.join(d, "build.json")
    if os.path.isfile(b):
        bj = json.load(open(b))
        parts = os.path.join(d, "parts")
        have = {f for f in os.listdir(parts) if f.endswith(".npy")} if os.path.isdir(parts) else set()
        done = sum((n[:-len(".csv.gz")] + ".npy") in have for n in bj["files"])
        return dict(total=len(bj["files"]), done=done, gb=0.0, complete=False, gmax=bj["gmax"], format=FORMAT,
                    groups=[])
    return dict(total=0, done=0, gb=0.0, complete=False, format=FORMAT, groups=[])


def remove_group(d, g):
    if g == "core" or g not in GROUPS:
        raise ValueError(f"only optional parts can be removed: {', '.join(GROUPS)}")
    for f in (f"{g}.npy", f"{g}.json"):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    man = _manifest(d)
    man["groups"] = [x for x in man.get("groups", []) if x != g]
    _write_json(os.path.join(d, "catalog.json"), man)


# ----------------------------------------------------------------------------------------------- read side
def _use_supplement():
    from pysyzygos import gaia_local as GL
    return GL.use_supplement()


class StarCatalog:
    """Read side of a format-2 catalog: the methods of gaia_local.LocalGaia (cone, corridor_stars, high_pm, gmax) and of
    its BrightIndex (near_path), on one memory-mapped core. supplement (default: gaia_local.use_supplement()): also the
    high-RUWE and 2-parameter stars (flagged by kind); off: kind 0 only."""

    def __init__(self, d, supplement=None, allow_partial=False):
        self.dir = d
        self.man = _manifest(d)
        self.gmax = float(self.man["gmax"])
        self.sup = _use_supplement() if supplement is None else bool(supplement)
        self.offsets = np.load(os.path.join(d, "offsets.npy"))
        self.core = np.load(os.path.join(d, "core.npy"), mmap_mode="r")
        self.hpm_rows = np.load(os.path.join(d, "hpm.npy"))
        self.groups = {g: np.load(os.path.join(d, f"{g}.npy"), mmap_mode="r") for g in GROUPS if group_ok(d, g, self.man)}
        self.quality = self.groups.get("quality")
        self.extras = self.groups.get("extras")
        self.stars = self.core                                   # (BrightIndex users test len(index.stars))

    # rows -------------------------------------------------------------------------------------
    def _cell_rows(self, cells, cap=None):
        """Row indices of these cells, G <= cap (each cell is sorted by G: only its bright end is read)."""
        cells = np.asarray(cells, np.int64)
        lo, hi = self.offsets[cells], self.offsets[cells + 1]
        keep = hi > lo
        lo, hi = lo[keep], hi[keep]
        if cap is not None and cap < self.gmax:
            g, lim = self.core["g"], int(math.floor(cap * 1000.0 + 1e-6))
            hi = np.array([a + np.searchsorted(g[a:b], lim, "right") for a, b in zip(lo, hi)], np.int64)
        if not len(lo):
            return np.empty(0, np.int64)
        n = hi - lo
        return np.repeat(lo - np.concatenate([[0], np.cumsum(n)[:-1]]), n) + np.arange(int(n.sum()))

    def rows(self, idx):
        """ROWS (structured) of the row indices idx (sorted), without the stars the supplement switch leaves out."""
        idx = np.asarray(idx, np.int64)
        c = np.asarray(self.core[idx])
        if not self.sup and len(c):
            m = kind_of(c["flags"]) == KIND_MAIN
            idx, c = idx[m], c[m]
        out = np.zeros(len(c), ROWS)
        out["ra"], out["dec"] = decode(np.searchsorted(self.offsets, idx, side="right") - 1, c["dra"], c["ddec"])
        for k in ("source_id", "parallax", "pmra", "pmdec"):
            out[k] = c[k]
        out["phot_g_mean_mag"] = _mag(c["g"])
        out["kind"] = kind_of(c["flags"])
        out["ruwe"] = np.asarray(self.quality["ruwe"][idx], float) if self.quality is not None else np.nan
        return out, idx, c

    def frame(self, idx, full=False):
        """DataFrame like gaia_local._frame (COLS, star_kind, ruwe, pos_err, pm_err); full: also the quality columns
        (Gaia's names, as the online check: ruwe, the errors and correlations, non_single_star, ipd_frac_multi_peak,
        duplicated_source) and the extras (phot_bp_mean_mag, phot_rp_mean_mag, radial_velocity, ...)."""
        import pandas as pd
        r, idx, c = self.rows(idx)
        df = pd.DataFrame({k: r[k].astype(np.float64) if k != "source_id" else r[k] for k in
                           ("source_id", "ra", "dec", "parallax", "pmra", "pmdec", "phot_g_mean_mag")})
        df["star_kind"] = r["kind"].astype(np.int64)
        df["ruwe"] = r["ruwe"].astype(np.float64)
        q = np.asarray(self.quality[idx]) if self.quality is not None else None
        df["pos_err"] = np.maximum(q["ra_error"], q["dec_error"]).astype(np.float64) if q is not None else np.nan
        two_p_pm = np.isin(r["kind"], (KIND_2P_UCAC5, KIND_2P_UCAC4))
        df["pm_err"] = (np.where(two_p_pm, np.maximum(q["pmra_error"], q["pmdec_error"]), np.nan).astype(np.float64)
                        if q is not None else np.nan)
        if full:
            df["duplicated_source"] = (c["flags"] & FLAG_DUP) > 0
            if q is not None:
                for k in ERR_COLS:
                    df[k] = q[k].astype(np.float64)
                for k in CORR_COLS:
                    df[k] = _uncorr(q[k])
                df["non_single_star"] = q["nss"].astype(np.int64)
                df["ipd_frac_multi_peak"] = q["multi_peak"].astype(np.int64)
            else:
                df["non_single_star"] = ((c["flags"] & FLAG_NSS) > 0).astype(np.int64)
            if self.extras is not None:
                e = np.asarray(self.extras[idx])
                df["phot_bp_mean_mag"], df["phot_rp_mean_mag"] = _mag(e["bp"]), _mag(e["rp"])
                for k, src in (("radial_velocity", "rv"), ("radial_velocity_error", "rv_error"), ("teff_gspphot", "teff")):
                    df[k] = e[src].astype(np.float64)
        return df

    # lookups (the interfaces of LocalGaia and BrightIndex) ---------------------------------------
    def _path_rows(self, U, w_deg, cap, sample_deg=None):
        from pysyzygos.corridor import _radec, _unit
        from pysyzygos.gaia_local import cells_near, near_path_mask
        if len(U) == 0:
            return np.empty(0, np.int64)
        w_deg = np.broadcast_to(np.asarray(w_deg, float), (len(U),))
        ang = np.degrees(np.arccos(np.clip(np.sum(U[:-1] * U[1:], axis=1), -1, 1)))
        cum = np.concatenate(([0.0], np.cumsum(ang)))
        pick = np.unique(np.concatenate((np.searchsorted(cum, np.arange(0, cum[-1], sample_deg or CELL / 5)),
                                         [len(U) - 1])))
        ra, dec = _radec(U[pick])
        cells = cells_near(ra, dec, 1.5 * float(np.max(w_deg)) + CELL / 5, CELL)
        idx = self._cell_rows(cells, cap)
        if not len(idx):
            return idx
        c = np.asarray(self.core[idx][["dra", "ddec"]])
        r, d = decode(np.searchsorted(self.offsets, idx, side="right") - 1, c["dra"], c["ddec"])
        return idx[near_path_mask(_unit(r, d), U, w_deg)]

    def near_path(self, U, w_deg, mag_cap=None, sample_deg=None):
        """As BrightIndex.near_path: ROWS within w_deg of the path U (a superset; the scan does the exact test)."""
        return self.rows(self._path_rows(U, w_deg, mag_cap, sample_deg))[0]

    def high_pm(self):
        return self.rows(self.hpm_rows)[0]

    def corridor_stars(self, plan, include_high_pm=True, chunk_deg=0.05):
        """As LocalGaia.corridor_stars: stars (G <= the plan's mag cap) near its path, plus the fast movers."""
        path = plan["path"]
        U, D = path["u"], path["delta_km"]
        w = np.degrees(plan["margin_km"] / D) + plan["pad_arcsec"] / 3600.0
        cap = plan["mag_cap"]
        if cap > self.gmax + 1e-9:
            print(f"{plan['target']}: magnitude cap {cap:.1f} is fainter than the local catalog (G <= {self.gmax:g}); "
                  f"using {self.gmax:g}")
        idx = self._path_rows(U, w, cap)
        if include_high_pm and len(self.hpm_rows):
            h = self.hpm_rows[_mag(self.core["g"][self.hpm_rows]) <= cap + 1e-9]
            idx = np.union1d(idx, h)
        return self.frame(idx).drop_duplicates("source_id").reset_index(drop=True)

    def cone(self, ra_deg, dec_deg, radius_deg, mag_cap=None):
        """As LocalGaia.cone, with all columns there are (frame full=True)."""
        from pysyzygos.corridor import _unit
        from pysyzygos.gaia_local import cells_near
        idx = self._cell_rows(cells_near([ra_deg], [dec_deg], [radius_deg], CELL), mag_cap)
        if len(idx):
            c = np.asarray(self.core[idx][["dra", "ddec"]])
            r, d = decode(np.searchsorted(self.offsets, idx, side="right") - 1, c["dra"], c["ddec"])
            idx = idx[_unit(r, d) @ _unit(ra_deg, dec_deg) >= math.cos(math.radians(radius_deg))]
        return self.frame(idx, full=True)


# ----------------------------------------------------------------------------------------------- Zenodo
def archive_name(gmax, group):
    stem = ZENODO_STEM.get(float(gmax))
    return f"{stem}_{group}.tar.xz" if stem else None


GROUP_FILES = {"core": ("catalog.json", "offsets.npy", "core.npy", "hpm.npy")}


def _group_files(g):
    return GROUP_FILES.get(g, (f"{g}.json", f"{g}.npy"))


def pack(d, out_folder, groups=None, xz_threads=0):
    """The Zenodo archives of catalog d: <stem>_<group>.tar.xz (+ .sha256) per group, top folder <stem>. Uses xz with
    threads where installed (-T0), else Python's lzma. Returns the archive paths."""
    import tarfile, hashlib
    man = _manifest(d)
    stem = ZENODO_STEM.get(float(man["gmax"])) or f"gaia_dr3_g{man['gmax']:g}_v2"
    os.makedirs(out_folder, exist_ok=True)
    out = []
    for g in groups or groups_present(d):
        tar = os.path.join(out_folder, f"{stem}_{g}.tar")
        with tarfile.open(tar, "w") as tf:
            for f in _group_files(g):
                tf.add(os.path.join(d, f), arcname=f"{stem}/{f}")
        xz = tar + ".xz"
        if shutil.which("xz"):
            subprocess.run(["xz", f"-T{xz_threads}", "-6", "-f", tar], check=True)
        else:
            import lzma
            with open(tar, "rb") as src, lzma.open(xz, "wb", preset=6) as dst:
                shutil.copyfileobj(src, dst, 1 << 22)
            os.remove(tar)
        h = hashlib.sha256()
        with open(xz, "rb") as f:
            for blk in iter(lambda: f.read(1 << 22), b""):
                h.update(blk)
        with open(xz + ".sha256", "w") as f:
            f.write(f"{h.hexdigest()}  {os.path.basename(xz)}\n")
        print(f"   {os.path.basename(xz)}: {os.path.getsize(xz) / 1e9:.2f} GB", flush=True)
        out.append(xz)
    return out


def mirrors():
    """Mirror folders of the catalog archives: env PYSYZYGOS_CATALOG_MIRROR (comma-separated) first, then urls.py."""
    env = [m.strip() for m in os.environ.get("PYSYZYGOS_CATALOG_MIRROR", "").split(",") if m.strip()]
    return [m if m.endswith("/") else m + "/" for m in env + list(getattr(U, "URL_CATALOG_MIRRORS", []))]


def _remote_size(url, timeout=30):
    """Size of a remote file (bytes) from a 1-byte range request, or None (also: file:// paths)."""
    if url.startswith("file://"):
        p = url[len("file://"):]
        return os.path.getsize(p) if os.path.isfile(p) else None
    import requests
    try:
        with requests.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=timeout) as r:
            if r.status_code == 206 and "/" in r.headers.get("Content-Range", ""):
                return int(r.headers["Content-Range"].rsplit("/", 1)[1])
            if r.status_code == 200 and r.headers.get("Content-Length"):
                return int(r.headers["Content-Length"])
    except (requests.RequestException, ValueError):
        pass
    return None


def _probe(url, nbytes=4 << 20, timeout=20):
    """Download speed of a source (bytes/s) from its first nbytes; 0 when it does not answer."""
    if url.startswith("file://"):
        return float("inf") if os.path.isfile(url[len("file://"):]) else 0.0
    import requests
    t0, got = time.time(), 0
    try:
        with requests.get(url, headers={"Range": f"bytes=0-{nbytes - 1}"}, stream=True, timeout=timeout) as r:
            if r.status_code not in (200, 206):
                return 0.0
            for c in r.iter_content(1 << 16):
                got += len(c)
                if got >= nbytes or time.time() - t0 > timeout:
                    break
    except requests.RequestException:
        return 0.0
    return got / max(time.time() - t0, 1e-3)


def sources(name, files=None, mirror_list=None):
    """[(label, url, size)] of the places that have this archive, fastest first, and the SHA-256 to expect: the stored
    one (ARCHIVE_SHA256), else Zenodo's .sha256, else the first mirror's. files: {name: (size, url)} stands in for
    Zenodo's listing (tests); mirror_list for mirrors()."""
    from pysyzygos import gaia_local as GL
    found, sha_zen = [], None
    try:
        fl = files if files is not None else GL.zenodo_files(None, name)
        if name in fl:
            found.append(("Zenodo " + GL.ZENODO_DOI, fl[name][1], fl[name][0]))
            if name + ".sha256" in fl:
                sha_zen = _get_text(fl[name + ".sha256"][1]).split()[0].lower()
    except SystemExit:                                            # not (yet) in the newest Zenodo version
        print(f"   Zenodo: no {name} there (yet); trying the mirrors", flush=True)
    except (OSError, ValueError, KeyError) as e:                  # Zenodo unreachable
        print(f"   Zenodo: no answer ({str(e)[:80]}); trying the mirrors", flush=True)
    for m in (mirrors() if mirror_list is None else mirror_list):
        size = _remote_size(m + name)
        if size:
            host = m.split("/")[2] if m.startswith(("http://", "https://")) else "(local folder)"
            found.append((f"mirror {host}", m + name, size))
    stored = ARCHIVE_SHA256.get(name)
    expect = sha_zen or (stored[1] if stored else None)
    if expect is None:
        for label, url, _ in found:
            if label.startswith("mirror"):
                try:
                    expect = _get_text(url + ".sha256").split()[0].lower()
                    break
                except Exception:
                    continue
    if stored and stored[0] and found:
        found = [f for f in found if f[2] == stored[0] or (sha_zen and sha_zen != stored[1])]
    speed = {url: _probe(url) for _, url, _ in found} if len(found) > 1 else {}
    found.sort(key=lambda f: -speed.get(f[1], 0.0))
    for label, url, _ in found:
        if url in speed:
            print(f"   {label}: {speed[url] / 1e6:.1f} MB/s" if speed[url] != float("inf") else f"   {label}: local",
                  flush=True)
    return found, expect


def fetch(d, gmax=16.0, groups=("quality",), keep_archive=False, files=None, mirror_list=None):
    """Install the ready-made catalog (core) and the optional groups into d: from the fastest of Zenodo and the mirrors
    (sources), resumable (a partial download continues from another source if one fails), SHA-256 checked. A complete
    core is kept; groups already there are skipped. files / mirror_list stand in for Zenodo / mirrors() (tests).
    Returns status(d)."""
    from pysyzygos import gaia_local as GL
    if float(gmax) not in ZENODO_STEM:
        sys.exit(f"the ready-made catalog is for G <= {', '.join(f'{g:g}' for g in ZENODO_STEM)} only, not {gmax:g}; "
                 f"build it from ESA's files instead")
    want = (["core"] if not is_format2(d) else []) + [g for g in groups
                                                      if not (is_format2(d) and group_ok(d, g))]
    for g in want:
        name = archive_name(gmax, g)
        found, expect = sources(name, files, mirror_list)
        if not found or not expect:
            sys.exit(f"{name}: not found on Zenodo nor on a mirror (offline?); rerun later, or build from ESA's files "
                     f"(--source esa)")
        size = found[0][2]
        archive = os.path.join(os.path.dirname(os.path.abspath(d)), name)
        free = shutil.disk_usage(os.path.dirname(archive)).free
        if free < 2.4 * size:
            sys.exit(f"not enough disk space next to {d}: {2.4 * size / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free")
        print(f"   {name}, {size / 1e9:.2f} GB ({GROUP_TEXT[g]})", flush=True)
        if not os.path.isfile(archive):
            for k, (label, url, _) in enumerate(found):
                print(f"   from {label}", flush=True)
                try:
                    GL._fetch_resume(url, size, archive + ".part")
                    break
                except Exception as e:                           # this source failed: the next one resumes the .part
                    if k == len(found) - 1:
                        raise
                    print(f"   {label} failed ({str(e)[:100]}); trying the next source", flush=True)
            if GL._sha256(archive + ".part") != expect:
                os.remove(archive + ".part")
                sys.exit(f"{name}: SHA-256 mismatch (corrupt download, deleted); rerun to download again")
            GL.replace_file(archive + ".part", archive)
        elif GL._sha256(archive) != expect:
            sys.exit(f"{archive} exists but its SHA-256 does not match; delete it and rerun")
        GL.unpack_archive(archive, d, need="catalog.json" if g == "core" else f"{g}.json")
        if g != "core" and not group_ok(d, g):
            remove_group(d, g)
            sys.exit(f"{name} does not belong to the catalog in {d} (another build): download the core again")
        if not keep_archive:
            os.remove(archive)
    return status(d)


def _get_text(url):
    if url.startswith("file://"):
        with open(url[len("file://"):]) as f:
            return f.read()
    import requests
    return requests.get(url, timeout=60).text


def add_group(d, g, keep_archive=False):
    """Add an optional group to catalog d: from Zenodo when d is the published build (same build id), else it needs a
    new build (the ESA build writes every group: rebuild without removing it)."""
    if g not in GROUPS:
        raise ValueError(f"unknown part {g!r}: {', '.join(GROUPS)}")
    if group_ok(d, g):
        print(f"{d}: {g} already there")
        return status(d)
    gmax = float(_manifest(d)["gmax"])
    if gmax not in ZENODO_STEM:
        sys.exit(f"{d} was built from ESA's files (G <= {gmax:g}); its {g} part comes only with a new build "
                 f"(pysyzygos catalog build writes all parts)")
    return fetch(d, gmax, (g,), keep_archive)


# ----------------------------------------------------------------------------------------------- upgrade
def staging_dir(d):
    return os.path.normpath(d) + ".new"


def swap_in(d):
    """Move the finished new catalog d.new to d; an old catalog in d goes to d.old (deleted by the caller or the user
    when it is not needed). Returns the old folder or None."""
    from pysyzygos import gaia_local as GL
    new, old = staging_dir(d), os.path.normpath(d) + ".old"
    if not is_format2(new):
        raise RuntimeError(f"{new} holds no finished catalog")
    moved = None
    if os.path.exists(d):
        if os.path.exists(old):
            shutil.rmtree(old)
        GL.replace_file(d, old)
        moved = old
    GL.replace_file(new, d)
    return moved


def main(argv=None):
    from pysyzygos import gaia_local as GL
    d0, g0 = GL.default_dir()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"PySyzygos {__version__}")
    ap.add_argument("cmd", choices=["build", "fetch", "add", "remove", "status", "xmatch", "pack"])
    ap.add_argument("group", nargs="?", help="add/remove: quality or extras")
    ap.add_argument("--dir", default=d0 or "gaia_dr3_g16", help="catalog folder (default: config gaia_local_dir)")
    ap.add_argument("--gmax", type=float, default=None,
                    help="build: faintest G (default: config gaia_local_gmax or 16); fetch: 16 (the ready-made one)")
    ap.add_argument("--workers", type=int, default=6, help="build: parallel downloads")
    ap.add_argument("--groups", default="quality", help="fetch: optional parts, comma-separated (quality,extras; "
                                                        "'none' for the core only)")
    ap.add_argument("--no-xmatch", action="store_true", help="build: leave the 2-parameter stars without proper motion")
    ap.add_argument("--keep-archive", action="store_true")
    ap.add_argument("--mirror", help="fetch/add: another folder address with the archives (as env "
                                     "PYSYZYGOS_CATALOG_MIRROR)")
    ap.add_argument("--out", default="release", help="pack: folder for the archives")
    a = ap.parse_args(argv)
    groups = [] if a.groups.strip().lower() in ("", "none", "core") else [g.strip() for g in a.groups.split(",")]
    if a.mirror:
        os.environ["PYSYZYGOS_CATALOG_MIRROR"] = a.mirror
    if a.cmd == "build":
        st = build(a.dir, g0 if a.gmax is None else a.gmax, a.workers)
        if st["complete"] and not a.no_xmatch and not (st.get("pm_xmatch") or {}):
            xmatch(a.dir)
    elif a.cmd == "fetch":
        fetch(a.dir, 16.0 if a.gmax is None else a.gmax, groups, a.keep_archive)
    elif a.cmd == "add":
        add_group(a.dir, a.group, a.keep_archive)
    elif a.cmd == "remove":
        remove_group(a.dir, a.group)
    elif a.cmd == "xmatch":
        xmatch(a.dir)
    elif a.cmd == "pack":
        pack(a.dir, a.out)
    print(json.dumps(status(a.dir)))


if __name__ == "__main__":
    sys.exit(main())
