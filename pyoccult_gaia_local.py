#!.venv/bin/python3
"""pyoccult_gaia_local.py - local, magnitude-limited copy of Gaia DR3 for the corridor search.

Why: the Gaia archive (TAP) can take many minutes per strip query or hang. The full gaia_source table is on ESA's CDN as
3386 gzipped CSV files (753 GB). This tool streams them once, keeps only what the search needs (G <= gmax, 5-parameter
astrometry, ruwe < 1.4; 7 columns as binary, ~40 bytes/star, about 19 GB for G <= 18), and deletes each download.
Afterwards a corridor lookup reads only the few files its strip touches, in about a second, without network.

    python pyoccult_gaia_local.py build                 # dir and gmax from pyoccult_config (gaia_local_dir, gaia_local_gmax)
    python pyoccult_gaia_local.py build --workers 6     # resumable: rerun after an interruption, finished files are skipped
    python pyoccult_gaia_local.py status
    python pyoccult_gaia_local.py zenodo --gmax 16    # ready-made copy (G <= 16 or 18) from Zenodo instead of building

Layout of the catalog folder:
    catalog.json                      gmax, cuts and the list of source files (written first)
    GaiaSource_xxxxxx-yyyyyy.npy      the kept stars of one source file, structured array DTYPE, sorted by source_id
    GaiaSource_xxxxxx-yyyyyy.cells.npy  1x1 deg sky cells that file has stars in (the lookup index)
    GaiaSource_xxxxxx-yyyyyy.hpm.npy  its stars with proper motion > HIGH_PM_MAS (they can leave the strip pad)
The .npy of a file is written last, atomically; its presence means that file is done.

Network only (no SPICE), so the build uses processes freely. Standard library + numpy, pandas, requests.
"""
from pyoccult_version import __version__
import pyoccult_urls as U
import argparse, json, math, os, re, shutil, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd

BUCKET = U.URL_GAIA_DR3_LISTING                                       # S3-style listing behind the CDN (pyoccult_urls)
PREFIX = U.GAIA_DR3_LISTING_PREFIX
COLS = ["source_id", "ra", "dec", "parallax", "pmra", "pmdec", "phot_g_mean_mag"]
DTYPE = np.dtype([("source_id", "<i8"), ("ra", "<f8"), ("dec", "<f8"), ("parallax", "<f4"),
                  ("pmra", "<f4"), ("pmdec", "<f4"), ("phot_g_mean_mag", "<f4")])
HIGH_PM_MAS = 1500.0                                                  # must match the corridor pm pad (pm_pad_mas)
RUWE_MAX = 1.4


class Progress:
    """Progress of a long step, so it never looks stuck: in a terminal one line rewritten in place (about once a
    second), else (log file, nohup) a new line every 30 s. p(done, note) updates, p.finish(text) ends it."""

    def __init__(self, label, total, fmt=lambda x: f"{x / 1e9:.2f} GB", rate=lambda r: f"{r / 1e6:.1f} MB/s", start=0):
        self.label, self.total, self.fmt, self.rate, self.start = label, max(total, 1), fmt, rate, start
        self.tty = sys.stdout.isatty()
        self.every = 1.0 if self.tty else 30.0
        self.t0 = self.last = time.time()
        self.width = 0

    def _out(self, text, end=False):
        if self.tty:
            print("\r" + text.ljust(self.width), end="\n" if end else "", flush=True)
            self.width = 0 if end else len(text)
        else:
            print(text, flush=True)

    def __call__(self, done, note="", force=False):
        now = time.time()
        if not force and now - self.last < self.every:
            return
        self.last = now
        el = max(now - self.t0, 1e-3)
        r = (done - self.start) / el
        eta = (self.total - done) / r if r > 0 else float("nan")
        eta_s = "?" if eta != eta else (f"{eta / 3600:.0f} h {eta % 3600 / 60:02.0f} min" if eta >= 3600
                                        else f"{eta // 60:.0f} min {eta % 60:02.0f} s")
        self._out(f"   {self.label}: {self.fmt(done)} of {self.fmt(self.total)} ({100 * done / self.total:.0f} %), "
                  f"{self.rate(r)}, ETA {eta_s}{note}")

    def finish(self, text):
        self._out(f"   {self.label}: {text} in {(time.time() - self.t0) / 60:.1f} min", end=True)


