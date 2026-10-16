"""starrv.py - Gaia DR3 radial velocities of the stars where they matter for the position (perspective acceleration).

A star's radial velocity changes its proper motion over the years (perspective acceleration): the position moves by
about mu * zeta * t^2, zeta = v_r x parallax (v_r in AU/yr, parallax in rad), t the years since Gaia's epoch 2016.0.
For most stars this is far below 0.001 mas; for nearby fast stars it is large (Barnard's star: 75 mas by 2026). The
local catalog has no radial velocities, so this table keeps Gaia DR3's for every star where they move the position by
more than 0.01 mas within 20 years: pm x |radial_velocity| x parallax > 24445 (mas/yr x km/s x mas). Used by
corridor.propagate_exact (and the old windows mode); unknown stars get 0, as before.

Table: data/gaia_dr3_rv_fast.npy (source_id int64, rv float32 km/s, rv_error float32), sorted by source_id; built from
a Gaia archive query (`python -m pysyzygos.starrv build <csv>`; the query is in QUERY, run in parts below the
archive's 50000-row cap for anonymous jobs).
"""
from pysyzygos.version import __version__
import os, sys
import numpy as np

from pysyzygos.home import PKG

FILE = os.path.join(PKG, "data", "gaia_dr3_rv_fast.npy")
DTYPE = np.dtype([("source_id", "<i8"), ("rv", "<f4"), ("rv_error", "<f4")])
THRESHOLD = 24445.0           # pm x |rv| x parallax: 0.01 mas within 20 years (0.01 / (400 x 4.8481e-9 / 4.74047))
QUERY = ("SELECT source_id, radial_velocity, radial_velocity_error, phot_g_mean_mag, pm, parallax "
         "FROM gaiadr3.gaia_source WHERE source_id >= {lo} AND source_id < {hi} AND radial_velocity IS NOT NULL "
         f"AND parallax > 0 AND pm * ABS(radial_velocity) * parallax > {THRESHOLD:g}")
_table = None


def _load():
    global _table
    if _table is None:
        _table = np.load(FILE) if os.path.isfile(FILE) else np.zeros(0, DTYPE)
    return _table


def rv_for(source_ids):
    """Radial velocities (km/s, float array) for these Gaia DR3 source ids; 0 where the table has none."""
    ids = np.asarray(source_ids, dtype=np.int64).ravel()
    t = _load()
    out = np.zeros(len(ids))
    if len(t) and len(ids):
        i = np.searchsorted(t["source_id"], ids)
        i = np.minimum(i, len(t) - 1)
        hit = t["source_id"][i] == ids
        out[hit] = t["rv"][i[hit]]
    return out


def perspective_mas(pm, rv, parallax, years):
    """Size of the position change from the radial velocity (mas) after `years`: pm x zeta x t^2."""
    zeta = np.abs(rv) / 4.740470463 * np.asarray(parallax) * np.pi / 648e6          # 1/yr
    return np.asarray(pm) * zeta * np.asarray(years) ** 2


def build(csv_path, out=FILE):
    """data/gaia_dr3_rv_fast.npy from the archive query's CSV (source_id, radial_velocity, radial_velocity_error)."""
    import pandas as pd
    df = pd.read_csv(csv_path).drop_duplicates("source_id").sort_values("source_id")
    a = np.zeros(len(df), DTYPE)
    a["source_id"], a["rv"] = df.source_id.to_numpy(), df.radial_velocity.to_numpy()
    a["rv_error"] = df.radial_velocity_error.to_numpy()
    tmp = out + ".tmp"
    with open(tmp, "wb") as f:
        np.save(f, a)
    os.replace(tmp, out)
    return len(a)


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    if len(a) == 2 and a[0] == "build":
        print(f"wrote {FILE}: {build(a[1])} stars")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
