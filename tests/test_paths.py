"""Test pyoccult_paths.py with a stand-in 'spiceypy' that follows the real contract:
surfpt() returns ONLY the point and raises NotFoundError on a miss (as in the user's traceback).
Geometry (ellipsoid intersection, geodetic lon/lat, Earth rotation) is exact; only ephemerides are synthetic."""
import sys, types, importlib.util
import numpy as np

A, C = 6378.137, 6356.7523142           # WGS84-like: oblate Earth
OMEGA = 7.2921159e-5                    # rad/s
ET0 = 8.45e8
D_AST = 1.6e8                           # km
star_ra, star_dec = np.radians(70.0), np.radians(10.0)
STAR = np.array([np.cos(star_dec)*np.cos(star_ra), np.cos(star_dec)*np.sin(star_ra), np.sin(star_dec)])


class NotFoundError(Exception):
    pass


def make_stub(xi0, eta0, vxi, veta):
    z = STAR
    x = np.cross([0, 0, 1.0], z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    s = types.ModuleType('spiceypy')

    def spkpos(tid, et, frame, corr, obs):
        t = et - ET0
        return D_AST * z + (xi0 + vxi*t) * x + (eta0 + veta*t) * y, 0.0

    def pxform(frm, to, et):                         # ITRF = Rz(+theta) * J2000, theta = OMEGA*(et-ET0)
        th = OMEGA * (et - ET0)
        c, sn = np.cos(th), np.sin(th)
        Rz = np.array([[c, sn, 0], [-sn, c, 0], [0, 0, 1.0]])   # J2000 -> ITRF
        return Rz if (frm, to) == ('J2000', 'ITRF93') else Rz.T

    def bodvrd(body, item, n):
        return n, np.array([A, A, C])

    def surfpt(positn, u, a, b, c):
        v = np.asarray(positn, float); d = np.asarray(u, float); d = d / np.linalg.norm(d)
        S = np.array([1/a**2, 1/b**2, 1/c**2])
        qa = np.sum(S*d*d); qb = 2*np.sum(S*v*d); qc = np.sum(S*v*v) - 1
        disc = qb*qb - 4*qa*qc
        if disc < 0:
            raise NotFoundError("Spice returns not found for function: surfpt")
        t = (-qb - np.sqrt(disc)) / (2*qa)
        if t < 0:
            raise NotFoundError("Spice returns not found for function: surfpt")
        return v + t*d                                # point only, like spiceypy

    def recgeo(p, re, f):
        rp = re*(1-f); lon = np.arctan2(p[1], p[0]); r = np.hypot(p[0], p[1])
        e2 = 1 - (rp/re)**2; lat = np.arctan2(p[2], r*(1-e2))
        for _ in range(20):
            N = re/np.sqrt(1 - e2*np.sin(lat)**2)
            h = r/np.cos(lat) - N
            lat = np.arctan2(p[2], r*(1 - e2*N/(N+h)))
        N = re/np.sqrt(1 - e2*np.sin(lat)**2)
        return lon, lat, r/np.cos(lat) - N

    def et2utc(et, fmt, prec): return "2026-10-03T07:07:33"

    for f in (spkpos, pxform, bodvrd, surfpt, recgeo, et2utc):
        setattr(s, f.__name__, f)
    ex = types.ModuleType('spiceypy.utils.exceptions'); ex.NotFoundError = NotFoundError
    ut = types.ModuleType('spiceypy.utils'); ut.exceptions = ex
    s.utils = ut
    sys.modules.update({'spiceypy': s, 'spiceypy.utils': ut, 'spiceypy.utils.exceptions': ex})
    return s, x, y, z


def load_module():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))   # for pyoccult_version
    spec = importlib.util.spec_from_file_location('pyoccult_paths', __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..', 'pyoccult_paths.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def geodetic_to_xyz(lon_deg, lat_deg, a=A, c=C):
    lon, lat = np.radians(lon_deg), np.radians(lat_deg)
    e2 = 1 - (c/a)**2
    N = a/np.sqrt(1 - e2*np.sin(lat)**2)
    return np.array([N*np.cos(lat)*np.cos(lon), N*np.cos(lat)*np.sin(lon), N*(1-e2)*np.sin(lat)])


def run_case(label, xi0, eta0, vxi, veta, r=2.0, s3=6.0, expect_empty=False, expect_missing=()):
    s, x, y, z = make_stub(xi0, eta0, vxi, veta)
    m = load_module()
    paths = m.shadow_path('4272', STAR, ET0, r, s3)           # defaults: auto span and step
    print(f"\n== {label}: speed {np.hypot(vxi, veta):.2f} km/s, points per line:",
          {k: len(v) for k, v in paths.items()})
    offs = {'center': 0.0, 'edge_plus': r, 'edge_minus': -r, 'sigma1_plus': r+s3/3, 'sigma1_minus': -(r+s3/3),
            'sigma_plus': r+s3, 'sigma_minus': -(r+s3)}
    if expect_empty:
        assert all(len(v) == 0 for v in paths.values()), "expected no points"
        print("   all lines empty, no exception")
        m.write_shadow_kml(paths, '/tmp/empty.kml', 'empty')
        return paths
    for k, v_ in paths.items():
        if k in expect_missing:
            assert len(v_) == 0, f"{k} should miss the Earth entirely but has {len(v_)} points"
        else:
            assert len(v_) >= 3, f"{k} has only {len(v_)} points"

    worst_plane, worst_dur = 0.0, 0.0
    v = np.array([vxi, veta]); nrm = np.array([-v[1], v[0]]) / np.linalg.norm(v)
    for name, off in offs.items():
        for et, lon, lat, dur in paths[name]:
            t = et - ET0
            R = s.pxform('J2000', 'ITRF93', et)
            p_j2000 = R.T @ geodetic_to_xyz(lon, lat)
            # (1) ground point must lie on the offset shadow axis: its plane coordinates equal the axis + off*n
            want = np.array([xi0 + vxi*t, eta0 + veta*t]) + off*nrm
            got = np.array([p_j2000 @ x, p_j2000 @ y])
            worst_plane = max(worst_plane, np.linalg.norm(got - want))
            # (2) must be the star-facing side
            assert p_j2000 @ z > 0, "point on the far side of the Earth"
            # (3) centre-line duration vs an independent calculation
            if name == 'center':
                p1 = s.pxform('ITRF93', 'J2000', et + 1.0) @ geodetic_to_xyz(lon, lat)
                vg = np.array([(p1 - p_j2000) @ x, (p1 - p_j2000) @ y])
                worst_dur = max(worst_dur, abs(dur - 2*r/np.linalg.norm(v - vg)))
    print(f"   max plane-position error {worst_plane:.2e} km, max duration error {worst_dur:.2e} s")
    assert worst_plane < 1e-6 and worst_dur < 1e-6
    c = paths['center']
    print(f"   centre line covers {c[0][0]-ET0:+.0f} s .. {c[-1][0]-ET0:+.0f} s, duration range "
          f"{min(p[3] for p in c):.3f}..{max(p[3] for p in c):.3f} s")
    return paths


# 1) typical central pass, 6 km/s
p1 = run_case("central pass", xi0=1500.0, eta0=-2500.0, vxi=5.0, veta=3.3)
# 2) slow shadow (1 km/s), as for 70141: span must auto-extend
p2 = run_case("slow shadow", xi0=-800.0, eta0=1200.0, vxi=-0.8, veta=0.6)
# 3) grazing: axis only just inside the limb, so some lines miss the Earth entirely
LIMB = np.sqrt(A**2*np.sin(star_dec)**2 + C**2*np.cos(star_dec)**2)   # N-S semi-axis of the projected silhouette
print(f"projected N-S limb radius {LIMB:.3f} km")
p3 = run_case("grazing pass (axis 5 km inside the limb; +8 km limit line is outside)",
              xi0=0.0, eta0=LIMB-5.0, vxi=7.0, veta=0.0, expect_missing=('sigma_plus',))
# 4) misses the Earth completely
p4 = run_case("complete miss", xi0=-30000.0, eta0=20000.0, vxi=6.0, veta=0.0, expect_empty=True)

# KML for the grazing case: well-formed, and lines with <2 points are dropped
m = load_module()
m.write_shadow_kml(p3, '/tmp/graze.kml', 'Graze & <test>', observer=(-74.006, 40.713))
import xml.etree.ElementTree as ET
root = ET.parse('/tmp/graze.kml').getroot()
ns = {'k': 'http://www.opengis.net/kml/2.2'}
print("\nKML (grazing case): linestrings", len(root.findall('.//k:LineString', ns)),
      "placemarks", len(root.findall('.//k:Placemark', ns)))
print("ALL TESTS PASSED")