# ----------------------------------------------------------------------------------------------- sky cells
def cell_of(ra_deg, dec_deg, size=1.0):
    """Plain ra/dec grid of size x size deg: cell = dec_band * n_ra + ra_band (n_ra = 360/size)."""
    n_dec, n_ra = int(round(180 / size)), int(round(360 / size))
    di = np.clip(np.floor((np.asarray(dec_deg, float) + 90.0) / size), 0, n_dec - 1).astype(np.int64)
    ri = (np.floor((np.asarray(ra_deg, float) % 360.0) / size).astype(np.int64)) % n_ra
    return di * n_ra + ri


def cells_near(ra_deg, dec_deg, w_deg, size=1.0):
    """All cells within w_deg (per point) of the points (a numpy array). The box ra +/- w/cos(dec), dec +/- w around
    each point is probed at steps below one cell, so no cell is skipped; near a pole the whole dec band is taken."""
    n_dec, n_ra = int(round(180 / size)), int(round(360 / size))
    ra, dec, w = np.broadcast_arrays(*(np.atleast_1d(np.asarray(x, float)) for x in (ra_deg, dec_deg, w_deg)))
    out = []
    kd = int(np.ceil(w.max() / (0.5 * size))) if len(w) else 1
    for fd in np.linspace(-1, 1, 2 * kd + 1):
        d = np.clip(dec + fd * w, -90, 90)
        cosd = np.cos(np.radians(np.minimum(np.abs(d) + w, 90.0)))
        wr = np.where(cosd > 0.02, w / np.maximum(cosd, 0.02), 360.0)
        polar = wr >= 180.0
        ok = ~polar
        if ok.any():
            kr = int(np.ceil(wr[ok].max() / (0.5 * size)))
            for fr in np.linspace(-1, 1, 2 * kr + 1):
                out.append(cell_of(ra[ok] + fr * wr[ok], d[ok], size))
        for di in np.unique(np.clip(np.floor((d[polar] + 90.0) / size), 0, n_dec - 1).astype(np.int64)):
            out.append(np.arange(di * n_ra, di * n_ra + n_ra))
    return np.unique(np.concatenate(out)) if out else np.empty(0, np.int64)


def near_path_mask(S, U, w_deg, chunk_deg=0.05):
    """Boolean mask of the unit vectors S (n,3) within w_deg (per path sample) of the path U (m,3): coarse discs per
    path chunk (<= chunk_deg long), a superset of the exact strip (the candidate scan does the exact test)."""
    ang = np.degrees(np.arccos(np.clip(np.sum(U[:-1] * U[1:], axis=1), -1, 1)))
    cum = np.concatenate(([0.0], np.cumsum(ang)))
    edges = np.unique(np.concatenate((np.searchsorted(cum, np.arange(0, cum[-1], chunk_deg)), [len(U) - 1])))
    C, cosr = [], []
    for i0, i1 in zip(edges[:-1], edges[1:]):
        c = U[i0:i1 + 1].mean(axis=0)
        c /= np.linalg.norm(c)
        r = np.degrees(np.arccos(np.clip(U[i0:i1 + 1] @ c, -1, 1))).max() + 1.2 * w_deg[i0:i1 + 1].max()
        C.append(c); cosr.append(math.cos(math.radians(r)))
    if not C:
        C, cosr = [U[0]], [math.cos(math.radians(1.2 * w_deg[0]))]
    C, cosr = np.array(C), np.array(cosr)
    keep = np.zeros(len(S), bool)
    for k in range(0, len(C), 64):                                                   # (stars x discs) in blocks
        keep |= ((S @ C[k:k + 64].T) >= cosr[None, k:k + 64]).any(axis=1)
    return keep


