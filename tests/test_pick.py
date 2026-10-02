import os, sys, json, math, time, types, tempfile, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyoccult_pick as P, pyoccult_screen as SC

# ---------- 1. exposure rule: exposure(m) and the faintest useful star are inverse; aperture scales flux
opt = dict(ref_mag=12.5, ref_exp=0.08, ref_aperture=25.0, aperture=25.0, frames=4)
assert abs(SC.exposure_s(12.5, opt) - 0.08) < 1e-12 and abs(SC.exposure_s(15.0, opt) / SC.exposure_s(12.5, opt) - 10) < 1e-9
for dur in (0.2, 0.5, 2.0, 5.0):
    m = SC.faintest_useful_star(dur, opt)
    assert abs(opt["frames"] * SC.exposure_s(m, opt) - dur) < 1e-9, (dur, m)
big = dict(opt, aperture=50.0); assert abs(SC.faintest_useful_star(1.0, big) - SC.faintest_useful_star(1.0, opt) - 2.5 * math.log10(4)) < 1e-9
assert abs(SC.drop_cut(0.1) - 2.5388) < 1e-3
# the OWC reference events that define the default calibration are detectable: (G, OWC duration)
for g, dur in ((12.28, 0.48), (14.09, 1.55), (12.78, 0.51), (14.06, 4.33)):
    assert dur >= 4 * SC.exposure_s(g, opt), (g, dur)
print("exposure: G 12.5 ->", SC.exposure_s(12.5, opt), "s, G 15 ->", round(float(SC.exposure_s(15, opt)), 2), "s;",
      "faintest star for a 0.5 s event:", round(float(SC.faintest_useful_star(0.5, opt)), 2))

# ---------- 2. asteroid table: sizes like pyoccult.get_asteroid_size, bad orbits skipped, H limit
F = P.SBDB_FIELDS
def row(**kw):
    d = dict(spkid=20000001, full_name=" 1 Test", H="10", G=None, diameter=None, diameter_sigma=None, extent=None,
             albedo=None, a="2.5", e="0.1", i="5", om="10", w="20", ma="30", epoch="2461200.5", condition_code="0",
             neo="N", **{"class": "MBA"}); d.update(kw); return [d[f] for f in F]
data = [row(), row(spkid=20000002, diameter="100", diameter_sigma="2"), row(spkid=20000003, diameter="50"),
        row(spkid=20000004, e="1.2"), row(spkid=20000005, H=None), row(spkid=20000006, H="18.0")]
rows = P.build_rows(F, data, 17.0)
assert [r["number"] for r in rows] == [1, 2, 3], [r["number"] for r in rows]
r1, r2, r3 = rows
Dp = lambda p, H: 1329.0 / math.sqrt(p) * 10 ** (-H / 5)
assert r1["D_est"] and abs(r1["D_km"] - Dp(0.14, 10)) < 1e-9 and abs(r1["D_max_km"] - Dp(0.05, 10)) < 1e-9 and r1["G"] == 0.15
assert not r2["D_est"] and r2["D_km"] == 100 and r2["D_max_km"] == 106 and abs(r3["D_max_km"] - 50 * 1.45) < 1e-9
assert len(P.build_rows(F, data, None)) == 4                       # --all keeps H 18, still skips the bad ones

# ---------- 3. SBDB bulk cache: reused only if full precision, all fields, covering hmax and fresh
calls = []
class R:
    def __init__(s, b): s.b = b
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def read(s): return json.dumps(s.b).encode()
def urlopen(url, timeout):
    calls.append(url); return R(dict(fields=F, data=data))
_j = json
P.urllib.request.urlopen = urlopen
cache = os.path.join(tempfile.mkdtemp(), "bulk.json")
P.fetch_sbdb(17.0, cache, 1e9); assert len(calls) == 1 and "full-prec=true" in calls[0] and "H%7CLT%7C17" in calls[0]
P.fetch_sbdb(17.0, cache, 1e9); assert len(calls) == 1, "cache not reused"
P.fetch_sbdb(16.0, cache, 1e9); assert len(calls) == 1, "a cache for H < 17 covers H < 16"
P.fetch_sbdb(None, cache, 1e9); assert len(calls) == 2 and "sb-cdata" not in calls[1], "--all needs a new download"
P.fetch_sbdb(17.0, cache, 1e9); assert len(calls) == 2, "the --all cache covers H < 17"
P.fetch_sbdb(17.0, cache, 0.0); assert len(calls) == 3, "expired cache not refreshed"
b = _j.load(open(cache)); b["full_prec"] = False; _j.dump(b, open(cache, "w"))
P.fetch_sbdb(17.0, cache, 1e9); assert len(calls) == 4, "an old rounded-elements cache must be replaced"
assert not [f for f in os.listdir(os.path.dirname(cache)) if f.endswith(".tmp")]

# ---------- 4. screen helpers: cubic interpolation and the site solver on a straight shadow track
ets = np.arange(0.0, 6000.0, 600.0)
g = np.stack([ets * 7.0 - 20000.0, 3.0e8 + 0 * ets, 50.0 + ets * 0.002], 1)        # linear motion: exact for cubics
tq = np.array([601.0, 2999.5, 4200.0]); gi = SC._interp(g, ets, tq)
assert np.allclose(gi, np.stack([tq * 7.0 - 20000.0, 3.0e8 + 0 * tq, 50.0 + tq * 0.002], 1))
class FakeSite:                                                                         # observer fixed at the origin
    def at(self, et):
        et = np.atleast_1d(et); return np.zeros((len(et), 3)), np.tile([0.0, 0.0, 1.0], (len(et), 1))
sdir = np.array([[0.0, 1.0, 0.0]])                                                       # star along +y: plane is x, z
T_TRUE, B = 2000.0, 37.0                                                                 # closest approach time, miss km
track = lambda t: np.stack([7.0 * (np.atleast_1d(t) - T_TRUE), 3.0e8 + 0 * np.atleast_1d(t), B + 0 * np.atleast_1d(t)], 1)
t, miss, off, v = SC.solve_site(None, FakeSite(), track, sdir, np.array([2300.0]), np.array([900.0]))
print("site solver: t", round(float(t[0]), 4), "miss", round(float(miss[0]), 4), "speed", round(float(v[0]), 4))
assert abs(t[0] - T_TRUE) < 1e-3 and abs(miss[0] - B) < 1e-6 and abs(v[0] - 7.0) < 1e-9
t, miss, _, _ = SC.solve_site(None, FakeSite(), track, sdir, np.array([2300.0]), np.array([100.0]))
assert abs(t[0] - 2200.0) < 1e-9, "the solution must stay inside the bracket"
print("PICK TESTS PASSED")
