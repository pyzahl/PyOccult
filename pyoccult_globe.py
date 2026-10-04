"""pyoccult_globe.py - Occult-style event plot as SVG: the whole Earth as seen from the star at the event time, with the
shadow path (centre line, shadow limits, 1- and 3-sigma limits, minute marks), the shadow axis off the Earth, day
side and terminator, the observer's site, a header with the event parameters (as Occult's plot: star, durations,
time per km and per mas, drop, Sun and Moon, 1-sigma error, asteroid size, parallax and motion) and a 2 deg star
chart with the asteroid's motion in 24 h steps.

    globe_data(spice, ...)   collects the geometry with SPICE (passed in; called by pyoccult.write_globe)
    render_svg(d)            pure drawing from that dict (testable without SPICE)

Coastlines and borders: data/ne_110m_earth.json (Natural Earth 1:110m, public domain).
"""
from pyoccult_version import __version__
import json, math, os
import numpy as np

W, H = 1024, 800                    # canvas, px
CX, CY, RPX = 512, 470, 300         # Earth disk centre and radius on the canvas
A_KM, C_KM = 6378.1366, 6356.7519   # Earth radii (as pck00010)
AU_KM = 1.495978707e8
RAD2MAS = math.degrees(1.0) * 3.6e6
LINES = (("center", "#111827", 2.4, None), ("edge_plus", "#dc2626", 1.4, None), ("edge_minus", "#dc2626", 1.4, None),
         ("sigma1_plus", "#7c3aed", 1.0, "2 3"), ("sigma1_minus", "#7c3aed", 1.0, "2 3"),
         ("sigma_plus", "#d97706", 1.0, "6 4"), ("sigma_minus", "#d97706", 1.0, "6 4"))
# styles: "color" (blue sea, land, dark night side, like OWC's globe) or "lines" (black on white, like Occult's plot)
STYLE = {
    "color": dict(sea="#1d4e89", land="#7b8f55", land_edge="#56663a", night=0.5, day=None, grid="#ffffff",
                  grid_op=0.22, coast=None, border="#e5e7eb", path={"center": "#fde047", "edge": "#f87171",
                  "sigma1": "#c4b5fd", "sigma": "#fdba74"}, mark="#fde047", label="#ffffff", halo="#0f172a",
                  site="#22d3ee", legend="yellow: centre line (dots: minutes UT) \u00b7 red: shadow limits \u00b7 "
                  "violet dotted: 1-sigma \u00b7 orange dashed: 3-sigma", legend2="dashed: shadow axis off the Earth "
                  "\u00b7 dark: night side \u00b7 cyan: site"),
    "lines": dict(sea="#f8fafc", land=None, land_edge=None, night=None, day="#fde68a", grid="#94a3b8", grid_op=1.0,
                  coast="#1f2937", border="#6b7280", path=None, mark="#111", label="#111", halo=None, site="#0369a1",
                  legend="black: centre line (dots: minutes UT) \u00b7 red: shadow limits \u00b7 violet dotted: "
                  "1-sigma \u00b7 orange dashed: 3-sigma", legend2="dashed: shadow axis off the Earth \u00b7 "
                  "yellow: day side \u00b7 blue: site"),
}


def _clamped(px, py, vis):
    """Polygon points with the hidden ones pushed onto the limb (orthographic fill trick)."""
    pts = []
    for x, y, v in zip(px, py, vis):
        if not v:
            r = math.hypot(x - CX, y - CY) or 1.0
            x, y = CX + (x - CX) / r * RPX, CY + (y - CY) / r * RPX
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)
_EARTH = None


def earth_lines():
    """{'coast': [[lon, lat, ...], ...], 'borders': [...]} from data/ne_110m_earth.json (cached)."""
    global _EARTH
    if _EARTH is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ne_110m_earth.json")
        try:
            with open(p, encoding="utf-8") as f:
                _EARTH = json.load(f)
        except (OSError, ValueError):
            _EARTH = {"coast": [], "borders": []}
    return _EARTH


