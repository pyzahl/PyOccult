"""preview.py - event preview: the star field around the occulted star at the event time, as an SVG image.

Shows the stars of the local Gaia catalog (moved by proper motion to the event date) in a finder field a few times
larger than the camera's field of view, the camera frame centred on the target star, the target star, the asteroid's
position and its track (+/- 1 h), a scale bar and the north/east directions. Orientation: north up, east left, as seen
on the sky (a telescope may flip or rotate this).

Standard library + numpy; the caller supplies the stars and the asteroid track (search.py does, with SPICE).
"""
from pyoccult.version import __version__
import math
import numpy as np

SIZE = 560                                 # image width and height, px (field area)
DENSE_START, DENSE_KEEP = 4000, 1500      # very dense field (> DENSE_START stars): only the brightest DENSE_KEEP are
                                           # drawn normally, the fainter ones as small dim dots


def camera_fov_arcmin(focal_mm, sensor_mm):
    """(width, height) of the camera field of view in arcmin."""
    return tuple(2 * math.degrees(math.atan(s / 2 / focal_mm)) * 60 for s in sensor_mm)


def _gnomonic(ra, dec, ra0, dec0):
    """Tangent-plane coordinates (arcmin) of (ra, dec) around (ra0, dec0): xi east, eta north."""
    ra, dec, ra0, dec0 = (np.radians(np.asarray(x, float)) for x in (ra, dec, ra0, dec0))
    cosc = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    xi = np.cos(dec) * np.sin(ra - ra0) / cosc
    eta = (np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / cosc
    return np.degrees(xi) * 60, np.degrees(eta) * 60


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_svg(stars, target, track, fov_arcmin, field_factor=3.0, title="", subtitle="", min_field_arcmin=10.0):
    """SVG text of the preview.
    stars: dict of arrays ra, dec (deg, at the event date), g (Gaia G)
    target: dict ra, dec, g (the occulted star)
    track: list of (minutes from the event, ra, dec) of the asteroid; must include 0
    fov_arcmin: (width, height) of the camera field."""
    fw, fh = fov_arcmin
    field = max(field_factor * max(fw, fh), min_field_arcmin)          # square finder field, arcmin
    scale = SIZE / field                                               # px per arcmin
    cx = cy = SIZE / 2
    px = lambda xi: cx - xi * scale                                    # east left
    py = lambda eta: cy - eta * scale                                  # north up
    head = 74
    W, H = SIZE, SIZE + head
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="system-ui,sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#0b1020"/>',
           f'<text x="12" y="22" fill="#e5e7eb" font-size="15" font-weight="600">{_esc(title)}</text>',
           f'<text x="12" y="42" fill="#9ca3af" font-size="12">{_esc(subtitle)}</text>',
           f'<g transform="translate(0,{head})">',
           f'<rect width="{SIZE}" height="{SIZE}" fill="#05070f"/>']
    # stars, faint first so bright ones are drawn on top
    xi, eta = _gnomonic(stars["ra"], stars["dec"], target["ra"], target["dec"])
    g = np.asarray(stars["g"], float)
    order = np.argsort(-g)
    X, Y = px(np.asarray(xi, float)), py(np.asarray(eta, float))
    inside = (X >= 0) & (X <= SIZE) & (Y >= 0) & (Y <= SIZE)
    g_in = np.sort(g[inside])
    g_dim = float(g_in[DENSE_KEEP]) if len(g_in) > DENSE_START else None   # very dense: fainter than this dimmed
    g_max = float(g_in[-1]) if len(g_in) else 0.0
    for k in order:
        if not inside[k]:
            continue
        if g_dim is not None and g[k] > g_dim:                         # small, dim dot, fading towards the limit
            t = (g[k] - g_dim) / max(g_max - g_dim, 0.1)
            r, op = 0.85 - 0.4 * t, 0.38 - 0.22 * t
        else:
            r, op = float(np.clip(0.8 + 0.55 * (16.5 - g[k]), 0.7, 7.5)), min(1.0, 0.45 + 0.08 * (16.5 - g[k]))
        out.append(f'<circle cx="{X[k]:.1f}" cy="{Y[k]:.1f}" r="{r:.2f}" fill="#f8fafc" fill-opacity="'
                   f'{op:.2f}"><title>G {g[k]:.2f}</title></circle>')
    # camera frame
    out.append(f'<rect x="{cx - fw * scale / 2:.1f}" y="{cy - fh * scale / 2:.1f}" width="{fw * scale:.1f}" '
               f'height="{fh * scale:.1f}" fill="none" stroke="#38bdf8" stroke-width="1.5" stroke-dasharray="6 4"/>')
    out.append(f'<text x="{cx - fw * scale / 2 + 4:.1f}" y="{cy - fh * scale / 2 - 6:.1f}" fill="#38bdf8" '
               f'font-size="11">camera {fw:.1f}′ × {fh:.1f}′</text>')
    # translucent backing for the legend and scale bar (bottom left)
    out.append(f'<rect x="8" y="{SIZE - 66}" width="320" height="56" rx="4" fill="#05070f" fill-opacity="0.8"/>')
    # asteroid track and position
    if track:
        t = np.array([p[0] for p in track], float)
        axi, aeta = _gnomonic([p[1] for p in track], [p[2] for p in track], target["ra"], target["dec"])
        pts = " ".join(f"{px(a):.1f},{py(b):.1f}" for a, b in zip(axi, aeta))
        out.append(f'<polyline points="{pts}" fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="3 3"/>')
        if len(t) > 1:                                                  # arrow at the end: direction of motion
            x1, y1, x0, y0 = px(axi[-1]), py(aeta[-1]), px(axi[-2]), py(aeta[-2])
            ang = math.atan2(y1 - y0, x1 - x0)
            a1, a2 = ang + 2.6, ang - 2.6
            out.append(f'<path d="M{x1:.1f},{y1:.1f} L{x1 + 7 * math.cos(a1):.1f},{y1 + 7 * math.sin(a1):.1f} '
                       f'M{x1:.1f},{y1:.1f} L{x1 + 7 * math.cos(a2):.1f},{y1 + 7 * math.sin(a2):.1f}" '
                       f'stroke="#f59e0b" stroke-width="1.5"/>')
        i0 = int(np.argmin(np.abs(t)))
        ax, ay = px(axi[i0]), py(aeta[i0])
        out.append(f'<path d="M{ax:.1f},{ay - 5:.1f} L{ax + 5:.1f},{ay:.1f} L{ax:.1f},{ay + 5:.1f} L{ax - 5:.1f},{ay:.1f} Z" '
                   f'fill="none" stroke="#f59e0b" stroke-width="1.5"><title>asteroid at the event</title></path>')
        out.append(f'<g font-size="11" fill="#f59e0b"><path d="M16,{SIZE - 52} h22" stroke="#f59e0b" stroke-width="1.5" '
                   f'stroke-dasharray="3 3"/><text x="44" y="{SIZE - 48}">asteroid track {t[0]:+.0f} to {t[-1]:+.0f} min, '
                   f'◇ at the event</text></g>')
    # target star
    r = 11
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#f43f5e" stroke-width="1.8"/>')
    out.append(f'<path d="M{cx - r - 9},{cy} H{cx - r - 2} M{cx + r + 2},{cy} H{cx + r + 9} '
               f'M{cx},{cy - r - 9} V{cy - r - 2} M{cx},{cy + r + 2} V{cy + r + 9}" stroke="#f43f5e" stroke-width="1.8"/>')
    out.append(f'<text x="{cx + r + 12}" y="{cy + 4}" fill="#f43f5e" font-size="12">G {target["g"]:.2f}</text>')
    # compass (north up, east left) and scale bar
    out.append(f'<g stroke="#9ca3af" stroke-width="1.5" fill="#9ca3af" font-size="12">'
               f'<path d="M{SIZE - 30},{SIZE - 30} V{SIZE - 70} M{SIZE - 30},{SIZE - 30} H{SIZE - 70}"/>'
               f'<text x="{SIZE - 35}" y="{SIZE - 75}" stroke="none">N</text>'
               f'<text x="{SIZE - 86}" y="{SIZE - 26}" stroke="none">E</text></g>')
    bar = max(1, round(field / 5))                                      # arcmin
    out.append(f'<g stroke="#9ca3af" stroke-width="2" font-size="12" fill="#9ca3af">'
               f'<path d="M16,{SIZE - 22} H{16 + bar * scale:.1f}"/>'
               f'<text x="16" y="{SIZE - 30}" stroke="none">{bar}′</text></g>')
    out.append("</g>")
    out.append(f'<text x="12" y="60" fill="#6b7280" font-size="11">'
               f'field {field:.0f}′ · stars to G {float(np.max(g)) if len(g) else 0:.1f}'
               + (f' · dense: fainter than G {g_dim:.1f} dimmed' if g_dim is not None else '') + ' · N up, E left</text>')
    out.append("</svg>")
    return "\n".join(out)
