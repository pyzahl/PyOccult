#!/usr/bin/env python3
"""pyoccult_report.py - turn PyOccult's hits_log.csv into a readable event list (HTML or Markdown).

Columns follow the Occult Watcher (OWC) list - asteroid, event time (UT), star magnitude, magnitude
drop, maximum duration, star altitude with compass direction, Moon distance with phase icon - plus the
observer's offset from the shadow centre line and a link to the KML ground-track file.

Standard library only. Usage:

    python pyoccult_report.py hits_log.csv                       # -> hits_report.html next to the CSV
    python pyoccult_report.py hits_log.csv -o events.html --kml-dir maps --max-miss 50 --min-drop 0.5
    python pyoccult_report.py hits_log.csv --format md           # Markdown table instead
    python pyoccult_report.py hits_log.csv --sort date           # by event time (default: by star magnitude)

The observer position (needed only for the compass direction) comes from pyoccult_config.py (LAT, LON)
if that file is importable, or from --lat / --lon (east-positive degrees).

KML files are looked up as  <kml-dir>/<target_id>_<YYYYMMDD>T<HHMM>*.kml , i.e. the name that
pyoccult_paths.write_shadow_kml() is given in the pipeline hook (best_utc truncated to the minute).

For every event with a KML file the HTML page gets a "Map" button: an interactive map (Leaflet + OpenStreetMap
tiles, loaded from the internet when the button is first used) showing the shadow centre line, the shadow
limits, the 3-sigma limits and the observer. The path data is embedded in the page, so it works when the file
is opened straight from disk. A link opens the closest centre-line point in Google Maps. --no-embed turns it off.
"""
import argparse
import csv
import glob
import html
import json
import math
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
MOON_ICONS = "🌑🌒🌓🌔🌕🌖🌗🌘"          # moon_age_deg: 0 new, 90 first quarter, 180 full, 270 last quarter
NEAR_KM = 10.0                            # misses closer than this to the shadow edge get the amber tag


# ---------------------------------------------------------------- reading the log

def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def read_log(path):
    """Rows as dicts. Tolerates repeated header lines (columns get added over time) and short/long rows."""
    rows, header, skipped = [], None, 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.reader(f):
            if not raw or not any(c.strip() for c in raw):
                continue
            if raw[0].strip() == "target_id":
                header = [c.strip() for c in raw]
                continue
            if header is None or len(raw) != len(header):
                skipped += 1
                continue
            rows.append(dict(zip(header, raw)))
    return rows, skipped


def read_last_run(csv_path):
    """The last run summary pyoccult.py appended to <hits log>.runs.jsonl, or None."""
    path = os.path.splitext(csv_path)[0] + ".runs.jsonl"
    try:
        with open(path) as f:
            lines = [ln for ln in f if ln.strip()]
        return json.loads(lines[-1]) if lines else None
    except (OSError, ValueError):
        return None


def header_info(run, lat, lon):
    """(label, text) lines for the page header: site, equipment, limits, run statistics."""
    if not run:
        if lat is None or lon is None:
            return []
        return [("Site", f"{abs(lat):.4f}°{'N' if lat >= 0 else 'S'} {abs(lon):.4f}°{'E' if lon >= 0 else 'W'}"
                         " (no run summary found)")]
    s, L = run["site"], run["limits"]
    ns, ew = ("N" if s["lat"] >= 0 else "S"), ("E" if s["lon"] >= 0 else "W")
    out = [("Site", f"{s['name']}" + (f" ({s['desc']})" if s.get("desc") else "") +
            f": {abs(s['lat']):.4f}°{ns} {abs(s['lon']):.4f}°{ew}, {s['ele']:g} m"),
           ("Equipment", f"{s['aperture_cm']:g} cm aperture, {s['frames']} detection frames, MagAdjust "
                         f"{s['mag_adjust']:+g}, extinction " +
                         (f"{s['extinction']:g} mag/airmass" if s["extinction"] else "off")),
           ("Limits", f"stars G ≤ {L['mag_limit']:g}, star altitude ≥ {L['min_star_alt']:g}°, Sun ≤ "
                      f"{L['max_sun_alt']:g}°, reach {L['reach_km']:g} km, drop ≥ {L['min_mag_drop']:g} mag, "
                      f"duration ≥ {L['min_dur_s']:g} s"),
           ("Run", f"{run['run_utc']} UT, {run['window_start'][:10]} + {run['window_days']:g} d, {run['targets']} asteroids, "
                   f"{run['candidates']} candidates, {run['solves']} exact solves, {run['hits']} hits"
                   + (f"; targets: {run['targets_from']}" if run.get("targets_from") else "")),
           ("Timing", f"total {run['total_s']:.1f} s: start-up {run['startup_s']:.1f} s, asteroid data "
                      f"{run['init_s']:.1f} s, search {run['search_s']:.1f} s (maps {run['maps_s']:.1f} s); "
                      f"{run['per_asteroid_s']:.2f} s per asteroid, {run['per_solve_s'] * 1000:.0f} ms search time per "
                      f"exact solve" + (f", {run['calc_per_hit_s'] * 1000:.0f} ms calculation per hit"
                                        if "calc_per_hit_s" in run else ""))]
    if run.get("earth_pck"):
        out.append(("Earth orientation", earth_pck_text(run["earth_pck"], run)))
    return out