def geodetic_to_itrf(lon_deg, lat_deg):
    """Points on the ellipsoid surface (height 0), km; arrays of lon, lat in degrees."""
    lon, lat = np.radians(np.asarray(lon_deg, float)), np.radians(np.asarray(lat_deg, float))
    e2 = 1 - (C_KM / A_KM) ** 2
    n = A_KM / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    return np.stack([n * np.cos(lat) * np.cos(lon), n * np.cos(lat) * np.sin(lon), n * (1 - e2) * np.sin(lat)], -1)


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------------------------------- drawing (pure)
class _Proj:
    """ITRF km -> canvas px for the Earth at the event time, seen from the star (x east right, y north up)."""
    def __init__(self, R, basis):
        self.R, (self.x, self.y, self.z) = np.asarray(R, float), (np.asarray(b, float) for b in basis)

    def __call__(self, itrf):
        p = np.atleast_2d(itrf) @ self.R.T                              # J2000
        X, Y, Z = p @ self.x, p @ self.y, p @ self.z
        return CX + X / A_KM * RPX, CY - Y / A_KM * RPX, Z > 0

    def plane(self, X, Y):                                              # fundamental-plane km -> px
        return CX + np.asarray(X) / A_KM * RPX, CY - np.asarray(Y) / A_KM * RPX


def _polylines(px, py, vis, style):
    """SVG polylines of the visible runs of a projected line."""
    out, run = [], []
    for x, y, v in zip(px, py, vis):
        if v:
            run.append(f"{x:.1f},{y:.1f}")
        elif run:
            if len(run) > 1:
                out.append(f'<polyline points="{" ".join(run)}" {style}/>')
            run = []
    if len(run) > 1:
        out.append(f'<polyline points="{" ".join(run)}" {style}/>')
    return out


def _day_side(R, basis, sun_dir_j2000, n=90):
    """Polygon (canvas px) of the visible day side: limb arc where the Sun is up, then the terminator arc."""
    x, y, z = basis
    s = np.asarray(sun_dir_j2000, float)
    p = np.cross(z, s)
    if np.linalg.norm(p) < 1e-9:
        return None
    p /= np.linalg.norm(p)
    pts = []
    for axis, keep in ((z, s), (s, z)):                                 # limb (n.z = 0), then terminator (n.s = 0)
        q = np.cross(axis, p)
        for t in np.linspace(0, math.pi, n):
            v = math.cos(t) * p + math.sin(t) * q
            if v @ keep < 0:
                v = math.cos(t) * p - math.sin(t) * q
            pts.append(v)
        p = -p
    P = np.array(pts) * A_KM
    X, Y = P @ x, P @ y
    return [f"{CX + a / A_KM * RPX:.1f},{CY - b / A_KM * RPX:.1f}" for a, b in zip(X, Y)]


