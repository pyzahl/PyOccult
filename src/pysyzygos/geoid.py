"""geoid.py - height of the geoid (mean sea level) above the WGS84 ellipsoid, EGM96 (NGA, public domain).

Site elevations from maps, Open-Meteo and most GPS displays are above mean sea level (the geoid); the geometry needs
heights above the WGS84 ellipsoid: ellipsoid height = elevation + N, with N between -107 m (south of India) and +85 m
(New Guinea). The site's N is looked up once when the site is saved (sites.py key `geoid_m`, `fill`) and added in
pysyzygos_config.py (ELE = ele + geoid_m); a site whose height is already above the ellipsoid (MPC observatory codes,
GPS set to ellipsoid height) has `ele_ref: "ellipsoid"` and geoid_m 0.

Grid: data/egm96_30min.npy, 0.5 deg (361 x 720, from 90 N and 0 E), int16 centimetres, sampled from GeographicLib's
EGM96 15-minute grid (URL_EGM96_GEOID); bilinear: 0.12 m rms, at most 3 m against the 15-minute grid.

    python -m pysyzygos.geoid build <egm96-15.pgm>     # rebuild the grid (from egm96-15.tar.bz2)
    python -m pysyzygos.geoid <lat> <lon>              # N at a place, metres
"""
from pysyzygos.version import __version__
import os, sys
import numpy as np

from pysyzygos.home import PKG

GRID = os.path.join(PKG, "data", "egm96_30min.npy")
STEP = 0.5                                       # degrees
_grid = None


def _load():
    global _grid
    if _grid is None:
        _grid = np.load(GRID).astype(float) / 100.0                 # metres
    return _grid


def height(lat, lon):
    """Geoid height N (m) above the WGS84 ellipsoid at geodetic lat, lon (degrees, east-positive), bilinear."""
    g = _load()
    r = (90.0 - float(lat)) / STEP
    c = (float(lon) % 360.0) / STEP
    r0 = min(max(int(np.floor(r)), 0), g.shape[0] - 2)
    c0 = int(np.floor(c)) % g.shape[1]
    c1 = (c0 + 1) % g.shape[1]
    fr, fc = r - r0, c - np.floor(c)
    return float(g[r0, c0] * (1 - fr) * (1 - fc) + g[r0, c1] * (1 - fr) * fc
                 + g[r0 + 1, c0] * fr * (1 - fc) + g[r0 + 1, c1] * fr * fc)


def fill(site):
    """Set site["geoid_m"] (rounded to 0.1 m) from its lat/lon, or 0 for a height above the ellipsoid
    (ele_ref "ellipsoid"). Returns the site."""
    if site.get("ele_ref") == "ellipsoid":
        site["geoid_m"] = 0.0
    else:
        site["geoid_m"] = round(height(site["lat"], site["lon"]), 1)
    return site


def fill_all(sites):
    """fill() every site of a sites dict (recomputed: a moved site gets its new value)."""
    for s in sites.values():
        fill(s)
    return sites


def build(pgm_path, out=GRID):
    """data/egm96_30min.npy from GeographicLib's egm96-15.pgm (P5, 1440 x 721, from 90 N 0 E, value = Offset + Scale x
    raw, big-endian 16 bit): every second row and column, in centimetres."""
    raw = open(pgm_path, "rb").read()
    parts, pos, offset, scale = [], 0, None, None
    while len(parts) < 4:
        j = raw.index(b"\n", pos)
        line = raw[pos:j].decode("ascii")
        pos = j + 1
        if line.startswith("# Offset"):
            offset = float(line.split()[2])
        elif line.startswith("# Scale"):
            scale = float(line.split()[2])
        elif not line.startswith("#"):
            parts += line.split()
    if parts[0] != "P5" or parts[1:3] != ["1440", "721"] or offset is None or scale is None:
        raise ValueError(f"not GeographicLib's EGM96 15-minute grid: {parts[:3]}, offset {offset}, scale {scale}")
    g = offset + scale * np.frombuffer(raw[pos:pos + 1440 * 721 * 2], ">u2").reshape(721, 1440).astype(float)
    sub = np.round(g[::2, ::2] * 100.0).astype(np.int16)             # 361 x 720, cm
    tmp = out + ".tmp"
    with open(tmp, "wb") as f:
        np.save(f, sub)
    os.replace(tmp, out)
    return sub.shape, float(sub.min()) / 100.0, float(sub.max()) / 100.0


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    if len(a) == 2 and a[0] == "build":
        shape, lo, hi = build(a[1])
        print(f"wrote {GRID}: {shape}, N {lo:.2f} .. {hi:.2f} m")
    elif len(a) == 2:
        print(f"{height(float(a[0]), float(a[1])):.2f}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