def earth_pck_text(e, run):
    """Coverage of the Earth orientation file the run used, and which part of it the search window falls in."""
    from datetime import date, timedelta
    last, stop = e.get("last_datum"), (e.get("stop") or "")[:10]
    txt = (f"earth_latest_high_prec.bpc of {(e.get('created') or '?')[:10]}: measured to {last or '?'}, "
           f"predicted to {stop or '?'}")
    try:
        w0 = date.fromisoformat(run["window_start"][:10])
        w1 = (w0 + timedelta(days=float(run["window_days"]))).isoformat()
    except (KeyError, ValueError):
        return txt
    if last and w1 <= last:
        part = "measured values"
    elif last and w0.isoformat() >= last:
        part = "predicted values"
    else:
        part = f"measured values up to {last}, predicted after" if last else "?"
    return txt + f"; this window ({w0.isoformat()} to {w1}) uses {part}"


def asteroid_label(target_id, name):
    """'218001 (2001 XQ72)' -> '(218001) 2001 XQ72';  '4272 Entsuji (1977 EG5)' -> '(4272) Entsuji'."""
    name = (name or "").strip()
    if name.startswith(("Numbered Asteroid", "Unnumbered")):
        name = ""
    m = re.match(r"^\(?\d+\)?\s*(.*)$", name)
    rest = m.group(1).strip() if m else name
    if rest.startswith("(") and rest.endswith(")") and rest.count("(") == 1:
        rest = rest[1:-1]                                        # only a provisional designation
    else:
        rest = re.sub(r"\s*\([^()]*\)\s*$", "", rest)            # a name is known: drop the designation
    return f"({target_id}) {rest}".strip()


# ---------------------------------------------------------------- azimuth (stdlib spherical astronomy)

def julian_date(dt):
    return 2440587.5 + (dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() / 86400.0


def precess_j2000(ra, dec, jd):
    """J2000 -> mean equator/equinox of date (IAU 1976, Meeus ch. 21); radians."""
    T = (jd - 2451545.0) / 36525.0
    s = lambda arcsec: math.radians(arcsec / 3600.0)
    zeta = s(2306.2181 * T + 0.30188 * T**2 + 0.017998 * T**3)
    z = s(2306.2181 * T + 1.09468 * T**2 + 0.018203 * T**3)
    theta = s(2004.3109 * T - 0.42665 * T**2 - 0.041833 * T**3)
    A = math.cos(dec) * math.sin(ra + zeta)
    B = math.cos(theta) * math.cos(dec) * math.cos(ra + zeta) - math.sin(theta) * math.sin(dec)
    C = math.sin(theta) * math.cos(dec) * math.cos(ra + zeta) + math.cos(theta) * math.sin(dec)
    return math.atan2(A, B) + z, math.asin(max(-1.0, min(1.0, C)))


def alt_az(ra_deg, dec_deg, when, lat_deg, lon_deg):
    """Altitude and azimuth (deg, from north through east) of a J2000 position. UT1 taken as UTC; no
    nutation/aberration (error well under 0.1 deg) - fine for a compass direction."""
    jd = julian_date(when)
    ra, dec = precess_j2000(math.radians(ra_deg), math.radians(dec_deg), jd)
    T = (jd - 2451545.0) / 36525.0
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - T**3 / 38710000.0) % 360.0
    H = math.radians(gmst + lon_deg) - ra
    phi = math.radians(lat_deg)
    sin_alt = math.sin(dec) * math.sin(phi) + math.cos(dec) * math.cos(phi) * math.cos(H)
    alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    az = math.degrees(math.atan2(-math.cos(dec) * math.sin(H),
                                 math.sin(dec) * math.cos(phi) - math.cos(dec) * math.sin(phi) * math.cos(H))) % 360.0
    return alt, az