def render_svg(d):
    """SVG text from globe_data()'s dict."""
    proj = _Proj(d["R"], d["basis"])
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="ui-monospace,Menlo,Consolas,monospace" font-size="11">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    # header: title line and three columns like Occult's plot
    o.append(f'<text x="8" y="18" font-size="15" font-weight="700" fill="#111">{_esc(d["title"])}</text>')
    for col, x in zip(d["columns"], (8, 395, 735)):
        for i, line in enumerate(col):
            o.append(f'<text x="{x}" y="{36 + 13 * i}" fill="#111">{_esc(line)}</text>')
    top = 48 + 13 * max(len(c) for c in d["columns"]) - 6               # header bottom line
    o.append(f'<line x1="0" y1="{top}" x2="{W}" y2="{top}" stroke="#111" stroke-width="1.2"/>')
    o.append(f'<clipPath id="plot"><rect x="0" y="{top + 1}" width="{W}" height="{H - top - 44}"/></clipPath>'
             f'<g clip-path="url(#plot)">')                            # globe and axis stay below the header
    st = STYLE.get(d.get("style", "color"), STYLE["color"])
    E = earth_lines()
    # globe: sea, land, night or day side, grid, coast, borders
    o.append(f'<circle cx="{CX}" cy="{CY}" r="{RPX}" fill="{st["sea"]}" stroke="#111" stroke-width="1.4"/>')
    if st["land"]:
        for ring in E.get("land", []):
            px, py, vis = proj(geodetic_to_itrf(ring[0::2], ring[1::2]))
            if vis.any():
                o.append(f'<polygon points="{_clamped(px, py, vis)}" fill="{st["land"]}" stroke="{st["land_edge"]}" '
                         f'stroke-width="0.5"/>')
    if st["night"]:
        night = _day_side(proj.R, (proj.x, proj.y, proj.z), -np.asarray(d["sun_dir"], float))
        if night:
            o.append(f'<polygon points="{" ".join(night)}" fill="#000" fill-opacity="{st["night"]}"/>')
    if st["day"]:
        day = _day_side(proj.R, (proj.x, proj.y, proj.z), d["sun_dir"])
        if day:
            o.append(f'<polygon points="{" ".join(day)}" fill="{st["day"]}" fill-opacity="0.35" stroke="#b45309" '
                     f'stroke-width="0.8" stroke-dasharray="1 2"/>')
    grid = f'fill="none" stroke="{st["grid"]}" stroke-opacity="{st["grid_op"]}" stroke-width="0.6"'
    for lat in range(-60, 61, 30):
        lon = np.linspace(-180, 180, 181)
        o += _polylines(*proj(geodetic_to_itrf(lon, np.full_like(lon, lat))), grid)
    for lon0 in range(-180, 180, 30):
        lat = np.linspace(-90, 90, 91)
        o += _polylines(*proj(geodetic_to_itrf(np.full_like(lat, lon0), lat)), grid)
    for key, style in (("coast", f'fill="none" stroke="{st["coast"]}" stroke-width="0.9"' if st["coast"] else None),
                       ("borders", f'fill="none" stroke="{st["border"]}" stroke-opacity="0.7" stroke-width="0.6" '
                                   f'stroke-dasharray="1.5 2"')):
        if not style:
            continue
        for ln in E.get(key, []):
            o += _polylines(*proj(geodetic_to_itrf(ln[0::2], ln[1::2])), style)
    # shadow axis off the Earth (fundamental plane), with minute ticks
    ax = d.get("axis") or []
    if ax:
        X, Y = np.array([a[1] for a in ax]), np.array([a[2] for a in ax])
        sx, sy = proj.plane(X, Y)
        out = np.hypot(X, Y) > A_KM
        o += _polylines(sx, sy, out, 'fill="none" stroke="#111" stroke-width="1" stroke-dasharray="3 3"')
        for i, ((et, Xk, Yk), ok) in enumerate(zip(ax, out)):
            if ok and abs(et - round(et / 60) * 60) < 0.5:
                j = i + 1 if i + 1 < len(ax) else i - 1
                dx, dy = (ax[j][1] - Xk, ax[j][2] - Yk) if j > i else (Xk - ax[j][1], Yk - ax[j][2])
                n = math.hypot(dx, dy) or 1.0
                px, py = proj.plane(Xk, Yk)
                tx, ty = -dy / n * 5, -dx / n * 5                         # perpendicular on the canvas (y down)
                o.append(f'<line x1="{px - tx:.1f}" y1="{py - ty:.1f}" x2="{px + tx:.1f}" y2="{py + ty:.1f}" '
                         f'stroke="#111" stroke-width="1"/>')
                o.append(f'<text x="{px + 2 * tx + 3:.1f}" y="{py + 2 * ty + 4:.1f}" fill="#111" font-size="10">'
                         f'{_esc(d["minute_label"](et))}</text>')
    # shadow path on the Earth
    for name, col, wid, dash in LINES:
        if st["path"]:
            col = st["path"][name.split("_")[0]]
        pts = (d.get("paths") or {}).get(name) or []
        if len(pts) > 1:
            a = np.array([[p[1], p[2]] for p in pts], float)
            style = f'fill="none" stroke="{col}" stroke-width="{wid}"' + (f' stroke-dasharray="{dash}"' if dash else "")
            o += _polylines(*proj(geodetic_to_itrf(a[:, 0], a[:, 1])), style)
    centre = (d.get("paths") or {}).get("center") or []
    if len(centre) > 1:                                                 # minute marks on the ground track
        ets = np.array([p[0] for p in centre])
        for m in range(int(math.ceil(ets[0] / 60)), int(math.floor(ets[-1] / 60)) + 1):
            t = m * 60.0
            k = int(np.searchsorted(ets, t))
            if not 0 < k < len(ets):
                continue
            f = (t - ets[k - 1]) / (ets[k] - ets[k - 1])
            lon = centre[k - 1][1] + f * (((centre[k][1] - centre[k - 1][1] + 180) % 360) - 180)
            lat = centre[k - 1][2] + f * (centre[k][2] - centre[k - 1][2])
            px, py, vis = proj(geodetic_to_itrf([lon], [lat]))
            if vis[0]:
                halo = (f' stroke="{st["halo"]}" stroke-width="2.5" paint-order="stroke"' if st["halo"] else "")
                o.append(f'<circle cx="{px[0]:.1f}" cy="{py[0]:.1f}" r="2" fill="{st["mark"]}"/>'
                         f'<text x="{px[0] + 4:.1f}" y="{py[0] - 4:.1f}" fill="{st["label"]}" font-size="10"{halo}>'
                         f'{_esc(d["minute_label"](t))}</text>')
    # the observer's site
    if d.get("site"):
        lon, lat, name = d["site"]
        px, py, vis = proj(geodetic_to_itrf([lon], [lat]))
        if vis[0]:
            halo = (f' stroke="{st["halo"]}" stroke-width="2.5" paint-order="stroke"' if st["halo"] else "")
            o.append(f'<circle cx="{px[0]:.1f}" cy="{py[0]:.1f}" r="4" fill="none" stroke="{st["site"]}" stroke-width="2"/>'
                     f'<text x="{px[0] + 7:.1f}" y="{py[0] + 12:.1f}" fill="{st["site"]}" font-size="11"{halo}>{_esc(name)}</text>')
    o.append("</g>")
    # legend
    o.append(f'<text x="8" y="{H - 30}" fill="#374151" font-size="10">{st["legend"]}</text>')
    o.append(f'<text x="8" y="{H - 18}" fill="#374151" font-size="10">{st["legend2"]}</text>')
    o.append(f'<text x="8" y="{H - 5}" fill="#374151" font-size="10">{_esc(d["footer"])}</text>')
    o += _inset(d.get("inset"))
    o.append("</svg>")
    return "\n".join(o)


