"""pyoccult_sbdb.py - shared on-disk cache of per-asteroid SBDB physical data (diameter, extent, H, G, albedo, name).

One JSON file, <cache_path>/PyOccult_sbdb_phys.json, keyed by asteroid number:
    {"19": {"fetched": unix time, "source": "sbdb.api" | "sbdb_query", "phys": {name: {"value", "sigma", "ref"}, ...,
                                                                               "_fullname": "19 Fortuna (A852 QA)"}}}
Written by pyoccult.py (per-object SBDB API, all fields with references) and by pyoccult_pick.py (from its bulk
download: diameter, diameter sigma, extent, albedo, H, G, name; no references). pyoccult.get_asteroid_size() derives the
size from it, the same way for either source. The raw data is cached, not the derived size, so SIZE_OVERRIDES and the
size rules always apply. Entries older than sbdb_max_age_days (config, default 30) are refetched.

Standard library only (the pick tool must not need SPICE/astropy).
"""
from pyoccult_version import __version__
import json, os, tempfile, time

FILE = "PyOccult_sbdb_phys.json"
BULK_FIELDS = ["diameter", "diameter_sigma", "extent", "albedo", "H", "G"]     # needed in the pick tool's bulk query


def _config(name, default):
    try:
        import pyoccult_config
        return getattr(pyoccult_config, name, default)
    except ImportError:
        return default


def cache_file(cache_path=None):
    return os.path.join(cache_path or _config("cache_path", tempfile.gettempdir()), FILE)


def max_age_s(max_age_days=None):
    return float(_config("sbdb_max_age_days", 30) if max_age_days is None else max_age_days) * 86400.0


def load(cache_path=None):
    try:
        with open(cache_file(cache_path)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get(number, cache_path=None, max_age_days=None):
    """(entry, fresh) for one asteroid; entry is None if not cached."""
    e = load(cache_path).get(str(number).strip())
    return e, bool(e) and time.time() - e.get("fetched", 0) < max_age_s(max_age_days)


def put(entries, cache_path=None, keep_newer=True):
    """Merge {number: entry} into the cache file (atomic). keep_newer: an existing entry fetched later is kept, so a
    bulk import never replaces a newer per-object lookup."""
    path = cache_file(cache_path)
    cache = load(cache_path)                                  # re-read: keep entries written meanwhile
    n_new = 0
    for k, e in entries.items():
        old = cache.get(str(k))
        if keep_newer and old and old.get("fetched", 0) > e.get("fetched", 0):
            continue
        cache[str(k)] = e
        n_new += 1
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(cache, f)
    os.replace(tmp, path)
    return n_new


def entry_from_api(js, fetched=None):
    """Cache entry from one sbdb.api reply (with phys-par=1)."""
    phys = {q["name"]: q for q in js.get("phys_par", [])}
    phys["_fullname"] = js.get("object", {}).get("fullname")
    return dict(fetched=fetched or time.time(), source="sbdb.api", phys=phys)


def entry_from_bulk(row, fetched):
    """Cache entry from one sbdb_query row (dict field -> value), in the same layout as entry_from_api."""
    phys = {}
    for name in ("diameter", "extent", "albedo", "H", "G"):
        v = row.get(name)
        if v not in (None, ""):
            phys[name] = dict(name=name, value=str(v), sigma=None, ref="SBDB bulk query")
    if "diameter" in phys and row.get("diameter_sigma") not in (None, ""):
        phys["diameter"]["sigma"] = str(row["diameter_sigma"])
    phys["_fullname"] = (row.get("full_name") or "").strip() or None
    return dict(fetched=fetched, source="sbdb_query", phys=phys)
