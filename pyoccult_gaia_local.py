#!.venv/bin/python3
"""pyoccult_gaia_local.py - local, magnitude-limited copy of Gaia DR3 for the corridor search.

Why: the Gaia archive (TAP) can take many minutes per strip query or hang. The full gaia_source table is on ESA's CDN as
3386 gzipped CSV files (753 GB). This tool streams them once, keeps only what the search needs (G <= gmax, 5-parameter
astrometry, ruwe < 1.4; 7 columns as binary, ~40 bytes/star, about 19 GB for G <= 18), and deletes each download.
Afterwards a corridor lookup reads only the few files its strip touches, in about a second, without network.

    python pyoccult_gaia_local.py build                 # dir and gmax from pyoccult_config (gaia_local_dir, gaia_local_gmax)
    python pyoccult_gaia_local.py build --workers 6     # resumable: rerun after an interruption, finished files are skipped
    python pyoccult_gaia_local.py status

Layout of the catalog folder:
    catalog.json                      gmax, cuts and the list of source files (written first)
    GaiaSource_xxxxxx-yyyyyy.npy      the kept stars of one source file, structured array DTYPE, sorted by source_id
    GaiaSource_xxxxxx-yyyyyy.cells.npy  1x1 deg sky cells that file has stars in (the lookup index)
    GaiaSource_xxxxxx-yyyyyy.hpm.npy  its stars with proper motion > HIGH_PM_MAS (they can leave the strip pad)
The .npy of a file is written last, atomically; its presence means that file is done.

Network only (no SPICE), so the build uses processes freely. Standard library + numpy, pandas, requests.
"""
import argparse, json, math, os, re, sys, tempfile, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd

BUCKET = "https://gaia.eu-1.cdn77-storage.com/"                     # S3-style listing behind cdn.gea.esac.esa.int
CDN = "https://cdn.gea.esac.esa.int/"
PREFIX = "Gaia/gdr3/gaia_source/"
COLS = ["source_id", "ra", "dec", "parallax", "pmra", "pmdec", "phot_g_mean_mag"]
DTYPE = np.dtype([("source_id", "<i8"), ("ra", "<f8"), ("dec", "<f8"), ("parallax", "<f4"),
                  ("pmra", "<f4"), ("pmdec", "<f4"), ("phot_g_mean_mag", "<f4")])
HIGH_PM_MAS = 1500.0                                                  # must match the corridor pm pad (pm_pad_mas)
RUWE_MAX = 1.4


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
        t = requests.get(BUCKET, params=p, timeout=timeout).text
        ks = re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", t, re.S)
        out += [(k.rsplit("/", 1)[1], int(s)) for k, s in ks]
        if "<IsTruncated>true" in t and ks:
            marker = ks[-1][0]
        else:
            return [(n, s) for n, s in out if n.startswith("GaiaSource_") and n.endswith(".csv.gz")]


def _download(name, dst, tries=4):
    import requests
    for k in range(tries):
        try:
            with requests.get(CDN + PREFIX + name, stream=True, timeout=120) as r:
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
    files = list_files()
    if os.path.isfile(man_path):
        man = json.load(open(man_path))
        if abs(man["gmax"] - gmax) > 1e-9 or man["ruwe_max"] != RUWE_MAX:
            sys.exit(f"{out_dir} holds a catalog with gmax {man['gmax']}, ruwe < {man['ruwe_max']}; use another folder")
    man = dict(gmax=gmax, ruwe_max=RUWE_MAX, high_pm_mas=HIGH_PM_MAS, source=CDN + PREFIX,
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
    t0, done, kept, seen = time.time(), 0, 0, 0
    if workers <= 0:                                                    # serial (tests, debugging)
        results = (process_file(n, out_dir, gmax) for n in todo)
    else:
        ex = ProcessPoolExecutor(max_workers=workers)
        results = (f.result() for f in as_completed([ex.submit(process_file, n, out_dir, gmax) for n in todo]))
    for name, n_in, n_keep, dt in results:
        done += 1
        if n_in is not None:
            seen, kept = seen + n_in, kept + n_keep
        if done % 20 == 0 or done == len(todo):
            el = time.time() - t0
            print(f"{done}/{len(todo)} files, {kept/1e6:.1f} M of {seen/1e6:.1f} M stars kept, {el/60:.0f} min, "
                  f"ETA {el/done*(len(todo)-done)/60:.0f} min", flush=True)
    if workers > 0:
        ex.shutdown()
    st = status(out_dir)
    print(f"done: {st['done']}/{st['total']} files, {st['gb']:.1f} GB")
    if st["complete"]:
        BrightIndex(out_dir, 15.0)                                           # for pyoccult_pick.py


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
        t0 = time.time()
        parts = []
        for n in man["files"]:
            a = np.load(os.path.join(self.dir, n[:-len(".csv.gz")] + ".npy"), mmap_mode="r")
            parts.append(np.asarray(a[a["phot_g_mean_mag"] <= self.gmax]))
        arr = np.concatenate(parts)
        cell = cell_of(arr["ra"], arr["dec"], self.CELL)
        order = np.lexsort((arr["phot_g_mean_mag"], cell))                          # by cell, then by G
        arr, cell = arr[order], cell[order]
        n_cells = int(round(180 / self.CELL)) * int(round(360 / self.CELL))
        offsets = np.searchsorted(cell, np.arange(n_cells + 1)).astype(np.int64)
        _save_atomic(stem + ".offsets.npy", offsets)                  # offsets first: the .npy of the stars marks done
        _save_atomic(stem + ".npy", arr)
        print(f"bright-star index G <= {self.gmax}: {len(arr) / 1e6:.1f} M stars in {time.time() - t0:.0f} s -> {stem}.npy")

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
    ap.add_argument("cmd", choices=["build", "status"])
    ap.add_argument("--dir", default=d0 or "gaia_dr3_local", help="catalog folder (default: config gaia_local_dir)")
    ap.add_argument("--gmax", type=float, default=g0, help="faintest G kept (default: config gaia_local_gmax or 18)")
    ap.add_argument("--workers", type=int, default=6, help="parallel download/parse processes")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.dir, a.gmax, a.workers)
    else:
        print(status(a.dir))
