"""favorites.py - a hand-picked list of events from any search and any site, kept with everything known.

    favorites/favorites.json                    the list (one entry per event, newest first)
    favorites/favorites.csv                     the same as a flat table (rewritten with every change; for sharing)
    favorites/<target>_<YYYYMMDDTHHMM>/          the event's own copies of its KML ground track and preview SVG

An entry holds the full hits_log record, the site and the run context of the search it came from, when it was added,
a status (planned / observed / cancelled / clouded) and a note. Map and preview are copies, so later searches (which
overwrite or delete files in maps/) never change a favorite. Private (site names): favorites/ is in .gitignore.
Used by gui.py (report star buttons, Favorites tab). Standard library only.

    pyoccult favorites list
"""
from pyoccult.version import __version__
from pyoccult import urls as U
import glob, json, os, shutil, sys, tempfile
from datetime import datetime, timezone

DIR = "favorites"
STATUSES = ("planned", "observed", "cancelled", "clouded")


def key_of(target_id, best_utc):
    """<target>_<YYYYMMDDTHHMM>, the same stem as the files in maps/."""
    return f"{str(target_id).strip()}_{str(best_utc).strip()[:16].replace(':', '').replace('-', '')}"


def _path(folder):
    return os.path.join(folder, "favorites.json")


def load(folder=DIR):
    try:
        with open(_path(folder), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save(items, folder):
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, _path(folder))
    write_csv(items, folder)


PHYS_KEYS = ("H", "G", "diameter", "diameter_sigma", "extent", "albedo", "rot_per", "pole", "spec_T", "spec_B")


def phys_of(entry):
    """{name: (value, ref)} of the size-cache entry (sbdb) kept with a favorite, for H, G, diameter, ..."""
    out = {}
    for k in PHYS_KEYS:
        v = ((entry or {}).get("phys") or {}).get(k)
        if v and v.get("value") not in (None, ""):
            out[k] = (v["value"], v.get("ref") or "")
    return out


def write_csv(items=None, folder=DIR):
    """favorites/favorites.csv: one row per favorite (status, note, added, site, the search record, size data)."""
    import csv
    items = load(folder) if items is None else items
    rec_cols = []
    for e in items:
        rec_cols += [k for k in e["record"] if k not in rec_cols]
    cols = (["key", "status", "note", "added", "site", "site_lat", "site_lon", "site_ele"] + rec_cols
            + [f"sbdb_{k}" for k in PHYS_KEYS] + ["kml", "preview_svg", "globe_svg"])
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for e in items:
            site, files, ph = e.get("site") or {}, e.get("files") or {}, e.get("phys") or {}
            row = dict(key=e["key"], status=e.get("status", ""), note=e.get("note", ""), added=e.get("added", ""),
                       site=site.get("name", ""), site_lat=site.get("lat", ""), site_lon=site.get("lon", ""),
                       site_ele=site.get("ele", ""), kml=files.get("kml", ""), preview_svg=files.get("svg", ""),
                       globe_svg=files.get("globe", ""))
            row.update({k: v for k, v in e["record"].items() if k in rec_cols})
            row.update({f"sbdb_{k}": (ph.get(k) or ["", ""])[0] for k in PHYS_KEYS})
            w.writerow(row)
    os.replace(tmp, os.path.join(folder, "favorites.csv"))


def keys(folder=DIR):
    return [e["key"] for e in load(folder)]


def add(record, run=None, map_dir="maps", folder=DIR, sbdb=None):
    """Add an event (record: a hits_log row as a dict; run: the run summary of its search, or None; sbdb: the
    asteroid's size-cache entry from sbdb, kept with the favorite). Copies its KML and preview from map_dir.
    Returns (ok, message)."""
    try:
        key = key_of(record["target_id"], record["best_utc"])
    except KeyError as ex:
        return False, f"not an event record (no {ex})"
    items = load(folder)
    if any(e["key"] == key for e in items):
        return False, f"{key} is already a favorite"
    own = os.path.join(folder, key)
    os.makedirs(own, exist_ok=True)
    files = {}
    for ext, pat in (("kml", "*.kml"), ("svg", "*.svg"), ("globe", "*_globe.svg")):
        found = sorted(glob.glob(os.path.join(glob.escape(map_dir), f"{glob.escape(key)}{pat}")))
        if ext == "svg":
            found = [f for f in found if not f.endswith("_globe.svg")]    # the preview, not the globe plot
        if found:
            dst = os.path.join(own, os.path.basename(found[0]))
            shutil.copyfile(found[0], dst)
            files[ext] = os.path.relpath(dst, folder).replace(os.sep, "/")
    run = run or {}
    entry = dict(key=key, added=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), version=__version__,
                 status="planned", note="",
                 record=record, site=run.get("site"), files=files,
                 phys=phys_of(sbdb), phys_src=(sbdb or {}).get("source", ""),
                 run={k: run.get(k) for k in ("run_utc", "window_start", "window_days", "limits", "earth_pck",
                                               "targets_from") if k in run})
    items.insert(0, entry)
    _save(items, folder)
    name = (record.get("target_name") or record["target_id"]).strip()
    return True, f"added to favorites: {name}, {str(record['best_utc'])[:19]} UT" + (
        "" if files else " (no map or preview found to copy)")


