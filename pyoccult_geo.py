"""pyoccult_geo.py - approximate observer positions: from the IP address (ipinfo.io), a place name (Open-Meteo geocoding),
Occult's site list (occultations.org), ground elevation and time zone (Open-Meteo). Used by pyoccult_setup.py and
pyoccult_gui.py. Standard library only.

All results are approximate: IP positions are city level (10-100 km off, wrong behind a VPN), place names give the town
centre. Use an exact position (GPS, map) for observing.
"""
from pyoccult_version import __version__
import io, json, os, re, tempfile, urllib.parse, urllib.request, zipfile


def get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "PyOccult"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def elevation(lat, lon):
    """Ground elevation (m) from Open-Meteo, or None."""
    try:
        return float(get_json(f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}")["elevation"][0])
    except Exception:
        return None


OCCULT_SITES_URL = "https://www.occultations.org/sw/occult/InstallSites.zip"
_SITE_LINE = re.compile(r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+)\s+(\d+)\s+(-?\d+\.\d+)\s+(\d+)\s(.{32})\s(\d)\s(.{9})"
                        r"\s*(-?\d+\.?\d*)\s+(\d+)\s*$")
_OCCULT_SITES = None


def occult_sites(folder="data", url=OCCULT_SITES_URL):
    """Occult's site list (the InstallSites.zip of Occult / OWC: about 890 reference places and observatories in
    regional .site files) as a list of dicts name, region, lat, lon, ele (m), tz (hours), sorted by name, duplicates
    between regions merged. Downloaded once into <folder>/InstallSites.zip (not in git), then read from there; [] if
    neither works. File columns: lon (east +), lat, height m, aperture cm, mag correction, ?, name (32), ?, short name
    (9), time zone hours, ?."""
    global _OCCULT_SITES
    if _OCCULT_SITES is not None:
        return _OCCULT_SITES
    path = os.path.join(folder, "InstallSites.zip")
    if not os.path.isfile(path):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PyOccult"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except Exception:
            return []
    out, seen = [], set()
    try:
        with zipfile.ZipFile(path) as z:
            for member in sorted(n for n in z.namelist() if n.lower().endswith(".site")):
                region = os.path.splitext(os.path.basename(member))[0]
                for line in io.TextIOWrapper(z.open(member), encoding="latin-1"):
                    m = _SITE_LINE.match(line.rstrip("\r\n"))
                    name = m[7].strip() if m else ""
                    if not m or not name or name.startswith("_"):
                        continue
                    lat, lon = float(m[2]), float(m[1])
                    key = (name.lower(), round(lat, 3), round(lon, 3))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(dict(name=name, region=region, lat=lat, lon=lon, ele=float(m[3]), tz=float(m[10])))
    except (OSError, zipfile.BadZipFile):
        return []
    _OCCULT_SITES = sorted(out, key=lambda s: (s["name"].lower(), s["region"]))
    return _OCCULT_SITES


def timezone(lat, lon):
    """IANA time zone name at a place (e.g. "Europe/Zurich") from Open-Meteo, or None."""
    try:
        return get_json(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                        f"&timezone=auto&forecast_days=1&daily=sunrise").get("timezone") or None
    except Exception:
        return None


def ip_location():
    """(lat, lon, ele, label) from the IP address, or None. Sends the IP address to ipinfo.io."""
    try:
        d = get_json("https://ipinfo.io/json")
        lat, lon = (float(x) for x in d["loc"].split(","))
        return lat, lon, elevation(lat, lon), ", ".join(x for x in (d.get("city"), d.get("region"), d.get("country")) if x)
    except Exception:
        return None


def places(name, count=5):
    """Places matching a name: list of (lat, lon, ele, label), best first (Open-Meteo geocoding). Empty if none/offline."""
    try:
        res = get_json("https://geocoding-api.open-meteo.com/v1/search?"
                       + urllib.parse.urlencode(dict(name=name, count=count))).get("results", [])
    except Exception:
        return []
    return [(r["latitude"], r["longitude"], r.get("elevation"),
             ", ".join(x for x in (r["name"], r.get("admin1"), r.get("country")) if x)) for r in res]