def _inset(ins):
    """2 deg star chart, north up, east left, with the asteroid's motion in 24 h steps (bottom right)."""
    if not ins:
        return []
    size, x0, y0 = 220, W - 236, H - 290
    f = ins["field_arcmin"]
    s = size / f
    px = lambda xi: x0 + size / 2 - xi * s
    py = lambda eta: y0 + size / 2 - eta * s
    o = [f'<rect x="{x0}" y="{y0}" width="{size}" height="{size}" fill="#fff" stroke="#111"/>',
         f'<text x="{x0 + size / 2}" y="{y0 - 6}" text-anchor="middle" font-size="10" fill="#111">'
         f'{f / 60:g}° square, to G {ins["mag_limit"]:.1f}</text>',
         f'<text x="{x0 + size / 2}" y="{y0 + size + 14}" text-anchor="middle" font-size="10" fill="#111">'
         f'Motion in 24 h steps</text>']
    for xi, eta, g in ins["stars"]:
        if abs(xi) < f / 2 and abs(eta) < f / 2:
            r = max(0.7, min(4.5, 0.9 + 0.55 * (ins["mag_limit"] + 0.5 - g)))
            o.append(f'<circle cx="{px(xi):.1f}" cy="{py(eta):.1f}" r="{r:.1f}" fill="#111"/>')
    o.append(f'<circle cx="{px(0):.1f}" cy="{py(0):.1f}" r="7" fill="none" stroke="#6b7280"/>')
    tr = ins.get("track") or []
    for (a, b), col in zip(zip(tr, tr[1:]), ("#15803d", "#6b7280")):
        o.append(f'<line x1="{px(a[0]):.1f}" y1="{py(a[1]):.1f}" x2="{px(b[0]):.1f}" y2="{py(b[1]):.1f}" '
                 f'stroke="{col}" stroke-width="1.3"/>')
    return o