# ----------------------------------------------------------------------------------------------- build
def list_files(timeout=90):
    """[(file name, size bytes)] of gaia_source on the CDN (paged S3 listing)."""
    import requests
    out, marker = [], None
    while True:
        p = dict(prefix=PREFIX, delimiter="/")
        if marker:
            p["marker"] = marker
        r = requests.get(BUCKET, params=p, timeout=timeout)
        r.raise_for_status()
        t = r.text
        ks = re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", t, re.S)
        out += [(k.rsplit("/", 1)[1], int(s)) for k, s in ks]
        if "<IsTruncated>true" in t and ks:
            marker = ks[-1][0]
        else:
            files = [(n, s) for n, s in out if n.startswith("GaiaSource_") and n.endswith(".csv.gz")]
            if not files:                     # e.g. a proxy's or portal's page instead of the listing
                raise RuntimeError(f"no Gaia source files in the listing at {BUCKET} (got {len(t)} bytes that are "
                                   f"not the file list: blocked by a proxy or firewall?)")
            return files


def _download(name, dst, tries=4):
    import requests
    for k in range(tries):
        try:
            with requests.get(U.URL_GAIA_DR3_FILES + name, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dst, "wb") as f:
                    for c in r.iter_content(1 << 20):
                        f.write(c)
            return
        except Exception as e:
            if k == tries - 1:
                raise
            print(f"  retry {name}: {str(e)[:100]}", flush=True)
            time.sleep(10 * (k + 1))


def _save_atomic(path, arr):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        np.save(f, arr)
    os.replace(tmp, path)


def process_file(name, out_dir, gmax, ruwe_max=RUWE_MAX):
    """Download one source file, keep the useful stars, write .cells/.hpm then the .npy (done marker). Returns stats."""
    stem = name[:-len(".csv.gz")]
    final = os.path.join(out_dir, stem + ".npy")
    if os.path.isfile(final):
        return name, None, None, 0.0
    t0 = time.time()
    fd, gz = tempfile.mkstemp(dir=out_dir, suffix=".csv.gz.tmp")
    os.close(fd)
    try:
        _download(name, gz)
        df = pd.read_csv(gz, compression="gzip", comment="#", usecols=COLS + ["ruwe"], na_values=["null"])
    finally:
        os.remove(gz)
    n_in = len(df)
    df = df[(df.phot_g_mean_mag <= gmax) & df.pmra.notna() & df.parallax.notna() & (df.ruwe < ruwe_max)]
    arr = np.empty(len(df), DTYPE)
    for c in COLS:
        arr[c] = df[c].to_numpy()
    arr.sort(order="source_id")
    _save_atomic(os.path.join(out_dir, stem + ".cells.npy"), np.unique(cell_of(arr["ra"], arr["dec"])))
    pm = np.hypot(arr["pmra"].astype(float), arr["pmdec"].astype(float))
    _save_atomic(os.path.join(out_dir, stem + ".hpm.npy"), arr[pm > HIGH_PM_MAS])
    _save_atomic(final, arr)
    return name, n_in, len(arr), time.time() - t0


