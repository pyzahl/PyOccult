import sys, json, math, numpy as np
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..'))
import pyoccult_pick as P

# 1 galactic matrix: galactic centre and north pole
def eq(ra, dec):
    ra, dec = math.radians(ra), math.radians(dec); return np.array([math.cos(dec)*math.cos(ra), math.cos(dec)*math.sin(ra), math.sin(dec)])
l0 = P.EQ2GAL @ eq(266.405, -28.936); print("GC galactic xyz", l0.round(3)); assert abs(l0[0]-1) < 1e-3
ngp = P.EQ2GAL @ eq(192.859, 27.128); assert abs(ngp[2]-1) < 1e-3
assert P.EQ2GAL @ P.EQ2GAL.T @ np.eye(3) is not None and np.allclose(P.EQ2GAL @ P.EQ2GAL.T, np.eye(3), atol=1e-6)

# 2 Earth: distance 0.983..1.017 AU; at the March equinox the Earth sees the Sun near ecliptic longitude 0
jd = 2451545.0 + np.arange(0, 366.0)
E, R = P.earth_helio_ecl(jd); print("R range", R.min().round(4), R.max().round(4)); assert .982 < R.min() < .984 and 1.016 < R.max() < 1.018
jd_eq = 2461119.0                      # ~2026-03-20 14:46 UT equinox is JD 2461120.1
e1, _ = P.earth_helio_ecl(np.array([2461120.1])); lam = math.degrees(math.atan2(-e1[0,1], -e1[0,0])) % 360
print("Sun ecl lon at 2026 equinox", round(lam,3)); assert abs(lam - (360 - 0.01397*26.2)) < 0.03   # J2000 frame: equinox of date is 0.366 deg west

# 3 Kepler: period closure, radius bounds, orbit-plane normal
el = {k: np.array([v]) for k, v in dict(a=2.766, e=0.0796, i=10.59, om=80.27, w=73.4, ma=130.0, epoch=2460600.5).items()}
per = 365.25636 * el['a'][0]**1.5 * 0.98560767 / 0.98560767
t = 2460600.5 + np.array([0.0, 1681.0])                         # ~ period of Ceres (4.60 yr = 1680 d)
pos, r = P.kepler_helio_ecl(el, t)
P_days = 360.0 / (0.98560767 / el['a'][0]**1.5); print("period d", round(P_days,1))
pos2, _ = P.kepler_helio_ecl(el, np.array([2460600.5 + P_days]))
assert np.allclose(pos[0,0], pos2[0,0], atol=1e-6), (pos[0,0], pos2[0,0])
tt = 2460600.5 + np.linspace(0, P_days, 400); pp, rr = P.kepler_helio_ecl(el, tt)
assert abs(rr.min()-2.766*(1-.0796)) < 2e-3 and abs(rr.max()-2.766*(1+.0796)) < 2e-3
hvec = np.cross(pp[0,10], pp[0,11]); hvec /= np.linalg.norm(hvec); I, O = math.radians(10.59), math.radians(80.27)
want = np.array([math.sin(I)*math.sin(O), -math.sin(I)*math.cos(O), math.cos(I)])
assert np.allclose(hvec, want, atol=1e-3), (hvec, want)
# vis-viva check at one point (speed)
v = np.linalg.norm(pp[0,11]-pp[0,10]) / (tt[11]-tt[10]); vv = 0.01720209895*math.sqrt(2/rr[0,10] - 1/2.766); print("speed", round(v,6), round(vv,6)); assert abs(v-vv)/vv < 2e-3

# 4 brightness: Ceres-like H=3.4 near opposition at r=2.6, delta=1.6 -> V ~ 7.2-7.6 ; small-phase should equal H+5log(r d)
m = P.apparent_mag(np.array(3.4), np.array(0.12), np.array(2.6), np.array(1.6), np.array(1.0)); print("m_ast", float(m)); assert abs(float(m) - (3.4 + 5*math.log10(2.6*1.6))) < 1e-9
# 5 diameters
D, est = P.diameter_km(np.array([np.nan, 100.0]), np.array([np.nan, 0.1]), np.array([12.0, 9.0])); print(D, est); assert est.tolist() == [True, False] and abs(D[0] - 1329/math.sqrt(0.14)*10**(-12/5)) < 1e-9
# 6 star density model: monotonic in mag, higher at plane, sky-mean equals the table
d = P.star_density(np.array([0., 30., 90.]), 14.0); print("dens G<14 b=0,30,90", d.round(0)); assert d[0] > d[1] > d[2]
bs = np.radians(np.linspace(-90, 90, 20001)); mean = np.sum(P.star_density(np.degrees(bs), 14.0)*np.cos(bs))/np.sum(np.cos(bs)); print("sky mean", round(mean,1)); assert abs(mean-580) < 8
assert P.star_density(np.array(0.), 15) > P.star_density(np.array(0.), 14)
print("unit checks OK")
