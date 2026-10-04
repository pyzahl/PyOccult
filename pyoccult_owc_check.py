#!.venv/bin/python3
"""pyoccult_owc_check.py - regression check against an OWC (Occult Watcher Cloud) search result.

Paste an OWC search result (the page text: the "Search Results for filter ..." line and the event table) into
owc_reference.txt (private, not in git: it names your site). This script reads the events and the search settings
from it (distance from shadow, StarMag, MinDur, Aperture, DetectionFrames, MinStarAltitude), runs pyoccult.py
(corridor mode) for those asteroids over the events' dates at your site (sites.py), then matches every OWC event to
our hits and checks: time within 10 s, magnitude drop within 0.25 mag, maximum duration within 10 %.
pyoccult_config.py is not changed: the settings override it for this run only. Hits go to owc_check_hits.csv, no maps.

    python pyoccult_owc_check.py                 # search + compare
    python pyoccult_owc_check.py --compare-only  # compare an existing owc_check_hits.csv
    python pyoccult_owc_check.py --ref other_owc_result.txt

Duration = diameter / shadow speed. The report shows our diameter and the one OWC's duration implies (OWC duration x our
speed); when only the diameters differ, the result is "ok, size differs", not a failure. Drops above DROP_TOTAL mag
are not compared (they differ only by the asteroid's own magnitude estimate).
"""
import argparse, os, re, runpy, sys
import pandas as pd

REF = "owc_reference.txt"
OUT = "owc_check_hits.csv"
TOL_T, TOL_DROP, TOL_DUR = 10.0, 0.25, 0.10
DROP_TOTAL = 5.0          # drops above this are total occultations either way: not compared
EVENT = re.compile(r"\((\d+)\)\s*([^\t]*)\t\s*(\d{4}-[A-Za-z]{3}-\d{2}),\s*(\d{2}:\d{2}:\d{2})"
                   r"\s*(?:\u263c\s*(-?\d+(?:\.\d+)?)\s*\u00b0?)?"           # twilight events: "\u263c -5\u00b0" = Sun altitude
                   r"\s*\t\s*([\d.]+)\s*\t\s*([\d.]+)\s*\t\s*([\d.]+)\s*\t\s*(\d+)")


def _clean_name(text):
    """'2000 SB350 NALowMagMDMattson' -> '2000 SB350': drop OWC's trailing tag words (capitals run into lowercase)."""
    words = text.split()
    while words and re.match(r"^[A-Z]{2,}[A-Za-z]*[a-z]", words[-1]):
        words.pop()
    return " ".join(words)


def read_owc(path):
    """(events DataFrame, settings dict) from an OWC search result pasted as text."""
    text = open(path, encoding="utf-8").read()
    rows = [dict(target_id=int(m[1]), name=_clean_name(m[2]),
                 event_utc=pd.Timestamp(f"{m[3]} {m[4]}").strftime("%Y-%m-%dT%H:%M:%S"),
                 sun_alt_deg=float(m[5]) if m[5] else float("nan"), star_mag_v=float(m[6]),
                 mag_drop_v=float(m[7]), max_dur_s=float(m[8]), altitude_deg=float(m[9])) for m in EVENT.finditer(text)]
    if not rows:
        sys.exit(f"no OWC events found in {path}")
    ref = pd.DataFrame(rows)
    f = re.search(r"Search Results for filter(.*)", text)
    f = f[1] if f else ""
    num = lambda pat, d: float(m[1]) if (m := re.search(pat, f, re.I)) else d
    t0 = pd.Timestamp(ref.event_utc.min()).normalize() - pd.Timedelta(days=1)
    t1 = pd.Timestamp(ref.event_utc.max()).normalize() + pd.Timedelta(days=2)
    settings = dict(max_shadow_dist=num(r"([\d.]+)\s*km from shadow", 20.0), MAG_MIN=num(r"StarMag:\s*([\d.]+)", 15.0),
                    pick_min_dur_s=num(r"MinDur:\s*([\d.]+)", 0.4), pick_aperture_cm=num(r"Aperture:\s*([\d.]+)", 25.0),
                    pick_frames=int(num(r"DetectionFrames:\s*(\d+)", 4)), MIN_STAR_ALT=num(r"MinStarAltitude:\s*([\d.]+)", 10.0),
                    ct=t0.strftime("%Y-%m-%dT%H:%M:%S"), days=(t1 - t0).days, write_maps=False, search_mode="corridor")
    if ref.sun_alt_deg.notna().any():               # OWC lists twilight events: allow the Sun up to the brightest one
        settings["MAX_SUN_ALT"] = float(ref.sun_alt_deg.max()) + 1.0
    return ref, settings


def run(ref, settings):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pyoccult_config as config
    for k, v in settings.items():
        setattr(config, k, v)
    config.targets = [str(t) for t in ref.target_id]
    config.targets_source = "list"
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
    ap.add_argument("--ref", default=REF, help="OWC search result as text (default owc_reference.txt)")
    a = ap.parse_args()
    ref, settings = read_owc(a.ref)
    print(f"{len(ref)} OWC events, {settings['ct'][:10]} + {settings['days']} d, reach {settings['max_shadow_dist']:g} km, "
          f"G <= {settings['MAG_MIN']:g}, min alt {settings['MIN_STAR_ALT']:g}, {settings['pick_aperture_cm']:g} cm, "
          f"{settings['pick_frames']} frames", flush=True)
    if not a.compare_only:
        run(ref, settings)
    sys.exit(0 if compare(ref) else 1)
