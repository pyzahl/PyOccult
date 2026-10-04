"""pyoccult_geo.py - approximate observer positions: from the IP address (ipinfo.io), a place name (Open-Meteo geocoding)
and ground elevation (Open-Meteo). Used by pyoccult_setup.py and pyoccult_gui.py. Standard library only.

All results are approximate: IP positions are city level (10-100 km off, wrong behind a VPN), place names give the town
centre. Use an exact position (GPS, map) for observing.
"""
from pyoccult_version import __version__
import json, urllib.parse, urllib.request


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