# ------------------------------------------------------------------------------------------- data (SPICE)
def gnomonic(ra, dec, ra0, dec0):
    """Arcmin offsets (xi east, eta north) of ra, dec (deg) about ra0, dec0."""
    ra, dec, ra0, dec0 = (np.radians(np.asarray(v, float)) for v in (ra, dec, ra0, dec0))
    c = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    xi = np.cos(dec) * np.sin(ra - ra0) / c
    eta = (np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / c
    return np.degrees(xi) * 60, np.degrees(eta) * 60


def _hms(deg, sign=False):
    v = deg / 15 if not sign else abs(deg)
    h = int(v); m = int((v - h) * 60); s = ((v - h) * 60 - m) * 60
    if sign:
        return f"{'-' if deg < 0 else '+'}{h:2d} {m:02d} {s:06.3f}"
    return f"{h:2d} {m:02d} {s:07.4f}"


def globe_data(spice, record, target, star_dir, paths, sigma3_km, site=None, stars=None, size=None,
               run_utc="", corrections=None, of_date=None, style="color"):
    """The dict render_svg() draws. record: the hits_log record of the event; target: SPICE name of the asteroid;
    star_dir: the (corrected) J2000 unit vector used by the search; paths: pyoccult_paths.shadow_path() result;
    site: (lon_deg, lat_deg, name); stars: (ra, dec, g) arrays at the event date for the 2 deg chart;
    size: the size dict of the search (r_km, r_min_km, r_max_km, source); of_date: (ra_deg, dec_deg) true of date."""
    from pyoccult_paths import plane_basis
    et = float(record["best_et"])
    basis = plane_basis(np.asarray(star_dir, float))
    x_ax, y_ax, z_ax = basis
    R = spice.pxform("ITRF93", "J2000", et)
    sun = np.asarray(spice.spkpos("10", et, "J2000", "LT+S", "399")[0])
    ast = np.asarray(spice.spkpos(str(target), et, "J2000", "CN", "399")[0])
    dist = float(np.linalg.norm(ast))
    v = float(record.get("speed_kms") or 0) or 1e-9
    # shadow axis in the fundamental plane, 1 s steps near whole minutes would be costly: 20 s steps, minutes exact
    span = 1.6 * A_KM / v
    ts = sorted(set(np.arange(et - span, et + span, 20.0).tolist() +
                    [m * 60.0 for m in range(int((et - span) // 60) + 1, int((et + span) // 60) + 1)]))
    axis = []
    for t in ts:
        a = np.asarray(spice.spkpos(str(target), t, "J2000", "CN", "399")[0])
        axis.append((t, float(a @ x_ax), float(a @ y_ax)))
    # asteroid motion: hourly dRA (s of time) and dDec (arcsec)
    _, ra1, de1 = spice.recrad(spice.spkpos(str(target), et - 1800, "J2000", "CN", "399")[0])
    _, ra2, de2 = spice.recrad(spice.spkpos(str(target), et + 1800, "J2000", "CN", "399")[0])
    dra_s = ((math.degrees(ra2 - ra1) + 180) % 360 - 180) * 240.0
    ddec = math.degrees(de2 - de1) * 3600
    elong = math.degrees(math.acos(float(np.clip(np.dot(star_dir, sun / np.linalg.norm(sun)), -1, 1))))
    km_per_mas = dist / RAD2MAS
    ra_d = math.degrees(math.atan2(star_dir[1], star_dir[0])) % 360
    dec_d = math.degrees(math.asin(float(np.clip(star_dir[2], -1, 1))))
    centre = (paths or {}).get("center") or []
    t0, t1 = (centre[0][0], centre[-1][0]) if centre else (et, et)
    utc = lambda t, n=0: spice.et2utc(t, "ISOC", n)
    hm = lambda t: f"{utc(t)[11:13]}h {utc(t)[14:16]}m"
    size = size or {}
    r, r0, r1 = (float(record.get(k) or size.get(k) or 0) for k in ("r_km", "r_min_km", "r_max_km"))
    sig = (sigma3_km or 0) / 3
    corr = corrections or {}
    name = str(record.get("target_name") or target).strip()
    title = f"{name} occults Gaia DR3 {record['star']} on {utc(et)[:10]} from {hm(t0)} to {hm(t1)} UT"
    left = ["Star:",
            f" G {float(record['mag']):.2f}",
            f" RA  = {_hms(ra_d)} (J2000, as used)",
            f" Dec = {_hms(dec_d, True)}",
            (f" [of Date: {_hms(of_date[0])}  {_hms(of_date[1], True)}]" if of_date else " [of Date: n/a]"),
            f" parallax {float(corr.get('parallax_mas', 0)):.2f} mas, deflection {float(corr.get('deflection_mas', 0)):.2f} mas applied",
            f"Prediction of {run_utc[:16].replace('T', ' ')} UT"]
    mid = [f"Durations: Max = {float(record.get('max_duration_s') or 0):.2f} secs",
           f"1km = {1 / v:.3f} secs, 1mas = {km_per_mas / v:.3f} secs",
           f"Mag Drop: {float(record.get('mag_drop') or 0):.1f}",
           f"Sun : Dist = {elong:.0f}°",
           (f"Moon: Dist = {float(record['moon_sep_deg']):.0f}°, illum = {float(record.get('moon_illum_pct') or 0):.0f}%"
            if record.get("moon_sep_deg") not in (None, "") and not _nan(record.get("moon_sep_deg")) else "Moon: -"),
           f"1σ Err: ±{sig:.1f} km = {sig / km_per_mas:.1f} mas (Horizons RSS)" if sig else "1σ Err: n/a"]
    right = ["Asteroid:",
             f" Mv = {float(record.get('m_ast') or 0):.1f}",
             f" Dia = {2 * r:.1f} ({2 * r0:.1f}-{2 * r1:.1f}) km, {2 * r / km_per_mas:.0f} mas",
             f" Parallax = {math.degrees(math.asin(A_KM / dist)) * 3600:.3f}\"",
             f" Hourly dRA = {dra_s:+.3f}s",
             f"        dDec = {ddec:+.2f}\"",
             f" Dist = {dist / AU_KM:.3f} AU"]
    inset = None
    if stars is not None:
        ra_s, dec_s, g = stars
        xi, eta = gnomonic(ra_s, dec_s, ra_d, dec_d)
        track = []
        for dt in (-86400.0, 0.0, 86400.0):
            _, a, b = spice.recrad(spice.spkpos(str(target), et + dt, "J2000", "CN", "399")[0])
            tx, ty = gnomonic([math.degrees(a)], [math.degrees(b)], ra_d, dec_d)
            track.append((float(tx[0]), float(ty[0])))
        inset = dict(field_arcmin=120.0, mag_limit=min(float(record["mag"]) + 1.5, 13.0),
                     stars=list(zip(np.ravel(xi).tolist(), np.ravel(eta).tolist(), np.ravel(g).tolist())), track=track)
    return dict(R=R, basis=basis, sun_dir=sun / np.linalg.norm(sun), paths=paths, axis=axis, site=site, style=style,
                title=title, columns=(left, mid, right), inset=inset,
                minute_label=lambda t: utc(t)[14:16],
                footer=f"PyOccult {__version__} · orbit JPL Horizons · size: "
                       f"{str(record.get('size_source') or size.get('source') or '').split(' (ref')[0]} · "
                       f"Earth as seen from the star at {utc(et)[11:19]} UT")


def _nan(v):
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True
