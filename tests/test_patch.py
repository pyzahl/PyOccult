import sys, os, math, types, tempfile, numpy as np, pandas as pd
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..')); import pyoccult_corridor as C
exec(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'test_corridor.py')).read().split("# ---------- 3. magnitude cap")[0])      # reuse synthetic path, catalogue, FakeLocal (no tests after this point)
src = open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..', 'pyoccult.py')).read()
funcs = src[src.index("def handle_star"):src.index('if __name__ == "__main__":')]   # handle_star + target_test_corridor

out_csv = os.path.join(tempfile.mkdtemp(), "hits.csv")
calls = dict(star_test=0, gate=0, propagate=0)
class Q:                                   # stand-in for astropy quantity
    def __init__(s, v): s.value = v
    def to(s, _): return s
class Loc: lon, lat, height = Q(-1.27), Q(0.71), Q(0.04)
class Cfg: max_shadow_dist = 200.0; hits_output_cvs_file = out_csv; min_mag_drop = 0.1; cache_path = tempfile.mkdtemp(); write_maps = False; default_sigma3_km = 10.0
ns = dict(np=np, pd=pd, os=os, config=Cfg, corridor=C, u=types.SimpleNamespace(rad=None, km=None))
ns['spice'] = types.SimpleNamespace(et2utc=lambda et, f, p: "ET:%r" % float(et))
def star_test(loc, utc, span, ra, dec, tid, r, reach):
    calls['star_test'] += 1
    et = float(utc[3:]) + 7.0                                  # solver lands 7 s from the guess, inside the bracket
    return None if calls['star_test'] % 3 == 0 else dict(best_utc=utc, best_et=et, min_distance=40.0, observable="yes")
ns.update(star_test=star_test,
          window_is_observable=lambda et, span, geo, t: (calls.__setitem__('gate', calls['gate']+1) or int(et) % 5 != 0),
          is_new_hit=lambda t, s, et: True, observable=lambda et, sd, geo: (True, 45.0, -20.0),
          apparent_mag_HG=lambda et, t, H, G: 15.0,
          event_metrics=lambda et, sd, geo, t, r, ms, ma: dict(speed_kms=12.0, chord_km=20.0, duration_s=1.5, mag_drop=0.8),
          moon_info=lambda et, sd, geo: dict(moon_sep_deg=40.0),
          besselian_offsets=lambda et, sd, geo, t: (1.0, 2.0), get_asteroid_name=lambda t: "Test",
          path_sigma3_km=lambda t, utc: None)
exec(funcs, ns)
# propagation stand-in (astropy is not installed in this sandbox): same output columns as propagate_exact
def fake_prop(df, utc):
    out = df.copy(); out["ra_20261003"], out["dec_20261003"] = out["ra"], out["dec"]; calls['propagate'] += 1; return out
C.propagate_exact = fake_prop

plan = C.plan_corridor('X', ets[0], ets[-1], dict(r_max_km=15.0, H=12.0, G=0.15, r_km=10.0), 20.0, 200.0, path=path)
stars, cands = C.corridor_candidates(plan, FakeLocal(), verbose=False)
sub = cands.sort_values('et_guess').head(60)
class _ET(list): pass
ns['_et'] = [float(sub.et_guess.iloc[0])]
size = dict(r_km=10.0, r_min_km=5.0, r_max_km=15.0, source="test", H=12.0, G=0.15)
n = ns['target_test_corridor'](Loc, plan, 'X', size, stars_cands=(stars, sub))
log = pd.read_csv(out_csv)
print("candidates", len(sub), "gate calls", calls['gate'], "solver calls", calls['star_test'], "propagations", calls['propagate'], "logged", n, "csv rows", len(log))
assert calls['gate'] == len(sub) and calls['propagate'] == calls['gate'] - (sub.et_guess.astype(int) % 5 == 0).sum()
assert calls['star_test'] == calls['propagate'] and n == len(log) and n > 0
need = {"target_id","best_utc","min_distance","r_min_km","r_max_km","size_source","star","mag","mag_drop","moon_sep_deg","offset_east_km","max_duration_s","observable"}
assert need <= set(log.columns), need - set(log.columns)
print(log.iloc[0][["target_id","star","mag","min_distance","mag_drop","max_duration_s"]].to_dict())
print("PATCH SMOKE TEST PASSED")