def build(out_dir, gmax=18.0, workers=6):
    os.makedirs(out_dir, exist_ok=True)
    man_path = os.path.join(out_dir, "catalog.json")
    print("listing ESA's Gaia DR3 files ...", flush=True)
    files = list_files()
    if os.path.isfile(man_path):
        man = json.load(open(man_path))
        if abs(man["gmax"] - gmax) > 1e-9 or man["ruwe_max"] != RUWE_MAX:
            sys.exit(f"{out_dir} holds a catalog with gmax {man['gmax']}, ruwe < {man['ruwe_max']}; use another folder")
    man = dict(gmax=gmax, ruwe_max=RUWE_MAX, high_pm_mas=HIGH_PM_MAS, source=U.URL_GAIA_DR3_FILES,
               files=[n for n, _ in files], created=time.strftime("%Y-%m-%d %H:%M:%S"))
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(man, f, indent=1)
    os.replace(tmp, man_path)
    for t in os.listdir(out_dir):                                       # leftovers of an interrupted run
        if t.endswith(".tmp"):
            os.remove(os.path.join(out_dir, t))
    todo = [n for n, _ in files if not os.path.isfile(os.path.join(out_dir, n[:-len(".csv.gz")] + ".npy"))]
    total_gb = sum(s for n, s in files if n in set(todo)) / 1e9
    print(f"{len(files)} source files, {len(todo)} to do ({total_gb:.0f} GB to download), G <= {gmax}, {workers} workers",
          flush=True)
    t0, done, kept, seen, failed = time.time(), 0, 0, 0, []
    ex = ProcessPoolExecutor(max_workers=workers) if workers > 0 else None       # workers <= 0: serial (tests)
    futs = {ex.submit(process_file, n, out_dir, gmax): n for n in todo} if ex else {}
    prog = Progress("ESA build", len(todo), fmt=lambda x: f"{x:.0f} files", rate=lambda r: f"{r * 60:.1f} files/min")
    prog(0, " (first files take a minute or two)", force=True)
    stream = ((n, None) for n in todo) if ex is None else ((futs[f], f) for f in as_completed(futs))
    try:
        for name, fut in stream:
            try:
                _, n_in, n_keep, dt = process_file(name, out_dir, gmax) if fut is None else fut.result()
            except Exception as e:                  # this file failed after its retries: go on, a rerun resumes it
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
            prog(done, f", {kept/1e6:.1f} M of {seen/1e6:.1f} M stars kept", force=done == len(todo))
    finally:
        if ex is not None:
            ex.shutdown(cancel_futures=True)
    if todo:
        prog.finish(f"{done - len(failed)} files, {kept/1e6:.1f} M stars kept")
    st = status(out_dir)
    print(f"done: {st['done']}/{st['total']} files, {st['gb']:.1f} GB")
    if failed:
        print(f"{len(failed)} files failed (network); rerun setup to fetch just those (it resumes)")
    if st["complete"]:
        BrightIndex(out_dir, 15.0)                                           # for pyoccult_pick.py


# ----------------------------------------------------------------------------------------------- ready-made copy
ZENODO_DOI = "10.5281/zenodo.23113337"                               # concept DOI: always the newest version
ZENODO_API = U.URL_ZENODO_CATALOG_RECORD
ZENODO_GMAX = (16.0, 18.0)                                            # limits published there (gaia_dr3_g16, gaia_dr3_g18)


def zenodo_files(gmax):
    """{name: (size, url)} of the archive for this limit and its .sha256 in the newest Zenodo version."""
    import requests
    stem = f"gaia_dr3_g{gmax:g}.tar.xz"
    r = requests.get(ZENODO_API, timeout=60)
    r.raise_for_status()
    files = {f["key"]: (f["size"], f["links"]["self"]) for f in r.json()["files"]}
    if stem not in files or stem + ".sha256" not in files:
        sys.exit(f"Zenodo record {ZENODO_DOI} has no {stem}; build from ESA instead")
    return {k: files[k] for k in (stem, stem + ".sha256")}


def _fetch_resume(url, size, dst, tries=6):
    """Download url to dst (resumes a partial dst with an HTTP Range request); progress every ~5 %."""
    import requests
    for k in range(tries):
        have = os.path.getsize(dst) if os.path.isfile(dst) else 0
        if have >= size:
            return
        try:
            hdr = {"Range": f"bytes={have}-"} if have else {}
            with requests.get(url, stream=True, timeout=120, headers=hdr) as r:
                r.raise_for_status()
                if have and r.status_code != 206:                            # server ignored the Range: start over
                    have = 0
                got = 0
                prog = Progress("download", size, start=have)
                prog(have, " (resumed)" if have else " (starting)", force=True)
                with open(dst, "ab" if have else "wb") as f:
                    for c in r.iter_content(1 << 20):
                        f.write(c)
                        got += len(c)
                        prog(have + got)
                prog.finish(f"{(have + got) / 1e9:.2f} GB")
            if os.path.getsize(dst) >= size:
                return
        except Exception as e:
            if k == tries - 1:
                raise
            print(f"   retry: {str(e)[:100]}", flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError(f"download of {url} incomplete after {tries} tries; rerun to resume")


def _sha256(path):
    import hashlib
    h, done = hashlib.sha256(), 0
    prog = Progress("SHA-256 check", os.path.getsize(path))
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 22), b""):
            h.update(c)
            done += len(c)
            prog(done)
    prog.finish("done")
    return h.hexdigest()


