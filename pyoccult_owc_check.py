#!.venv/bin/python3
"""pyoccult_owc_check.py - regression check against an OWC/Occult search result.

Runs pyoccult.py (corridor mode) for the asteroids in owc_reference.csv with the OWC search settings, then matches every
OWC event to our hits and checks: time within 10 s, magnitude drop within 0.25 mag, maximum duration within 10 %.
pyoccult_config.py is not changed: the settings below override it for this run only. Hits go to owc_check_hits.csv,
no maps.

    python pyoccult_owc_check.py                 # search + compare
    python pyoccult_owc_check.py --compare-only  # compare an existing owc_check_hits.csv

Duration = diameter / shadow speed. The report shows our diameter and the one OWC's duration implies (OWC duration x our
speed); when only the diameters differ, the result is "ok, size differs", not a failure. Drops above DROP_TOTAL mag
are not compared (they differ only by the asteroid's own magnitude estimate).
"""
import argparse, os, runpy, sys
import pandas as pd

REF = "owc_reference.csv"
OUT = "owc_check_hits.csv"
TOL_T, TOL_DROP, TOL_DUR = 10.0, 0.25, 0.10
DROP_TOTAL = 5.0          # drops above this are total occultations either way: not compared
SETTINGS = dict(ct="2026-10-01T00:00:00", days=8, max_shadow_dist=20.0, MAG_MIN=15.0, MIN_STAR_ALT=5.0,
                write_maps=False, search_mode="corridor")


def run(ref):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pyoccult_config as config
    for k, v in SETTINGS.items():
        setattr(config, k, v)
    config.targets = [str(t) for t in ref.target_id]
    config.hits_output_cvs_file = OUT
    if os.path.isfile(OUT):
        os.remove(OUT)
    runpy.run_path("pyoccult.py", run_name="__main__")


def compare(ref):
    hits = pd.read_csv(OUT) if os.path.isfile(OUT) else pd.DataFrame(columns=["target_id", "best_utc"])
    hits["t"] = pd.to_datetime(hits["best_utc"])
    rows, used = [], set()
    for r in ref.itertuples():
        h = hits[hits.target_id == r.target_id]
        dt = (h.t - pd.Timestamp(r.event_utc)).dt.total_seconds()
        if len(h) == 0 or dt.abs().min() > 600:
            rows.append(dict(target=r.target_id, name=r.name, owc_utc=r.event_utc, result="NOT FOUND"))
            continue
        i = dt.abs().idxmin()
        used.add(i)
        x = h.loc[i]
        ok_t = abs(dt[i]) <= TOL_T
        ok_drop = abs(x.mag_drop - r.mag_drop_v) <= TOL_DROP or min(x.mag_drop, r.mag_drop_v) > DROP_TOTAL
        ok_dur = abs(x.max_duration_s / r.max_dur_s - 1) <= TOL_DUR
        d_owc = r.max_dur_s * x.speed_kms                                  # diameter OWC's duration implies at our speed
        rows.append(dict(target=r.target_id, name=r.name, owc_utc=r.event_utc, dt_s=round(dt[i], 1),
                         star_G=round(x.mag, 2), star_V=r.star_mag_v,
                         drop=round(x.mag_drop, 2), owc_drop=r.mag_drop_v,
                         dur_s=round(x.max_duration_s, 2), owc_dur=r.max_dur_s,
                         miss_km=round(x.min_distance, 1), D_km=round(2 * x.r_km, 2), D_owc_km=round(d_owc, 2),
                         size_src="H+albedo" if str(x.size_source).startswith("H only") else str(x.size_source)[:14],
                         result="ok" if ok_t and ok_drop and ok_dur else
                         ("ok, size differs" if ok_t and ok_drop else
                          "FAIL " + ",".join(n for n, ok in (("time", ok_t), ("drop", ok_drop)) if not ok)
                          + (" (+size)" if not ok_dur else ""))))
    tab = pd.DataFrame(rows)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(tab.to_string(index=False))
    extra = hits.drop(index=list(used))
    if len(extra):
        print(f"\nOur hits not in the OWC list ({len(extra)}):")
        print(extra[["target_id", "best_utc", "mag", "mag_drop", "max_duration_s", "min_distance"]].to_string(index=False))
    n_ok = tab.result.str.startswith("ok").sum()
    n_size = (tab.result == "ok, size differs").sum()
    print(f"\n{n_ok}/{len(tab)} OWC events match (time {TOL_T:g} s, drop {TOL_DROP} mag below {DROP_TOTAL:g}); "
          f"{n_size} of them with a different diameter (duration off > {TOL_DUR:.0%})")
    return n_ok == len(tab)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compare-only", action="store_true")
    a = ap.parse_args()
    ref = pd.read_csv(REF, comment="#")
    if not a.compare_only:
        run(ref)
    sys.exit(0 if compare(ref) else 1)
