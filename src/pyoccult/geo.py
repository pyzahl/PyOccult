"""geo.py - approximate observer positions: from the IP address (ipinfo.io), a place name (Open-Meteo geocoding),
observatories with their MPC codes (Minor Planet Center), ground elevation and time zone (Open-Meteo). Used by setup.py and
gui.py. Standard library only.

All results are approximate: IP positions are city level (10-100 km off, wrong behind a VPN), place names give the town
centre. Use an exact position (GPS, map) for observing.
"""
from pyoccult.version import __version__
from pyoccult import net                      # https with certifi's certificate authorities
from pyoccult import urls as U
import json, urllib.parse, urllib.request


def get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "PyOccult"})
    with net.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def elevation(lat, lon):
    """Ground elevation (m) from Open-Meteo, or None."""
    try:
        return float(get_json(f"{U.URL_OPENMETEO_ELEVATION}?latitude={lat}&longitude={lon}")["elevation"][0])
    except Exception:
        return None


MPC_OBSCODES_URL = U.URL_MPC_OBSCODES
_MPC = None


def mpc_geodetic(lon_e, rho_cos, rho_sin, a=6378.137, f=1 / 298.257223563):
    """(lat_deg, lon_deg in -180..180, height_m) from the MPC parallax constants rho*cos(phi'), rho*sin(phi') (in Earth
    equatorial radii) and the east longitude; geodetic on the WGS84 ellipsoid (iterative)."""
    import math
    x, z = rho_cos * a, rho_sin * a
    e2 = f * (2 - f)
    lat = math.atan2(z, x * (1 - e2))
    for _ in range(8):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        h = x / math.cos(lat) - n if abs(math.cos(lat)) > 1e-9 else abs(z) - n * (1 - e2)
        lat = math.atan2(z, x * (1 - e2 * n / (n + h)))
    return math.degrees(lat), (lon_e + 180.0) % 360.0 - 180.0, h * 1000.0


def mpc_observatories(folder="data", url=MPC_OBSCODES_URL):
    """The MPC observatory codes (Minor Planet Center ObsCodes.html: about 2500 observatories with their official
    code) as a list of dicts code, name, lat, lon, ele (m), ele_ok, sorted by code. Downloaded once into
    <folder>/ObsCodes.html (not in git), then read from there; [] if neither works. Codes without a position
    (spacecraft, roving observers) are skipped. ele_ok is False when the parallax constants have fewer than 5
    decimals: the height is then only good to about a kilometre (look it up instead)."""
    global _MPC
    if _MPC is not None:
        return _MPC
    import os, tempfile
    path = os.path.join(folder, "ObsCodes.html")
    if not os.path.isfile(path):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PyOccult"})
            with net.urlopen(req, timeout=30) as r:
                data = r.read()
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except Exception:
            return []
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\r\n")
                code, lon_s, c_s, s_s, name = line[0:3], line[4:13], line[13:21], line[21:30], line[30:].strip()
                if len(line) < 31 or not code.strip() or code == "Cod" or not lon_s.strip() or not c_s.strip():
                    continue
                try:
                    lon_e, rc, rs = float(lon_s), float(c_s), float(s_s)
                except ValueError:
                    continue
                if rc == 0.0 and rs == 0.0:                                 # geocentric (500)
                    continue
                lat, lon, ele = mpc_geodetic(lon_e, rc, rs)
                dec = min(len(c_s.strip().split(".")[-1]), len(s_s.strip().lstrip("+-").split(".")[-1]))
                out.append(dict(code=code.strip(), name=name, lat=lat, lon=lon, ele=ele, ele_ok=dec >= 5))
    except OSError:
        return []
    _MPC = sorted(out, key=lambda o: o["code"])
    return _MPC


def timezone(lat, lon):
    """IANA time zone name at a place (e.g. "Europe/Zurich") from Open-Meteo, or None."""
    try:
        return get_json(f"{U.URL_OPENMETEO_FORECAST}?latitude={lat}&longitude={lon}"
                        f"&timezone=auto&forecast_days=1&daily=sunrise").get("timezone") or None
    except Exception:
        return None


def ip_location():
    """(lat, lon, ele, label) from the IP address, or None. Sends the IP address to ipinfo.io."""
    try:
        d = get_json(U.URL_IPINFO)
        lat, lon = (float(x) for x in d["loc"].split(","))
        return lat, lon, elevation(lat, lon), ", ".join(x for x in (d.get("city"), d.get("region"), d.get("country")) if x)
    except Exception:
        return None


def places(name, count=5):
    """Places matching a name: list of (lat, lon, ele, label), best first (Open-Meteo geocoding). Empty if none/offline."""
    try:
        res = get_json(U.URL_OPENMETEO_GEOCODING + "?"
                       + urllib.parse.urlencode(dict(name=name, count=count))).get("results", [])
    except Exception:
        return []
    return [(r["latitude"], r["longitude"], r.get("elevation"),
             ", ".join(x for x in (r["name"], r.get("admin1"), r.get("country")) if x)) for r in res]