def update(key, folder=DIR, **fields):
    """Set status and/or note of a favorite. Returns (ok, message)."""
    items = load(folder)
    for e in items:
        if e["key"] == key:
            if "status" in fields and fields["status"] not in STATUSES:
                return False, f"status must be one of {', '.join(STATUSES)}"
            e.update({k: v for k, v in fields.items() if k in ("status", "note")})
            _save(items, folder)
            return True, f"{key} saved"
    return False, f"{key} is not a favorite"


def remove(key, folder=DIR):
    """Drop a favorite and its copied files. Returns (ok, message)."""
    items = load(folder)
    rest = [e for e in items if e["key"] != key]
    if len(rest) == len(items):
        return False, f"{key} is not a favorite"
    _save(rest, folder)
    shutil.rmtree(os.path.join(folder, key), ignore_errors=True)
    return True, f"{key} removed"


def update_many(keys_, folder=DIR, **fields):
    """Set status and/or note of several favorites. Returns (ok, message)."""
    if "status" in fields and fields["status"] not in STATUSES:
        return False, f"status must be one of {', '.join(STATUSES)}"
    items, want, n = load(folder), set(keys_), 0
    for e in items:
        if e["key"] in want:
            e.update({k: v for k, v in fields.items() if k in ("status", "note")})
            n += 1
    if n:
        _save(items, folder)
    return n > 0, f"{n} favorite{'s' if n != 1 else ''} updated" if n else "none of these is a favorite"


def remove_many(keys_, folder=DIR):
    """Drop several favorites and their copied files. Returns (ok, message)."""
    items, want = load(folder), set(keys_)
    rest = [e for e in items if e["key"] not in want]
    n = len(items) - len(rest)
    if n:
        _save(rest, folder)
        for k in want:
            shutil.rmtree(os.path.join(folder, k), ignore_errors=True)
    return n > 0, f"{n} favorite{'s' if n != 1 else ''} removed" if n else "none of these is a favorite"


def cleanup(before=None, folder=DIR):
    """Remove every favorite whose event is before `before` (ISO date, default: today UTC). Returns (ok, message)."""
    day = before or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    old = [e["key"] for e in load(folder) if str(e["record"].get("best_utc", ""))[:10] < day]
    if not old:
        return True, f"no favorites before {day}"
    ok, msg = remove_many(old, folder)
    return ok, f"{msg} (events before {day})"


def write_page(folder=DIR, tiles=None):
    """favorites/favorites.html: the favorites as a report table (as the Results page, plus select box, site, status,
    note, added) with the same tools, using each favorite's own map and preview copies. Returns the path."""
    from pyoccult import report as R
    events, paths, sites = [], {}, set()
    for f in load(folder):
        r, site = f["record"], f.get("site") or {}
        own = os.path.join(folder, f["key"])
        try:
            e = R.build_event(r, site.get("lat"), site.get("lon"), own, folder)
        except (KeyError, ValueError):
            continue
        e.update(fav=dict(key=f["key"], status=f.get("status", ""), note=f.get("note", ""), added=f.get("added", "")),
                 site=site)
        if e["kml_abs"]:
            try:
                paths[f["key"]] = R.kml_to_data(e["kml_abs"])
                e["pkey"] = f["key"]
            except Exception:
                pass
        sites.add(site.get("name", "?"))
        events.append(e)
    events.sort(key=lambda e: e["when"])
    span = (f" from {min(e['when'] for e in events):%Y-%m-%d} to {max(e['when'] for e in events):%Y-%m-%d}"
            if events else "")
    meta = dict(title="PyOccult favorites", span=span, sort="date", info=None,
                observer=f"{len(sites)} site{'s' if len(sites) != 1 else ''}: {', '.join(sorted(sites))}" if sites
                else "no favorites yet: add events with the star button in the Results report",
                generated=datetime.now().strftime("%Y-%m-%d %H:%M"), paths=paths, tiles=tiles or U.URL_OSM_TILES,
                obs=None, site=None,
                favorites=True, statuses=STATUSES)
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, "favorites.html")
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(R.to_html(events, meta))
    os.replace(tmp, out)
    return out