def unpack_archive(archive, out_dir):
    """Unpack a catalog .tar.xz (one top folder, any name) into out_dir. Unpacks into out_dir.unpack first, then moves
    the files over (overwriting a partial build of the same limit), so an interruption leaves no half-written files."""
    import tarfile
    stage = os.path.abspath(out_dir) + ".unpack"
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    n = 0
    prog = Progress(f"unpack into {out_dir}", os.path.getsize(archive), fmt=lambda x: f"{x / 1e9:.2f} GB", rate=lambda r: f"{r / 1e6:.1f} MB/s")
    with open(archive, "rb") as raw, tarfile.open(fileobj=raw, mode="r|xz") as tf:   # streaming: one pass, low memory
        for m in tf:
            prog(raw.tell(), f", {n} files")
            parts = m.name.replace("\\", "/").split("/")[1:]            # drop the archive's own top folder
            if not m.isfile() or not parts or os.path.isabs(m.name) or ".." in parts:
                continue
            m.name = "/".join(parts)
            try:
                tf.extract(m, stage, filter="data")
            except TypeError:                                            # Python without extraction filters
                tf.extract(m, stage)
            n += 1
    prog.finish(f"{n} files")
    if not os.path.isfile(os.path.join(stage, "catalog.json")):
        sys.exit(f"{archive} holds no catalog.json: not a PyOccult catalog archive")
    os.makedirs(out_dir, exist_ok=True)
    for f in sorted(os.listdir(stage), key=lambda f: f == "catalog.json"):   # catalog.json last
        os.replace(os.path.join(stage, f), os.path.join(out_dir, f))
    os.rmdir(stage)


def fetch_zenodo(out_dir, gmax=18.0, keep_archive=False):
    """Install the ready-made catalog for G <= gmax (16 or 18) from Zenodo instead of building it: download (resumable),
    check the SHA-256, unpack into out_dir. The archive goes next to out_dir and is deleted afterwards unless
    keep_archive. No bright-star index inside: BrightIndex(out_dir) builds it."""
    import requests
    if float(gmax) not in ZENODO_GMAX:
        sys.exit(f"Zenodo has catalogs for G <= {', '.join(f'{g:g}' for g in ZENODO_GMAX)} only, not {gmax:g}; "
                 f"build from ESA instead")
    files = zenodo_files(gmax)
    (name, (size, url)), (sha_name, (_, sha_url)) = files.items()
    archive = os.path.join(os.path.dirname(os.path.abspath(out_dir)), name)
    need = (0 if os.path.isfile(archive) else size - (os.path.getsize(archive + ".part")
                                                     if os.path.isfile(archive + ".part") else 0)) + 1.4 * size
    free = shutil.disk_usage(os.path.dirname(archive)).free
    if free < need:
        sys.exit(f"not enough disk space next to {out_dir}: {need / 1e9:.1f} GB needed (archive + unpacked), "
                 f"{free / 1e9:.1f} GB free")
    want = requests.get(sha_url, timeout=60).text.split()[0].lower()
    print(f"   Zenodo {ZENODO_DOI}: {name}, {size / 1e9:.1f} GB", flush=True)
    if not os.path.isfile(archive):
        _fetch_resume(url, size, archive + ".part")
        if _sha256(archive + ".part") != want:
            os.remove(archive + ".part")
            sys.exit(f"{name}: SHA-256 mismatch (corrupt download, deleted); rerun to download again")
        os.replace(archive + ".part", archive)
    elif _sha256(archive) != want:
        sys.exit(f"{archive} exists but its SHA-256 does not match Zenodo's; delete it and rerun")
    unpack_archive(archive, out_dir)
    if not keep_archive:
        os.remove(archive)
    st = status(out_dir)
    print(f"   done: {st['done']}/{st['total']} files, {st['gb']:.1f} GB" + ("" if keep_archive else
                                                                          f"; {name} deleted"), flush=True)
    return st


