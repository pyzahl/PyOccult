"""ellipses.py - sky-plane 1-sigma error ellipses of an event, as OccultWatcher's event page shows them: the target's
(JPL Horizons, quantity 37), the star's (Gaia DR3 position and proper-motion errors carried to the event date) and the
combined one (the sum of both covariances: the uncertainty of the star relative to the target, which moves the path).
One SVG with all three at the same scale (favorites panel). Standard library only.

Conventions: x = east (RA x cos Dec), y = north, in mas; position angle (PA) from north through east.
"""
from pyoccult.version import __version__
import math


def cov(smaa, smia, pa_deg):
    """Covariance (xx, xy, yy) in mas^2 of a 1-sigma ellipse with semi-axes smaa >= smia and its major axis at pa_deg."""
    p = math.radians(pa_deg)
    ux, uy = math.sin(p), math.cos(p)                            # major axis direction (east, north)
    a2, b2 = smaa ** 2, smia ** 2
    return (a2 * ux * ux + b2 * uy * uy, (a2 - b2) * ux * uy, a2 * uy * uy + b2 * ux * ux)


def ellipse(c):
    """(smaa, smia, pa_deg) of a covariance (xx, xy, yy)."""
    xx, xy, yy = c
    tr, det = xx + yy, xx * yy - xy * xy
    d = math.sqrt(max(tr * tr / 4 - det, 0.0))
    l1, l2 = tr / 2 + d, max(tr / 2 - d, 0.0)
    pa = math.degrees(0.5 * math.atan2(2 * xy, yy - xx)) % 180.0     # angle from north (y) towards east (x)
    return math.sqrt(l1), math.sqrt(l2), pa


def add(*covs):
    return tuple(sum(c[i] for c in covs) for i in range(3))


def star_ellipse(g, years):
    """The star's 1-sigma ellipse (smaa, smia, pa) in mas at `years` after the Gaia epoch, from a Gaia DR3 row (mapping
    with ra_error, dec_error, pmra_error, pmdec_error and the correlations ra_dec_corr, pmra_pmdec_corr,
    ra_pmra_corr, ra_pmdec_corr, dec_pmra_corr, dec_pmdec_corr): position + years x proper motion, with their
    correlations (the parallax error is left out: 0.01-0.1 mas). None without errors (a 2-parameter source has no
    proper motion errors: its position error then grows by the unknown motion and is not given)."""
    def v(k, default=None):
        x = g.get(k) if hasattr(g, "get") else g[k]
        try:
            x = float(x)
        except (TypeError, ValueError):
            return default
        return x if math.isfinite(x) else default
    sa, sd, spa, spd = v("ra_error"), v("dec_error"), v("pmra_error"), v("pmdec_error")
    if None in (sa, sd, spa, spd):
        return None
    t = float(years)
    c = lambda k, s1, s2: v(k, 0.0) * s1 * s2
    xx = sa * sa + 2 * t * c("ra_pmra_corr", sa, spa) + t * t * spa * spa
    yy = sd * sd + 2 * t * c("dec_pmdec_corr", sd, spd) + t * t * spd * spd
    xy = c("ra_dec_corr", sa, sd) + t * (c("ra_pmdec_corr", sa, spd) + c("dec_pmra_corr", sd, spa)) \
        + t * t * c("pmra_pmdec_corr", spa, spd)
    return ellipse((xx, xy, yy))


# typical Gaia DR3 uncertainties by G (Lindegren et al. 2021, A&A 649, A2): position at the Gaia epoch (mas) and
# proper motion (mas/yr), for stars without their own errors (archive not reached, or a 2-parameter source)
TYPICAL = ((12.0, 0.015, 0.02), (15.0, 0.02, 0.025), (17.0, 0.05, 0.07), (19.0, 0.15, 0.2), (20.0, 0.4, 0.5),
           (21.0, 1.0, 1.4))


def typical_star(g, years):
    """A typical star's 1-sigma ellipse (s, s, 0) in mas for Gaia G at `years` after the Gaia epoch (circular:
    position and proper-motion errors of a typical DR3 star of that G, interpolated in log)."""
    g = min(max(float(g), TYPICAL[0][0]), TYPICAL[-1][0])
    for (g0, p0, m0), (g1, p1, m1) in zip(TYPICAL, TYPICAL[1:]):
        if g <= g1:
            f = (g - g0) / (g1 - g0)
            pos, pm = p0 * (p1 / p0) ** f, m0 * (m1 / m0) ** f
            break
    s = math.hypot(pos, float(years) * pm)
    return s, s, 0.0