def compass(az):
    return COMPASS[int((az + 22.5) // 45) % 8]


# ---------------------------------------------------------------- building events

def find_kml(kml_dir, target_id, when, ext="kml"):
    """<kml_dir>/<target>_<YYYYMMDDTHHMM>*.<ext>: the KML ground track, or with ext="svg" the event preview."""
    if not kml_dir or not os.path.isdir(kml_dir):
        return None
    stamp = when.strftime("%Y%m%dT%H%M")
    found = sorted(glob.glob(os.path.join(glob.escape(kml_dir), f"{glob.escape(str(target_id))}_{stamp}*.{ext}")))
    return found[0] if found else None


KML_NS = "{http://www.opengis.net/kml/2.2}"
LINE_STYLES = (("Centre", "#15803d", 3, None), ("Shadow limit", "#dc2626", 2, None), ("1-sigma", "#7c3aed", 1.5, "2 4"),
               ("3-sigma", "#d97706", 2, "6 6"))


def kml_to_data(path):
    """Lines and pins of a pyoccult_paths KML as a compact dict ([lat, lon] order, ~1 m precision).
    Line colours are re-mapped to map-friendly ones (the KML uses neon colours meant for Google Earth)."""
    root = ET.parse(path).getroot()
    lines, pins = [], []
    for pm in root.iter(KML_NS + "Placemark"):
        name = (pm.findtext(KML_NS + "name") or "").strip()
        ls = pm.find(f".//{KML_NS}LineString/{KML_NS}coordinates")
        pt = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")
        if ls is not None and ls.text:
            pts = []
            for tok in ls.text.split():
                c = tok.split(",")
                if len(c) >= 2:
                    pts.append([round(float(c[1]), 5), round(float(c[0]), 5)])
            color, width, dash = "#2563eb", 2, None
            for prefix, col, w, d in LINE_STYLES:
                if name.startswith(prefix):
                    color, width, dash = col, w, d
            lines.append(dict(name=name, color=color, width=width, dash=dash, pts=pts))
        elif pt is not None and pt.text:
            c = pt.text.strip().split(",")
            pins.append(dict(name=name, desc=(pm.findtext(KML_NS + "description") or "").strip(),
                             lat=round(float(c[1]), 5), lon=round(float(c[0]), 5)))
    return dict(lines=lines, pins=pins)


def build_event(r, lat, lon, kml_dir, out_dir):
    when = datetime.fromisoformat(r["best_utc"].strip().rstrip("Z")).replace(tzinfo=timezone.utc)
    tid = r["target_id"].strip()
    mag, drop = num(r.get("mag")), num(r.get("mag_drop"))
    speed, rad = num(r.get("speed_kms")), num(r.get("r_km"))
    dur = num(r.get("max_duration_s"))
    if dur is None and speed and rad is not None:
        dur = 2 * rad / speed
    alt, az = num(r.get("star_alt")), num(r.get("star_az"))
    ra, dec = num(r.get("star_ra")), num(r.get("star_dec"))
    if az is None and None not in (ra, dec, lat, lon):
        calc_alt, az = alt_az(ra, dec, when, lat, lon)
        alt = calc_alt if alt is None else alt
    moon = None
    if (num(r.get("moon_alt_deg")) or -1) > 0 and num(r.get("moon_sep_deg")) is not None:
        age = num(r.get("moon_age_deg"))
        icon = MOON_ICONS[int(round(age / 45.0)) % 8] if age is not None else "🌙"
        illum = num(r.get("moon_illum_pct"))
        moon = dict(icon=icon, sep=num(r["moon_sep_deg"]), alt=num(r["moon_alt_deg"]), illum=illum)
    kml_abs = find_kml(kml_dir, tid, when)
    prev_abs = find_kml(kml_dir, tid, when, "svg")
    fov = 2.0                                                    # deg; the preview's field when there is one
    if prev_abs:
        try:
            with open(prev_abs, encoding="utf-8") as f:
                m = re.search(r"field (\d+(?:\.\d+)?)\u2032", f.read())
            fov = float(m[1]) / 60.0 if m else fov
        except OSError:
            pass
    preview = urllib.parse.quote(os.path.relpath(prev_abs, out_dir).replace(os.sep, "/")) if prev_abs else None
    kml = urllib.parse.quote(os.path.relpath(kml_abs, out_dir).replace(os.sep, "/")) if kml_abs else None
    miss, margin = num(r.get("min_distance")), num(r.get("margin_km"))
    if margin is None and miss is not None and rad is not None:
        margin = miss - rad
    return dict(when=when, label=asteroid_label(tid, r.get("target_name")), tid=tid,
                star=r.get("star", "").strip(), mag=mag, drop=drop, dur=dur, alt=alt,
                compass=compass(az) if az is not None else "", az=az, moon=moon,
                miss=miss, margin=margin, rad=rad, kml=kml, kml_abs=kml_abs, preview=preview,
                m_ast=num(r.get("m_ast")), m_before=num(r.get("m_before")), calc=num(r.get("calc_s")),
                margin_mag=num(r.get("mag_margin")), airmass=num(r.get("airmass")), ext=num(r.get("extinction_mag")),
                size_src=(r.get("size_source") or "").strip(), utc=r["best_utc"].strip(), ra=ra, dec=dec, fov=fov)


def dedupe(events, tol=300.0):
    """Reruns append the same event again; the later log line replaces the earlier one."""
    kept = []
    for ev in events:
        for i, k in enumerate(kept):
            if k["tid"] == ev["tid"] and k["star"] == ev["star"] and abs((k["when"] - ev["when"]).total_seconds()) < tol:
                kept[i] = ev
                break
        else:
            kept.append(ev)
    return kept


def fmt_time(when):
    t = when + timedelta(seconds=0.5)
    return f"{t.year}-{MONTHS[t.month - 1]}-{t.day:02d} {t:%H:%M:%S}"


def fmt(v, nd=2, unit=""):
    return "—" if v is None else f"{v:.{nd}f}{unit}"


def alt_text(e):
    return "—" if e["alt"] is None else f"{e['alt']:.0f}° {e['compass']}".rstrip()


def moon_text(e):
    return "" if not e["moon"] else f"{e['moon']['icon']} {e['moon']['sep']:.0f}°"


# ---------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202b;--muted:#5d6b7a;--line:#e1e5ea;--head:#eef1f5;--accent:#1f6feb;
--in-bg:#dff5e6;--in-ink:#14653a;--near-bg:#fdf0d2;--near-ink:#7a5200}
@media (prefers-color-scheme:dark){:root{--bg:#10151b;--card:#171e26;--ink:#e6ebf1;--muted:#93a1b1;--line:#2a3441;
--head:#1e2732;--accent:#6aa6ff;--in-bg:#17402a;--in-ink:#8be0ae;--near-bg:#4a3a12;--near-ink:#f3cf7a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1440px;margin:0 auto;padding:24px 16px 40px}
h1{font-size:1.35rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 16px}
.info{display:grid;grid-template-columns:max-content 1fr;gap:2px 14px;font-size:.88rem;margin:0 0 16px}
.info dt{color:var(--muted)}.info dd{margin:0}
.wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:760px}
th,td{padding:8px 10px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line)}
th{background:var(--head);font-size:.8rem;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);
cursor:pointer;user-select:none;position:sticky;top:0}
th.sorted-asc::after{content:" ▲"}th.sorted-desc::after{content:" ▼"}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--head)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.sub{display:block;color:var(--muted);font-size:.78rem;line-height:1.5}
.badge{display:inline-block;padding:0 8px;border-radius:99px;font-size:.78rem}
.in{background:var(--in-bg);color:var(--in-ink)}.near{background:var(--near-bg);color:var(--near-ink)}
a{color:var(--accent)}
.notes{color:var(--muted);font-size:.85rem;margin-top:16px}
.notes li{margin:3px 0}
.empty{padding:28px;text-align:center;color:var(--muted)}
"""

JS = """
document.querySelectorAll('th[data-k]').forEach(function(th){
  th.addEventListener('click',function(){
    var tb=th.closest('table').tBodies[0],i=th.cellIndex,rows=Array.from(tb.rows),
        dir=th.classList.contains('sorted-asc')?-1:1;
    th.closest('tr').querySelectorAll('th').forEach(function(h){h.classList.remove('sorted-asc','sorted-desc')});
    th.classList.add(dir===1?'sorted-asc':'sorted-desc');
    rows.sort(function(a,b){
      var x=a.cells[i].dataset.s||'',y=b.cells[i].dataset.s||'',num=/^\\s*-?\\d+(\\.\\d+)?([eE][-+]?\\d+)?\\s*$/;
      var c=(num.test(x)&&num.test(y))?parseFloat(x)-parseFloat(y):x.localeCompare(y);return c*dir;});
    rows.forEach(function(r){tb.appendChild(r)});
  });
});
"""


MAP_CSS = """
.mapbtn,.tb{font:inherit;font-size:.85rem;padding:2px 10px;border:1px solid var(--line);border-radius:6px;background:var(--head);color:var(--ink);cursor:pointer}
.mapbtn:hover,.tb:hover{border-color:var(--accent);color:var(--accent)}
dialog{width:min(980px,96vw);height:min(720px,90vh);padding:0;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);overflow:hidden}
dialog[open]{display:flex;flex-direction:column}
dialog::backdrop{background:rgba(0,0,0,.55)}
.dh{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;border-bottom:1px solid var(--line)}
.dh h2{font-size:1rem;margin:0}
.dh button{font:inherit;font-size:1.1rem;border:0;background:none;color:var(--muted);cursor:pointer}
#map{flex:1;min-height:200px;background:#cfd8e3;color:#16202b;padding:0}
.df{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:10px 14px;border-top:1px solid var(--line);font-size:.85rem}
.legend{margin-left:auto;color:var(--muted)}
.legend i{display:inline-block;width:18px;height:3px;margin:0 5px 2px 12px;vertical-align:middle}
.legend i.dash{background:repeating-linear-gradient(90deg,#d97706 0 6px,transparent 6px 10px)}
.legend i.dot{background:repeating-linear-gradient(90deg,#7c3aed 0 2px,transparent 2px 5px)}
"""

LEAFLET_TAGS = ('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">'
                '<script defer src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>')

TOAST_JS = """<script>
function pyoToast(msg,stay){var t=document.getElementById('pyotoast');if(!t){t=document.createElement('div');t.id='pyotoast';
 t.setAttribute('role','status');t.style.cssText='position:fixed;left:50%;bottom:20px;transform:translateX(-50%);'+
 'max-width:min(720px,92vw);padding:10px 14px;border-radius:8px;background:#1e293b;color:#f8fafc;font-size:.9rem;'+
 'box-shadow:0 4px 16px rgba(0,0,0,.3);z-index:1000';document.body.appendChild(t);}
 t.textContent=msg;t.hidden=false;clearTimeout(t._h);t._h=setTimeout(function(){t.hidden=true;},stay?9000:4000);}
</script>"""

FAV_JS = """<script>
(function(){var bs=document.querySelectorAll('.favbtn');if(!bs.length||location.protocol==='file:')return;
fetch('/api/favorites/keys').then(function(r){return r.json();}).then(function(j){
 var have=new Set(j.keys||[]);
 bs.forEach(function(b){b.hidden=false;var on=have.has(b.dataset.key);b.textContent=on?'★':'☆';
  b.title=on?'In the favorites (GUI tab Favorites)':'Add to the favorites (with its map and preview)';
  b.addEventListener('click',function(){if(b.textContent==='★'){pyoToast('Already a favorite: manage it in the GUI tab Favorites');return;}
   var q=new URLSearchParams({tid:b.dataset.tid,utc:b.dataset.utc});
   fetch('/api/favorites/add?'+q).then(function(r){return r.json();}).then(function(j){
    if(j.ok){b.textContent='★';b.title='In the favorites (GUI tab Favorites)';}pyoToast(j.msg,!j.ok);})
   .catch(function(){pyoToast('Favorites: no answer from the GUI',true);});});});}).catch(function(){});})();
</script>"""

KSTARS_JS = """<script>
(function(){var site=__SITE__,bs=document.querySelectorAll('.ksbtn');if(!bs.length||location.protocol==='file:')return;
fetch('/api/kstars/status').then(function(r){return r.json();}).then(function(j){if(!j.ok)return;
 bs.forEach(function(b){b.hidden=false;b.addEventListener('click',function(){
  var q=new URLSearchParams({ra:b.dataset.ra,dec:b.dataset.dec,utc:b.dataset.utc,fov:b.dataset.fov});
  if(site){q.set('lat',site.lat);q.set('lon',site.lon);q.set('ele',site.ele||0);}
  b.textContent='KStars …';
  fetch('/api/kstars/show?'+q).then(function(r){return r.json();}).then(function(j){
   b.textContent=j.ok?'KStars ✓':'KStars ✗';b.title=j.msg;pyoToast(j.msg,!j.ok||j.msg.indexOf('; ')>0);
   setTimeout(function(){b.textContent='KStars';},4000);})
  .catch(function(){b.textContent='KStars ✗';pyoToast('KStars: no answer from the GUI',true);});});});}).catch(function(){});})();
</script>"""

PREVIEW_DIALOG = """<dialog id="prevdlg" aria-label="Event preview" style="width:auto;height:auto;max-width:96vw;max-height:96vh">
<div class="dh"><h2>Preview</h2><button id="prevclose" type="button" aria-label="Close preview">✕</button></div>
<img id="previmg" alt="Event preview" style="display:block;max-width:min(560px,94vw);max-height:84vh;margin:0 auto">
</dialog>
<script>
(function(){var d=document.getElementById('prevdlg'),img=document.getElementById('previmg');
document.querySelectorAll('.prevbtn').forEach(function(b){b.addEventListener('click',function(){
  d.querySelector('h2').textContent=b.dataset.t;img.src=b.dataset.src;if(!d.open)d.showModal();});});
document.getElementById('prevclose').addEventListener('click',function(){d.close();});
d.addEventListener('click',function(ev){if(ev.target===d)d.close();});})();
</script>"""

DIALOG = """<dialog id="mapdlg" aria-label="Shadow path map">
<div class="dh"><h2>Map</h2><button id="mapclose" type="button" aria-label="Close map">✕</button></div>
<div id="map"></div>
<div class="df"><button class="tb" id="mapobs" type="button">Zoom to observer</button>
<button class="tb" id="mapall" type="button">Whole path</button>
<a id="mapgm" target="_blank" rel="noopener" hidden>Closest centre-line point in Google Maps</a>
<span class="legend"><i style="background:#15803d"></i>centre line<i style="background:#dc2626"></i>shadow limits<i class="dot"></i>1σ limits<i class="dash"></i>3σ limits</span></div>
</dialog>"""

MAP_JS = """
(function(){
var DATA=JSON.parse(document.getElementById('pathdata').textContent),TILES=__TILES__,OBS0=__OBS__,
    dlg=document.getElementById('mapdlg'),box=document.getElementById('map'),gm=document.getElementById('mapgm'),
    map=null,layer=null,obs=null,near=null;
function nearest(line,o){            /* closest point of a polyline to o; equirectangular is fine at this scale */
  var k=Math.cos(o[0]*Math.PI/180),best=null;
  for(var i=0;i<line.length-1;i++){
    var ax=(line[i][1]-o[1])*k,ay=line[i][0]-o[0],bx=(line[i+1][1]-o[1])*k,by=line[i+1][0]-o[0],
        dx=bx-ax,dy=by-ay,L2=dx*dx+dy*dy,t=L2?Math.max(0,Math.min(1,-(ax*dx+ay*dy)/L2)):0,
        px=ax+t*dx,py=ay+t*dy,d=px*px+py*py;
    if(!best||d<best.d)best={d:d,lat:o[0]+py,lon:o[1]+px/k};
  }
  return best;
}
function zoomAll(){if(map&&layer)map.fitBounds(layer.getBounds(),{padding:[20,20]});}
function zoomObs(){
  if(!map)return;
  if(obs&&near)map.fitBounds([[obs[0],obs[1]],[near.lat,near.lon]],{padding:[70,70],maxZoom:11});
  else if(obs)map.setView(obs,7);
  else zoomAll();
}
function show(key,title){
  var d=DATA[key];if(!d)return;
  dlg.querySelector('h2').textContent=title;
  if(!dlg.open)dlg.showModal();
  if(!window.L){box.innerHTML='<p style="margin:14px">The map library could not be loaded (offline?). Use the KML link instead.</p>';return;}
  if(!map){box.textContent='';                 /* only before the first map: later it would remove Leaflet's panes */
    map=L.map(box,{worldCopyJump:true});
    L.tileLayer(TILES,{maxZoom:18,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);}
  if(layer)layer.remove();
  layer=L.featureGroup().addTo(map);
  var centre=null;obs=OBS0;
  d.lines.forEach(function(l){
    L.polyline(l.pts,{color:l.color,weight:l.width,dashArray:l.dash||null}).bindTooltip(l.name,{sticky:true}).addTo(layer);
    if(!centre&&l.name.indexOf('Centre')===0)centre=l.pts;
  });
  d.pins.forEach(function(p){
    if(p.name==='Observer'){obs=[p.lat,p.lon];
      L.circleMarker(obs,{radius:7,color:'#fff',weight:2,fillColor:'#e11d48',fillOpacity:1}).bindTooltip('Observer',{permanent:true,direction:'right'}).addTo(layer);}
    else L.circleMarker([p.lat,p.lon],{radius:3,color:'#15803d',weight:1,fillOpacity:1}).bindTooltip(p.name+(p.desc?' · '+p.desc:'')).addTo(layer);
  });
  near=(obs&&centre&&centre.length>1)?nearest(centre,obs):null;
  if(near){gm.href='https://www.google.com/maps/search/?api=1&query='+near.lat.toFixed(5)+','+near.lon.toFixed(5);gm.hidden=false;}
  else gm.hidden=true;
  setTimeout(function(){map.invalidateSize();zoomObs();},0);
}
document.querySelectorAll('.mapbtn').forEach(function(b){b.addEventListener('click',function(){show(b.dataset.k,b.dataset.t);});});
document.getElementById('mapobs').addEventListener('click',zoomObs);
document.getElementById('mapall').addEventListener('click',zoomAll);
document.getElementById('mapclose').addEventListener('click',function(){dlg.close();});
dlg.addEventListener('click',function(ev){if(ev.target===dlg)dlg.close();});
})();
"""


def map_script(paths, meta):
    data = json.dumps(paths, separators=(",", ":")).replace("</", "<\\/")
    js = MAP_JS.replace("__TILES__", json.dumps(meta["tiles"])).replace("__OBS__", json.dumps(meta["obs"]))
    return f'<script id="pathdata" type="application/json">{data}</script><script>{js}</script>'


def esc(s):
    return html.escape(str(s), quote=True)


def shadow_cell(e):
    if e["miss"] is None:
        return '<td class="num" data-s="">—</td>'
    m = e["margin"]
    if m is None:
        sub = ""
    elif m <= 0:
        sub = '<span class="sub"><span class="badge in">inside shadow</span></span>'
    elif m <= NEAR_KM:
        sub = f'<span class="sub"><span class="badge near">{m:.1f} km outside</span></span>'
    else:
        sub = f'<span class="sub">{m:.1f} km outside</span>'
    return f'<td class="num" data-s="{e["miss"]:.3f}">{e["miss"]:.1f} km{sub}</td>'


def map_cell(e):
    fav = (f'<button class="mapbtn favbtn" type="button" hidden data-tid="{esc(e["tid"])}" data-utc="{esc(e["utc"])}" '
           f'data-key="{esc(e["tid"])}_{e["when"]:%Y%m%dT%H%M}" aria-label="Favorite">☆</button> ')
    ks = fav + (f'<button class="mapbtn ksbtn" type="button" hidden data-ra="{e["ra"]:.7f}" data-dec="{e["dec"]:.7f}" '
          f'data-utc="{esc(e["utc"])}" data-fov="{e["fov"]:.3f}" title="Point KStars at the star at the event time, '
          f'seen from the site (Linux, KStars running, report opened from the GUI)">KStars</button> '
          if e.get("ra") is not None and e.get("dec") is not None else "")
    if not e["kml"] and not e.get("preview"):
        return f"<td>{ks}—</td>" if ks else "<td>—</td>"
    title = f'{e["label"]} · {fmt_time(e["when"])} UT'
    out = ks
    if e.get("pkey"):
        out += f'<button class="mapbtn" type="button" data-k="{esc(e["pkey"])}" data-t="{esc(title)}">Map</button> '
    if e.get("preview"):
        out += (f'<button class="mapbtn prevbtn" type="button" data-src="{e["preview"]}" data-t="{esc(title)}" '
                f'title="Star field at the event: camera frame, target star, asteroid track">Preview</button> ')
    if e["kml"]:
        out += f'<a href="{e["kml"]}" download title="KML for Google Earth or My Maps">KML</a>'
    return f"<td>{out}</td>"


def html_row(e):
    size = f"D≈{2 * e['rad']:.1f} km" if e["rad"] is not None else ""
    tip_ast = esc(f"Gaia DR3 {e['star']} · {size} ({e['size_src']})")
    drop_tip = ""
    if e["m_ast"] is not None:
        before = f"{e['m_before']:.2f} → " if e["m_before"] is not None else ""
        drop_tip = esc(f"{before}{e['m_ast']:.2f} mag during the event (asteroid alone)")
    alt_tip = f"azimuth {e['az']:.0f}°" if e["az"] is not None else ""
    if e["airmass"] is not None:
        alt_tip += f" · airmass {e['airmass']:.2f}" + (f", extinction {e['ext']:.2f} mag" if e["ext"] else "")
    alt_tip = esc(alt_tip)
    mag_tip = esc(f"{e['margin_mag']:+.2f} mag below the observability limit" if e["margin_mag"] is not None
                  and e["margin_mag"] >= 0 else f"{-e['margin_mag']:.2f} mag fainter than the observability limit"
                  if e["margin_mag"] is not None else "")
    moon = e["moon"]
    moon_tip = esc(f"Moon {moon['alt']:.0f}° above horizon, {moon['illum']:.0f}% lit") if moon and moon["illum"] is not None else ""
    s = lambda v, nd=3: "" if v is None else f"{v:.{nd}f}"
    return (
        "<tr>"
        f'<td data-s="{esc(e["label"])}" title="{tip_ast}">{esc(e["label"])}</td>'
        f'<td data-s="{e["when"].timestamp():.3f}" title="{esc(e["utc"])} UTC (closest approach to the observer)">{esc(fmt_time(e["when"]))}</td>'
        f'<td class="num" data-s="{s(e["mag"])}" title="{mag_tip}">{fmt(e["mag"])}</td>'
        f'<td class="num" data-s="{s(e["drop"])}" title="{drop_tip}">{fmt(e["drop"])}</td>'
        f'<td class="num" data-s="{s(e["dur"])}">{fmt(e["dur"])}</td>'
        f'<td data-s="{s(e["alt"], 1)}" title="{alt_tip}">{esc(alt_text(e))}</td>'
        f'<td data-s="{s(moon["sep"], 1) if moon else ""}" title="{moon_tip}">{esc(moon_text(e))}</td>'
        f"{shadow_cell(e)}"
        f'<td class="num" data-s="{s(e["calc"])}">{fmt(e["calc"])}</td>'
        f"{map_cell(e)}"
        "</tr>"
    )


def info_html(info):
    if not info:
        return ""
    return '<dl class="info">' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in info) + "</dl>"


def to_html(events, meta):
    on = lambda key: ' sorted-asc' if meta.get("sort", "date") == key else ""
    head = ('<th data-k>Asteroid</th>'
            f'<th class="{on("date").strip()}" data-k>Event time (UT)</th>'
            f'<th class="num{on("mag")}" data-k title="Gaia G magnitude of the star">Star mag</th>'
            '<th class="num" data-k title="Magnitude drop with the star fully covered">Mag drop</th>'
            '<th class="num" data-k title="Maximum duration (centre line), seconds">Max dur (s)</th>'
            '<th data-k title="Star altitude and compass direction at closest approach">Altitude</th>'
            '<th data-k title="Moon distance from the star; shown while the Moon is up">Moon dist</th>'
            '<th class="num" data-k title="Distance of the observer from the shadow centre line">Offset</th>'
            '<th class="num" data-k title="Calculation time for this event (exact solve and metrics), seconds">Calc (s)</th>'
            '<th title="☆ favorites and KStars (when opened from the GUI), Map: shadow path, Preview: star field, '
            'KML: ground track for Google Earth">Tools</th>')
    body = "".join(html_row(e) for e in events)
    table = (f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
             if events else '<div class="wrap"><div class="empty">No events match.</div></div>')
    n_kml = sum(1 for e in events if e["kml"])
    n_prev = sum(1 for e in events if e.get("preview"))
    paths = meta.get("paths") or {}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(meta['title'])}</title><style>{CSS}{MAP_CSS if paths or n_prev else ''}</style>{LEAFLET_TAGS if paths else ''}</head>
<body><main>
<h1>{esc(meta['title'])}</h1>
<p class="sub">{len(events)} events{esc(meta['span'])} · {esc(meta['observer'])} · times in UT · generated {esc(meta['generated'])} · {n_kml} map file{'s' if n_kml != 1 else ''}</p>
{info_html(meta.get("info"))}
{table}
<ul class="notes">
<li>Star magnitude is Gaia G. The drop assumes the star is fully covered and ignores the star's angular size and diffraction, so bright stars and very small bodies can show a smaller real drop.</li>
<li>Offset is the observer's distance from the shadow centre line in the fundamental plane. "Inside" means within the shadow radius; otherwise it is the gap to the shadow edge. Radius comes from the size lookup (hover the asteroid name).</li>
<li>Altitude is the star's altitude at closest approach. The Moon is shown only while above the horizon. Click a column heading to sort.</li>
<li>Map shows the path on an interactive map (needs internet for the map tiles) and links the closest centre-line point in Google Maps. Google Maps itself cannot load a local KML file: use the KML link with Google Earth, or import it in My Maps (Create a new map, then Import).</li>
</ul>
</main>{DIALOG if paths else ''}<script>{JS}</script>{map_script(paths, meta) if paths else ''}{PREVIEW_DIALOG if n_prev else ''}{TOAST_JS}{FAV_JS}{KSTARS_JS.replace("__SITE__", json.dumps(meta.get("site")))}</body></html>
"""


# ---------------------------------------------------------------- Markdown

def to_markdown(events, meta):
    out = [f"# {meta['title']}", "",
           f"{len(events)} events{meta['span']} · {meta['observer']} · times in UT · generated {meta['generated']}", ""]
    out += [f"- **{k}:** {v}" for k, v in (meta.get("info") or [])] + ([""] if meta.get("info") else [])
    out += ["| Asteroid | Event time (UT) | Star mag (G) | Mag drop | Max dur (s) | Altitude | Moon dist | Offset | Calc (s) | Files |",
            "|---|---|---:|---:|---:|---|---|---:|---:|---|"]
    for e in events:
        if e["miss"] is None:
            off = "—"
        elif e["margin"] is not None and e["margin"] <= 0:
            off = f"inside ({e['miss']:.1f} km)"
        else:
            off = f"{e['miss']:.1f} km" + (f" ({e['margin']:.1f} outside)" if e["margin"] is not None else "")
        kml = " ".join(x for x in (f"[KML]({e['kml']})" if e["kml"] else "", f"[Preview]({e['preview']})"
                                   if e.get("preview") else "") if x) or "—"
        out.append(f"| {e['label']} | {fmt_time(e['when'])} | {fmt(e['mag'])} | {fmt(e['drop'])} | {fmt(e['dur'])} "
                   f"| {alt_text(e)} | {moon_text(e)} | {off} | {fmt(e['calc'])} | {kml} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- main

def load_config_observer(csv_path):
    for d in (os.path.dirname(os.path.abspath(csv_path)), os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        sys.path.insert(0, d)
    try:
        import pyoccult_config as cfg
        return getattr(cfg, "LAT", None), getattr(cfg, "LON", None), getattr(cfg, "map_dir", None)
    except ImportError:
        return None, None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Turn PyOccult hits_log.csv into an HTML or Markdown event list.")
    ap.add_argument("csv", help="hits_log.csv written by PyOccult")
    ap.add_argument("-o", "--output", help="output file (default: hits_report.html / .md next to the CSV)")
    ap.add_argument("--format", choices=("html", "md"), help="default: from the output extension, else html")
    ap.add_argument("--kml-dir", help="folder with the KML files (default: map_dir from pyoccult_config, else ./maps)")
    ap.add_argument("--lat", type=float, help="observer latitude, deg north (for the compass direction)")
    ap.add_argument("--lon", type=float, help="observer longitude, deg east (negative = west)")
    ap.add_argument("--max-miss", type=float, help="only events whose centre-line distance is below this (km)")
    ap.add_argument("--min-drop", type=float, help="only events with at least this magnitude drop")
    ap.add_argument("--sort", choices=("mag", "date"), default="mag",
                    help="row order: mag = brightest star first (default), date = by event time")
    ap.add_argument("--title", default="PyOccult asteroid occultation events")
    ap.add_argument("--no-embed", action="store_true", help="do not embed the KML paths and map viewer in the HTML page")
    ap.add_argument("--tile-url", default="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                    help="tile URL template for the embedded map (default: OpenStreetMap, fine for light personal use)")
    a = ap.parse_args(argv)

    cfg_lat, cfg_lon, cfg_maps = load_config_observer(a.csv)
    lat = a.lat if a.lat is not None else cfg_lat
    lon = a.lon if a.lon is not None else cfg_lon
    fmt_name = a.format or ("md" if (a.output or "").lower().endswith(".md") else "html")
    out = a.output or os.path.join(os.path.dirname(os.path.abspath(a.csv)), "hits_report." + fmt_name)
    out_dir = os.path.dirname(os.path.abspath(out))
    kml_dir = a.kml_dir or cfg_maps or "maps"
    if lat is None or lon is None:
        print("note: no observer position (pyoccult_config.py or --lat/--lon): compass directions omitted", file=sys.stderr)

    if os.path.isfile(a.csv):
        rows, skipped = read_log(a.csv)
    elif os.path.isfile(os.path.splitext(a.csv)[0] + ".runs.jsonl"):
        rows, skipped = [], 0                     # the last run found no events: report it (header with the run's site)
        print(f"note: {a.csv} does not exist: the last run logged no events", file=sys.stderr)
    else:
        sys.exit(f"{a.csv} not found")
    events, bad = [], 0
    for r in rows:
        try:
            events.append(build_event(r, lat, lon, kml_dir, out_dir))
        except (KeyError, ValueError) as ex:
            bad += 1
            print(f"skipping unreadable row ({ex!r}): {r.get('target_id', '?')} {r.get('best_utc', '?')}", file=sys.stderr)
    events = dedupe(events)
    if a.max_miss is not None:
        events = [e for e in events if e["miss"] is not None and e["miss"] <= a.max_miss]
    if a.min_drop is not None:
        events = [e for e in events if e["drop"] is not None and e["drop"] >= a.min_drop]
    if a.sort == "mag":                                  # brightest first, unknown magnitudes last, ties by time
        events.sort(key=lambda e: (e["mag"] is None, e["mag"] if e["mag"] is not None else 0.0, e["when"]))
    else:
        events.sort(key=lambda e: e["when"])

    paths = {}
    if fmt_name == "html" and not a.no_embed:
        for e in events:
            if e["kml_abs"]:
                key = os.path.splitext(os.path.basename(e["kml_abs"]))[0]
                try:
                    paths[key] = kml_to_data(e["kml_abs"])
                    e["pkey"] = key
                except (ET.ParseError, ValueError, OSError) as ex:
                    print(f"could not read {e['kml_abs']} for the map ({ex}); the KML link is kept", file=sys.stderr)

    span = ""
    if events:
        span = f" from {min(e['when'] for e in events):%Y-%m-%d} to {max(e['when'] for e in events):%Y-%m-%d}"
    observer = f"observer {abs(lat):.4f}°{'N' if lat >= 0 else 'S'} {abs(lon):.4f}°{'E' if lon >= 0 else 'W'}" \
        if lat is not None and lon is not None else "observer position not set"
    run = read_last_run(a.csv)
    if run and run.get("site"):                                  # the run's site wins over the current config
        lat, lon = run["site"]["lat"], run["site"]["lon"]
        observer = f"site {run['site']['name']}"
    meta = dict(title=a.title, span=span, sort=a.sort, info=header_info(run, lat, lon), observer=observer, generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                paths=paths, tiles=a.tile_url, obs=[lat, lon] if lat is not None and lon is not None else None,
                site=dict(lat=lat, lon=lon, ele=(run or {}).get("site", {}).get("ele", 0.0))
                if lat is not None and lon is not None else None)
    text = to_markdown(events, meta) if fmt_name == "md" else to_html(events, meta)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"{len(events)} events -> {out}" + (f"  ({skipped + bad} unreadable rows skipped)" if skipped + bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