def find_catalogs(root="."):
    """Local catalogs in the sub-folders of root: list of (folder, gmax, complete, gb), brightest limit first."""
    out = []
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if os.path.isfile(os.path.join(p, "catalog.json")):
            st = status(p)
            out.append((d, st.get("gmax"), st["complete"], st["gb"]))
    return sorted(out, key=lambda c: (c[1] if c[1] is not None else 99, c[0]))


def status(out_dir):
    man_path = os.path.join(out_dir, "catalog.json")
    if not os.path.isfile(man_path):
        return dict(total=0, done=0, gb=0.0, complete=False)
    man = json.load(open(man_path))
    have = {f for f in os.listdir(out_dir) if f.endswith(".npy") and f.count(".") == 1}
    done = sum((n[:-len(".csv.gz")] + ".npy") in have for n in man["files"])
    gb = sum(os.path.getsize(os.path.join(out_dir, f)) for f in have) / 1e9
    return dict(total=len(man["files"]), done=done, gb=gb, complete=done == len(man["files"]), gmax=man["gmax"])


# ----------------------------------------------------------------------------------------------- lookup
class LocalGaia:
    """Read side. LocalGaia(dir).corridor_stars(plan) -> DataFrame like the archive query (epoch 2016.0)."""

    def __init__(self, out_dir, allow_partial=False):
        self.dir = out_dir
        man = json.load(open(os.path.join(out_dir, "catalog.json")))
        self.gmax = man["gmax"]
        st = status(out_dir)
        if not st["complete"] and not allow_partial:
            raise RuntimeError(f"local Gaia catalog in {out_dir} is incomplete ({st['done']}/{st['total']} files); "
                               f"run: python pyoccult_setup.py  (resumes)")
        self.stems = [n[:-len(".csv.gz")] for n in man["files"]
                      if os.path.isfile(os.path.join(out_dir, n[:-len(".csv.gz")] + ".npy"))]
        self.by_cell = {}
        for i, s in enumerate(self.stems):
            for c in np.load(os.path.join(out_dir, s + ".cells.npy")).tolist():
                self.by_cell.setdefault(c, []).append(i)
        self._hpm = None

    def high_pm(self):
        if self._hpm is None:
            self._hpm = np.concatenate([np.load(os.path.join(self.dir, s + ".hpm.npy")) for s in self.stems] or
                                       [np.empty(0, DTYPE)])
        return self._hpm

    def cone(self, ra_deg, dec_deg, radius_deg, mag_cap=None):
        """Stars (DataFrame, epoch 2016.0) within radius_deg of (ra, dec), G <= mag_cap. For small fields (previews)."""
        from pyoccult_corridor import _unit
        cap = self.gmax if mag_cap is None else min(mag_cap, self.gmax)
        c = _unit(ra_deg, dec_deg)
        files = sorted({i for k in cells_near([ra_deg], [dec_deg], [radius_deg]).tolist() for i in self.by_cell.get(k, ())})
        parts = []
        for i in files:
            a = np.load(os.path.join(self.dir, self.stems[i] + ".npy"), mmap_mode="r")
            a = a[a["phot_g_mean_mag"] <= cap]
            if len(a):
                parts.append(np.asarray(a[_unit(a["ra"], a["dec"]) @ c >= math.cos(math.radians(radius_deg))]))
        arr = np.concatenate(parts) if parts else np.empty(0, DTYPE)
        return pd.DataFrame({k: arr[k].astype(np.float64) if k != "source_id" else arr[k] for k in COLS})

    def corridor_stars(self, plan, include_high_pm=True, chunk_deg=0.05):
        """Stars (G <= plan mag_cap) within margin_km/distance + pad of the plan's path, plus the high-pm stars."""
        from pyoccult_corridor import _radec, _unit
        path = plan["path"]
        U, D = path["u"], path["delta_km"]
        w = np.degrees(plan["margin_km"] / D) + plan["pad_arcsec"] / 3600.0              # half-width per sample, deg
        cap = plan["mag_cap"]
        if cap > self.gmax + 1e-9:
            print(f"{plan['target']}: magnitude cap {cap:.1f} is fainter than the local catalog (G <= {self.gmax}); using {self.gmax}")
        ra, dec = _radec(U)
        files = sorted({i for c in cells_near(ra, dec, 1.5 * w).tolist() for i in self.by_cell.get(c, ())})
        parts = []
        for i in files:
            a = np.load(os.path.join(self.dir, self.stems[i] + ".npy"), mmap_mode="r")
            a = a[a["phot_g_mean_mag"] <= cap]
            if len(a):
                parts.append(np.asarray(a[near_path_mask(_unit(a["ra"], a["dec"]), U, w, chunk_deg)]))
        if include_high_pm:
            h = self.high_pm()
            parts.append(h[h["phot_g_mean_mag"] <= cap])
        arr = np.concatenate(parts) if parts else np.empty(0, DTYPE)
        df = pd.DataFrame({c: arr[c].astype(np.float64) if c != "source_id" else arr[c] for c in COLS})
        return df.drop_duplicates("source_id").reset_index(drop=True)