def across_track(c, motion_ra, motion_dec):
    """1-sigma (mas) of a covariance across the target's motion on the sky (what shifts the path on the ground)."""
    m = math.hypot(motion_ra, motion_dec)
    if not m:
        return None
    nx, ny = -motion_dec / m, motion_ra / m                       # perpendicular to the motion
    xx, xy, yy = c
    return math.sqrt(max(nx * nx * xx + 2 * nx * ny * xy + ny * ny * yy, 0.0))


def _nice(x):
    """A round scale-bar length (1, 2, 5 x 10^n) not above x."""
    e = 10 ** math.floor(math.log10(x))
    return max(m * e for m in (1, 2, 5) if m * e <= x)


def svg(target=None, star=None, motion=None, size=300, labels=("Target", "Star", "Combined"), note="",
        missing=None, star_note="", star_at=None, disk_mas=None, star_at_note="",
        title="Uncertainty ellipses (sky plane, 1σ)"):
    """SVG of the 1-sigma ellipses at one scale: target (blue), star (green), combined (orange outline), each
    (smaa, smia, pa) in mas or None; motion = (RA x cos Dec, Dec) rate of the target (any unit) for its direction
    (the path runs along it: only the error across it shifts the path); note: a last line (e.g. the error across
    the track in km); missing: {label: reason} for an ellipse not known (a legend line). A star ellipse smaller than
    a few pixels is marked with a "+" at the centre; star_note: the star's ellipse is a typical one, not the star's
    own (its legend line gets a "!" and this note). star_at = (east, north) mas: where the star stands relative to
    the target's centre as seen from the site at closest approach (its ellipse drawn there again, dashed, with its
    track relative to the target); disk_mas: the target's angular radius (its disk, outlined); star_at_note: legend
    text for it. North up, east left, as the sky."""
    ells = [(e, col, lab) for e, col, lab in ((target, "#2563eb", labels[0]), (star, "#16a34a", labels[1]))
            if e and e[0] > 0]
    comb = ellipse(add(*[cov(*e) for e, _, _ in ells])) if ells else None
    if comb:
        ells.append((comb, "#ea580c", labels[2]))
    W, H, cx, cy = size, size + 96, size / 2, size / 2 + 14
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="system-ui,sans-serif" font-size="11">',
           f'<rect width="{W}" height="{H}" fill="#0b1020" rx="6"/>',
           f'<text x="10" y="17" fill="#e5e7eb" font-size="12" font-weight="600">{title}</text>',
           f'<path d="M{cx},{cy - size * 0.45:.1f} V{cy + size * 0.45:.1f} M{cx - size * 0.45:.1f},{cy} H{cx + size * 0.45:.1f}" '
           f'stroke="#475569" stroke-width="1"/>',
           f'<text x="{cx + 4}" y="{cy - size * 0.45 + 10:.1f}" fill="#9ca3af">N</text>',
           f'<text x="{cx - size * 0.45:.1f}" y="{cy - 4}" fill="#9ca3af">E</text>']
    if not ells:
        out.append(f'<text x="{cx}" y="{cy + 20}" fill="#9ca3af" text-anchor="middle">no error data</text></svg>')
        return "\n".join(out)
    big = max(e[0] for e, _, _ in ells)
    if star_at:                                                   # room for the star's place and the disk
        big = max(big, math.hypot(*star_at) + (star[0] if star else 0), disk_mas or 0)
    scale = size * 0.4 / big                                      # px per mas: the largest item fills 80 %
    if disk_mas:                                                  # the target's disk at its angular size
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{max(disk_mas * scale, 1.0):.2f}" fill="#e5e7eb" fill-opacity="0.07" '
                   f'stroke="#e5e7eb" stroke-opacity="0.6" stroke-width="1"><title>target disk: radius {disk_mas:.2f} mas'
                   f'</title></circle>')
    if star_at:                                                   # the star as seen from the site
        sx, sy = cx - star_at[0] * scale, cy - star_at[1] * scale
        if motion and (motion[0] or motion[1]):                   # its track relative to the target
            m = math.hypot(*motion)
            dx, dy = -motion[0] / m, -motion[1] / m
            L = size * 0.6
            out.append(f'<path d="M{sx - dx * L:.1f},{sy - dy * L:.1f} L{sx + dx * L:.1f},{sy + dy * L:.1f}" '
                       f'stroke="#16a34a" stroke-opacity="0.6" stroke-width="1" stroke-dasharray="2 3"/>')
        if star:
            a, b, pa = star
            out.append(f'<ellipse cx="{sx:.1f}" cy="{sy:.1f}" rx="{max(b * scale, 0.8):.2f}" ry="{max(a * scale, 0.8):.2f}" '
                       f'transform="rotate({-pa:.2f} {sx:.1f} {sy:.1f})" stroke="#16a34a" fill="#16a34a" '
                       f'fill-opacity="0.2" stroke-width="1.3" stroke-dasharray="3 2"/>')
        out.append(f'<path d="M{sx - 6:.1f},{sy:.1f} H{sx + 6:.1f} M{sx:.1f},{sy - 6:.1f} V{sy + 6:.1f}" stroke="#16a34a" '
                   f'stroke-width="1.5"><title>the star seen from the site at closest approach</title></path>')
    if motion and (motion[0] or motion[1]):                       # the target's motion (path direction)
        m = math.hypot(*motion)
        dx, dy = -motion[0] / m, -motion[1] / m                   # east left, north up
        L = size * 0.45
        out.append(f'<path d="M{cx - dx * L:.1f},{cy - dy * L:.1f} L{cx + dx * L:.1f},{cy + dy * L:.1f}" '
                   f'stroke="#64748b" stroke-width="1" stroke-dasharray="5 4"/>')
        ang = math.atan2(dy, dx)
        tip = (cx + dx * L, cy + dy * L)
        out.append(f'<path d="M{tip[0]:.1f},{tip[1]:.1f} l{-8 * math.cos(ang - 0.4):.1f},{-8 * math.sin(ang - 0.4):.1f} '
                   f'M{tip[0]:.1f},{tip[1]:.1f} l{-8 * math.cos(ang + 0.4):.1f},{-8 * math.sin(ang + 0.4):.1f}" '
                   f'stroke="#64748b" stroke-width="1.2"/>')
    for (a, b, pa), col, lab in ells:
        if lab == labels[1] and a * scale < 3:                    # the star: too small to see, mark its place
            out.append(f'<path d="M{cx - 6},{cy} H{cx + 6} M{cx},{cy - 6} V{cy + 6}" stroke="{col}" stroke-width="1.5">'
                       f'<title>{lab}: {a:.2f} x {b:.2f} mas (too small to see at this scale)</title></path>')
        rot = -pa                                                 # SVG rotates clockwise; PA runs north -> east (left)
        fill = 'fill="none" stroke-width="2"' if lab == labels[2] else f'fill="{col}" fill-opacity="0.28" stroke-width="1.3"'
        out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{max(b * scale, 0.8):.2f}" ry="{max(a * scale, 0.8):.2f}" '
                   f'transform="rotate({rot:.2f} {cx} {cy})" stroke="{col}" {fill}>'
                   f'<title>{lab}: {a:.2f} x {b:.2f} mas at PA {pa:.0f}°</title></ellipse>')
    bar = _nice(big * 0.8)
    out.append(f'<path d="M{W - 12 - bar * scale:.1f},{size + 8} h{bar * scale:.1f}" stroke="#e5e7eb" stroke-width="2"/>'
               f'<text x="{W - 12}" y="{size + 2}" fill="#e5e7eb" text-anchor="end">{bar:g} mas</text>')
    y = size + 24
    for (a, b, pa), col, lab in ells:                             # one legend line each: (a x b) mas @ PA
        if lab == labels[1] and star_note:
            out.append(f'<text x="12" y="{y}" fill="{col}">{lab} !: {a:.2f} mas, {star_note}</text>')
        else:
            out.append(f'<text x="12" y="{y}" fill="{col}">{lab}: ({a:.2f} × {b:.2f}) mas @ {pa:.0f}°</text>')
        y += 15
    for lab, why in (missing or {}).items():
        out.append(f'<text x="12" y="{y}" fill="#9ca3af">{lab}: {why}</text>')
        y += 15
    if star_at_note:
        out.append(f'<text x="12" y="{y}" fill="#16a34a">{star_at_note}</text>')
        y += 15
    if note:
        out.append(f'<text x="12" y="{y}" fill="#9ca3af">{note}</text>')
    out.append("</svg>")
    return "\n".join(out)
