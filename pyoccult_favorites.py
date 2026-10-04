"""pyoccult_favorites.py - a hand-picked list of events from any search and any site, kept with everything known.

    favorites/favorites.json                    the list (one entry per event, newest first)
    favorites/<target>_<YYYYMMDDTHHMM>/          the event's own copies of its KML ground track and preview SVG

An entry holds the full hits_log record, the site and the run context of the search it came from, when it was added,
a status (planned / observed / cancelled / clouded) and a note. Map and preview are copies, so later searches (which
overwrite or delete files in maps/) never change a favorite. Private (site names): favorites/ is in .gitignore.
Used by pyoccult_gui.py (report star buttons, Favorites tab). Standard library only.

    python pyoccult_favorites.py list
"""
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


def keys(folder=DIR):
    return [e["key"] for e in load(folder)]


def add(record, run=None, map_dir="maps", folder=DIR):
    """Add an event (record: a hits_log row as a dict; run: the run summary of its search, or None). Copies its KML
    and preview from map_dir. Returns (ok, message)."""
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
    for ext in ("kml", "svg"):
        found = sorted(glob.glob(os.path.join(glob.escape(map_dir), f"{glob.escape(key)}*.{ext}")))
        if found:
            dst = os.path.join(own, os.path.basename(found[0]))
            shutil.copyfile(found[0], dst)
            files[ext] = os.path.relpath(dst, folder).replace(os.sep, "/")
    run = run or {}
    entry = dict(key=key, added=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), status="planned", note="",
                 record=record, site=run.get("site"), files=files,
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


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if sys.argv[1:2] != ["list"]:
        sys.exit(__doc__)
    for e in load():
        r, s = e["record"], e.get("site") or {}
        print(f"{e['key']:24s} {e['status']:9s} {(r.get('target_name') or '')[:28]:28s} site {s.get('name', '?'):12s} "
              f"G {float(r.get('mag') or 0):5.2f}  {e['note'][:40]}")