def index_gmax(mag_limit):
    """Limit of the bright-star index serving a magnitude limit: whole magnitudes, at least 15, so changing the
    aperture does not build a new index every time."""
    return max(15.0, float(math.ceil(mag_limit - 1e-9)))


class BrightIndex:
    """Stars with G <= gmax (default 15, ~32 M stars, 1.3 GB) from the local catalog, sorted by a fine sky cell and,
    within a cell, by magnitude (so a lookup with a bright cap reads only the bright end of each cell). For screening many
    asteroids at once (pyoccult_screen.py). Built once from the catalog (~15 s) and saved next to it as
    bright_G<gmax>.v2.npy + .v2.offsets.npy; opened memory-mapped."""
    CELL = 0.25                                                                       # deg

    def __init__(self, catalog_dir, gmax=15.0):
        self.dir, self.gmax = catalog_dir, float(gmax)
        stem = os.path.join(catalog_dir, f"bright_G{self.gmax:.1f}.v2")
        if not (os.path.isfile(stem + ".npy") and os.path.isfile(stem + ".offsets.npy")):
            self._build(stem)
        self.stars = np.load(stem + ".npy", mmap_mode="r")
        self.offsets = np.load(stem + ".offsets.npy")

    def _build(self, stem):
        man = json.load(open(os.path.join(self.dir, "catalog.json")))
        if man["gmax"] < self.gmax:
            raise ValueError(f"local catalog goes to G {man['gmax']}, cannot index G <= {self.gmax}")
        if not status(self.dir)["complete"]:
            raise RuntimeError(f"local Gaia catalog in {self.dir} is incomplete; run: python pyoccult_setup.py")
        # Low-memory build (any limit, any RAM): 1) count stars per cell, 2) write each file's stars into their cell's
        # slots of a memory-mapped output, 3) sort each cell by G, a block of cells at a time. Peak memory: one source
        # file's selection or one block, not the whole index (a G <= 16 index is ~3.7 GB, G <= 18 ~11 GB).
        t0 = time.time()
        files = [os.path.join(self.dir, n[:-len(".csv.gz")] + ".npy") for n in man["files"]]
        n_cells = int(round(180 / self.CELL)) * int(round(360 / self.CELL))
        counts, dtype = np.zeros(n_cells, np.int64), None
        prog = Progress(f"bright-star index G <= {self.gmax:g}", 2 * len(files), fmt=lambda x: f"{x:.0f} file reads",
                        rate=lambda r: f"{r:.0f} files/s")

        def selected(path):
            a = np.load(path, mmap_mode="r")
            sel = np.asarray(a[np.asarray(a["phot_g_mean_mag"]) <= self.gmax])
            return sel, cell_of(sel["ra"], sel["dec"], self.CELL)

        for i, f in enumerate(files, 1):
            sel, cell = selected(f)
            counts += np.bincount(cell, minlength=n_cells)
            dtype = sel.dtype
            prog(i)
        offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(stem), suffix=".tmp")
        os.close(fd)
        out = np.lib.format.open_memmap(tmp, mode="w+", dtype=dtype, shape=(int(offsets[-1]),))
        cursor = offsets[:-1].copy()
        for i, f in enumerate(files, 1):
            sel, cell = selected(f)
            order = np.argsort(cell, kind="stable")
            sel, cell = sel[order], cell[order]
            rank = np.arange(len(cell)) - np.searchsorted(cell, cell, side="left")      # place within its cell
            out[cursor[cell] + rank] = sel
            cursor += np.bincount(cell, minlength=n_cells)
            prog(len(files) + i)
        prog.finish("read; sorting by G within cells")
        block, i = 4_000_000, 0
        while i < len(out):
            j = int(offsets[np.searchsorted(offsets, i + block, side="right") - 1])     # end on a cell boundary
            if j <= i:
                j = int(offsets[np.searchsorted(offsets, i, side="right")])           # one cell larger than a block
            blk = np.asarray(out[i:j])
            out[i:j] = blk[np.lexsort((blk["phot_g_mean_mag"], cell_of(blk["ra"], blk["dec"], self.CELL)))]
            i = j
        out.flush()
        n_stars = len(out)
        del out
        _save_atomic(stem + ".offsets.npy", offsets)                  # offsets first: the .npy of the stars marks done
        os.replace(tmp, stem + ".npy")
        print(f"bright-star index G <= {self.gmax}: {n_stars / 1e6:.1f} M stars in {time.time() - t0:.0f} s -> {stem}.npy")

    def near_path(self, U, w_deg, mag_cap=None, sample_deg=None):
        """Stars (structured array) within w_deg (per sample) of the path U (m,3 unit vectors), G <= mag_cap.
        A superset of the exact strip (coarse discs); the candidate scan does the exact test."""
        from pyoccult_corridor import _radec, _unit
        if len(U) == 0:
            return self.stars[:0]
        # cells: path points every ~CELL/5 are enough (the strip is far narrower than a cell)
        ang = np.degrees(np.arccos(np.clip(np.sum(U[:-1] * U[1:], axis=1), -1, 1)))
        cum = np.concatenate(([0.0], np.cumsum(ang)))
        pick = np.unique(np.concatenate((np.searchsorted(cum, np.arange(0, cum[-1], sample_deg or self.CELL / 5)),
                                         [len(U) - 1])))
        ra, dec = _radec(U[pick])
        cells = cells_near(ra, dec, 1.5 * float(np.max(w_deg)) + self.CELL / 5, self.CELL)   # + half the sample spacing
        lo, hi = self.offsets[cells], self.offsets[cells + 1]
        if mag_cap is not None and mag_cap < self.gmax:                    # each cell is sorted by G: cut its tail
            g = self.stars["phot_g_mean_mag"]
            hi = np.array([a + np.searchsorted(g[a:b], mag_cap, "right") for a, b in zip(lo, hi)], np.int64)
        idx = np.concatenate([np.arange(a, b) for a, b in zip(lo, hi) if b > a] or [np.empty(0, np.int64)])
        a = np.asarray(self.stars[idx])
        if len(a) == 0:
            return a
        return a[near_path_mask(_unit(a["ra"], a["dec"]), U, w_deg)]


def default_dir():
    try:
        import pyoccult_config as C
        return getattr(C, "gaia_local_dir", None), getattr(C, "gaia_local_gmax", 18.0)
    except ImportError:
        return None, 18.0


if __name__ == "__main__":
    d0, g0 = default_dir()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"PyOccult {__version__}")
    ap.add_argument("cmd", choices=["build", "status", "zenodo"])
    ap.add_argument("--dir", default=d0 or "gaia_dr3_local", help="catalog folder (default: config gaia_local_dir)")
    ap.add_argument("--gmax", type=float, default=g0, help="faintest G kept (default: config gaia_local_gmax or 18)")
    ap.add_argument("--workers", type=int, default=6, help="parallel download/parse processes")
    ap.add_argument("--keep-archive", action="store_true", help="zenodo: keep the downloaded .tar.xz")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.dir, a.gmax, a.workers)
    elif a.cmd == "zenodo":
        if fetch_zenodo(a.dir, a.gmax, a.keep_archive)["complete"]:
            BrightIndex(a.dir, 15.0)                                         # for pyoccult_pick.py
    else:
        print(status(a.dir))
