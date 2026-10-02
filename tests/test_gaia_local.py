import sys, os, gzip, math, tempfile, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyoccult_corridor as C
import pyoccult_gaia_local as L
rng = np.random.default_rng(3)

# ---------- synthetic path (as in test_corridor): 20 days, ~0.4 deg/day, distance ~2 AU
STEP = 600.0
ets = np.arange(0.0, 20*86400 + STEP, STEP); t = ets/86400.0
u0 = C._unit(100.0, 20.0); e, n = C._basis(u0)
v = u0 + e*np.radians(0.40)*t[:, None] + n*np.radians(0.06)*t[:, None] - e*np.radians(0.004)*t[:, None]**2
U = v/np.linalg.norm(v, axis=1, keepdims=True)
D = (2.0 + 0.15*np.sin(t/7))*C.AU_KM
path = dict(ets=ets, u=U, delta_km=D, step_s=STEP, sun_au=U*0 + np.array([2.6, 0.5, 0.1]), earth_au=U*D[:, None]/C.AU_KM)
plan = C.plan_corridor('X', ets[0], ets[-1], dict(r_max_km=15.0, H=None, G=None), 18.0, 200.0, path=path)
w = np.degrees(plan['margin_km']/D) + plan['pad_arcsec']/3600.0

# ---------- synthetic Gaia: field stars + stars placed just inside / outside the strip + a few high-pm stars
N = 60000
ra = rng.uniform(95, 112, N); dec = rng.uniform(14, 30, N)
k = rng.integers(0, len(U), 3000); f = rng.uniform(-2, 2, 3000)                         # +/- 2 half-widths off the path
eb = np.cross([0, 0, 1.0], U[k]); eb /= np.linalg.norm(eb, axis=1, keepdims=True); nb = np.cross(U[k], eb)
side = np.where((rng.random(3000) < 0.5)[:, None], eb, nb)
P = U[k] + (f*np.radians(w[k]))[:, None]*side; P /= np.linalg.norm(P, axis=1, keepdims=True)
r2, d2 = C._radec(P)
ra = np.concatenate((ra, r2, [10.0, 200.0])); dec = np.concatenate((dec, d2, [-40.0, 60.0]))
M = len(ra)
g = rng.uniform(9, 21, M)
pmra, pmdec = rng.normal(0, 8, M), rng.normal(0, 8, M)
pmra[-2:] = [3000.0, -2500.0]; g[-2:] = [9.0, 12.0]                                     # high-pm, far from the path
ruwe = np.where(rng.random(M) < 0.05, 2.0, 1.0)
nopm = rng.random(M) < 0.03
ruwe[-2:] = 1.0; nopm[-2:] = False
src = pd.DataFrame(dict(solution_id=1, source_id=np.arange(M) + 10**15, ra=ra, dec=dec, parallax=rng.uniform(0.1, 5, M),
                        pmra=pmra, pmdec=pmdec, ruwe=ruwe, phot_g_mean_mag=g, other="x"))
src.loc[nopm, ["pmra", "pmdec", "parallax"]] = np.nan

cdn = tempfile.mkdtemp(); out = tempfile.mkdtemp()
names = []
shuf = src.sample(frac=1, random_state=1)
for i, idx in enumerate(np.array_split(np.arange(M), 3)):
    part = shuf.iloc[idx]
    nm = f"GaiaSource_{i:06d}-{i:06d}.csv.gz"; names.append(nm)
    with gzip.open(os.path.join(cdn, nm), "wt") as fh:
        fh.write("# ECSV header line\n# another\n")
        part.to_csv(fh, index=False, na_rep="null")
downloads = []
L.list_files = lambda timeout=90: [(nm, os.path.getsize(os.path.join(cdn, nm))) for nm in names]
def fake_download(name, dst, tries=4):
    downloads.append(name); open(dst, "wb").write(open(os.path.join(cdn, name), "rb").read())
L._download = fake_download

# ---------- 1. partial catalog is refused, full build, resume does nothing
L.process_file(names[0], out, 18.0) if os.makedirs(out, exist_ok=True) is None else None
import json; json.dump(dict(gmax=18.0, ruwe_max=L.RUWE_MAX, files=names), open(os.path.join(out, "catalog.json"), "w"))
try:
    L.LocalGaia(out); raise SystemExit("partial catalog accepted")
except RuntimeError as ex:
    print("partial refused:", str(ex)[:60])
L.build(out, 18.0, workers=0)
assert L.status(out)["complete"] and len(downloads) == 3
L.build(out, 18.0, workers=0); assert len(downloads) == 3, "resume re-downloaded"
assert not [x for x in os.listdir(out) if x.endswith(".tmp")]

# ---------- 2. filtering
lg = L.LocalGaia(out)
allk = np.concatenate([np.load(os.path.join(out, s + ".npy")) for s in lg.stems])
want = src[(src.phot_g_mean_mag <= 18) & src.pmra.notna() & (src.ruwe < 1.4)]
assert len(allk) == len(want) and set(allk["source_id"]) == set(want.source_id)
assert all((np.diff(np.load(os.path.join(out, s + ".npy"))["source_id"]) > 0).all() for s in lg.stems)
print("kept", len(allk), "of", M)

# ---------- 3. corridor lookup = superset of brute force, and small
cap = 17.0; plan["mag_cap"] = cap
got = lg.corridor_stars(plan)
S = C._unit(want.ra.to_numpy(), want.dec.to_numpy())
ang = np.degrees(np.arccos(np.clip(S @ U.T, -1, 1)))                                   # (stars, samples) deg
inside = (ang <= w[None, :]).any(axis=1) & (want.phot_g_mean_mag.to_numpy() <= cap)
need = set(want.source_id[inside])
print("strip stars (brute force)", len(need), " returned", len(got))
assert need <= set(got.source_id), f"missed {len(need - set(got.source_id))}"
assert len(got) < 3 * len(need) + 10
assert {10**15 + M - 2, 10**15 + M - 1} <= set(got.source_id), "high-pm stars missing"
assert (got.phot_g_mean_mag <= cap).all() and list(got.columns) == L.COLS

# ---------- 4. the candidate scan works on the local stars, cap above gmax is clipped
cands = C.corridor_candidates(plan, local=lg, verbose=True)[1]
assert len(cands) > 0
plan["mag_cap"] = 19.0; assert (lg.corridor_stars(plan).phot_g_mean_mag <= 18.0).all()

# ---------- 5. cells near the pole take the whole band
c = L.cells_near([10.0], [89.7], [0.5]); assert len(c) >= 360, len(c)
c = L.cells_near([359.99], [0.0], [0.05]); assert L.cell_of(0.01, 0.0).item() in c
print("GAIA LOCAL TESTS PASSED")