def backfill_phys(lookup, folder=DIR):
    """Give favorites SBDB's full physical data (size, and shape and rotation where known): lookup(target_id) ->
    size-cache entry or None (sbdb.get_full). Done once per favorite: 'phys_src' notes that the entry came
    from the per-object SBDB API (bulk rows of the pick tool hold only the size; offline, it is tried again next
    time). Saves (and rewrites the CSV) only if something changed. Returns the number updated."""
    items, n = load(folder), 0
    for e in items:
        if e.get("phys_src") == "sbdb.api":
            continue
        entry = lookup(str(e["record"].get("target_id", "")).strip())
        if not entry:
            continue
        e["phys"] = {**(e.get("phys") or {}), **phys_of(entry)}
        e["phys_src"], n = entry.get("source", ""), n + 1
    if n:
        _save(items, folder)
    return n


def backfill_globes(map_dir="maps", folder=DIR):
    """Give favorites added before globe plots existed the plot of a later search (<key>*_globe.svg in map_dir),
    copied into their own folder. Returns the number added."""
    items, n = load(folder), 0
    for e in items:
        files = e.setdefault("files", {})
        if "globe" in files:
            continue
        found = sorted(glob.glob(os.path.join(glob.escape(map_dir), f"{glob.escape(e['key'])}*_globe.svg")))
        if found:
            own = os.path.join(folder, e["key"])
            os.makedirs(own, exist_ok=True)
            dst = os.path.join(own, os.path.basename(found[0]))
            shutil.copyfile(found[0], dst)
            files["globe"], n = os.path.relpath(dst, folder).replace(os.sep, "/"), n + 1
    if n:
        _save(items, folder)
    return n


def backfill_timezones(lookup, folder=DIR):
    """Give each favorite's site its IANA time zone (for showing site times): lookup(lat, lon) -> name or None,
    called once per distinct site position. Saves only if something changed. Returns the number filled in."""
    items, n, cache = load(folder), 0, {}
    for e in items:
        site = e.get("site") or {}
        if site.get("tz") or site.get("lat") is None or site.get("lon") is None:
            continue
        key = (round(float(site["lat"]), 3), round(float(site["lon"]), 3))
        if key not in cache:
            cache[key] = lookup(site["lat"], site["lon"])
        if cache[key]:
            site["tz"], n = cache[key], n + 1
    if n:
        _save(items, folder)
    return n


def size_text(entry):
    """'D 3.04 km (2.81-3.27 km, SBDB diameter, NEOWISE) · H 14.03 · albedo 0.06': the size the search used (from
    its record: radius and range, source) and the cached SBDB data kept with the favorite."""
    r, ph = entry["record"], entry.get("phys") or {}
    parts = []
    try:
        d, lo, hi = (2 * float(r[k]) for k in ("r_km", "r_min_km", "r_max_km"))
        src = (r.get("size_source") or "").split(" (ref")[0].strip()
        if "neowise" in (r.get("size_source") or "").lower():
            src += ", NEOWISE"
        parts.append(f"D {d:.2f} km ({lo:.2f}-{hi:.2f} km" + (f", {src})" if src else ")"))
    except (KeyError, TypeError, ValueError):
        pass
    for k, label in (("H", "H"), ("albedo", "albedo")):
        if k in ph:
            parts.append(f"{label} {ph[k][0]}")
    if str(r.get("size_source") or "").lower().startswith("h only"):
        parts.append("* estimate, uncertain by a factor ~1.7")
    return " · ".join(parts)


def shape_text(entry):
    """'axes 18.2 x 10.5 x 8.9 km · rotation 5.27 h · pole (300, 25) · type S': shape and rotation data from SBDB kept
    with the favorite, where known (most small asteroids have none). Empty string if there is nothing."""
    ph, parts = entry.get("phys") or {}, []
    if "extent" in ph:
        parts.append(f"axes {str(ph['extent'][0]).replace('x', ' x ')} km")
    if "rot_per" in ph:
        parts.append(f"rotation {ph['rot_per'][0]} h")
    if "pole" in ph:
        parts.append(f"pole {ph['pole'][0]}")
    tax = ph.get("spec_T") or ph.get("spec_B")
    if tax:
        parts.append(f"type {tax[0]}")
    return " · ".join(parts)


def find_record(csv_path, target_id, best_utc):
    """The hits_log row (dict) of this event, matched by target and event minute, or None."""
    import csv
    want = key_of(target_id, best_utc)
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if key_of(r.get("target_id", ""), r.get("best_utc", "")) == want:
                    return r
    except OSError:
        pass
    return None


def main():
    from pyoccult.home import HOME
    os.chdir(HOME)
    if sys.argv[1:2] != ["list"]:
        sys.exit(__doc__)
    for e in load():
        r, s = e["record"], e.get("site") or {}
        print(f"{e['key']:24s} {e['status']:9s} {(r.get('target_name') or '')[:28]:28s} site {s.get('name', '?'):12s} "
              f"G {float(r.get('mag') or 0):5.2f}  {e['note'][:40]}")


if __name__ == "__main__":
    sys.exit(main())
