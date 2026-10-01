"""pyoccult_paths.py - ground track of an asteroid shadow as KML for Google My Maps / Earth.

Needs the same SPICE state as the main tool: LSK, planetary SPK, Earth PCK (ITRF93) and the
asteroid SPK loaded, and the asteroid number string aliased with boddef (fetch_target_orbit does that).

v2: SpiceyPy's surfpt() returns only the point and raises NotFoundError when the ray misses the Earth
(v1 unpacked a (point, found) tuple, which crashed near the ends of the time window).
"""
import numpy as np
import spiceypy as spice
from spiceypy.utils.exceptions import NotFoundError
from xml.sax.saxutils import escape

AU_KM = 149597870.7


def plane_basis(star_vector):
    """Fundamental-plane axes in J2000: x east, y north, z toward the star (same as besselian_offsets)."""
    z = star_vector / np.linalg.norm(star_vector)
    x = np.cross([0.0, 0.0, 1.0], z)
    if np.linalg.norm(x) < 1e-12:                 # star at a celestial pole
        x = np.array([1.0, 0.0, 0.0])
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    return x, y, z


def shadow_path(target_id, star_dir, et_best, r_km, sigma3_km, half_span=None, step=None):
    """Ground track of the shadow axis and its limits.

    Returns {name: [(et, lon_deg, lat_deg, duration_s_or_None), ...]} for
    'center', 'edge_plus', 'edge_minus' (+/- r_km) and 'sigma_plus', 'sigma_minus' (+/- (r_km + sigma3_km)).
    '+' is the side 90 deg counter-clockwise of the shadow's motion in the plane (x east, y north).
    duration_s is the centre-line duration 2*r/(shadow speed relative to the ground point).

    Samples where a line does not touch the Earth (shadow off the disk, or a limit line beyond the
    terminator) are skipped, so lines can have different lengths and may be empty.
    half_span / step (s) default to values derived from the shadow speed: the span covers about
    1.3 Earth radii of along-track motion on each side, the step about 100 km of along-track motion.
    """
    a, b, c = spice.bodvrd('EARTH', 'RADII', 3)[1]
    flat = (a - c) / a
    x_ax, y_ax, z_ax = plane_basis(star_dir)
    M = np.vstack((x_ax, y_ax, z_ax))
    tid = str(target_id)

    def axis_velocity(et):                              # shadow velocity on the plane, km/s
        p0, _ = spice.spkpos(tid, et - 0.5, 'J2000', 'CN', '399')
        p1, _ = spice.spkpos(tid, et + 0.5, 'J2000', 'CN', '399')
        return (M @ (p1 - p0))[:2]

    speed = np.linalg.norm(axis_velocity(et_best))
    if speed < 1e-6:
        raise ValueError("shadow does not move on the fundamental plane")
    if half_span is None:
        half_span = 1.3 * a / speed
    if step is None:
        step = max(1.0, min(60.0, 100.0 / speed))
    n_steps = int(np.ceil(half_span / step))
    ets = et_best + step * np.arange(-n_steps, n_steps + 1)

    offsets = {'center': 0.0, 'edge_plus': r_km, 'edge_minus': -r_km,
               'sigma_plus': r_km + sigma3_km, 'sigma_minus': -(r_km + sigma3_km)}
    out = {k: [] for k in offsets}

    for et in ets:
        ast0, _ = spice.spkpos(tid, et, 'J2000', 'CN', '399')          # same convention as the solver
        v_axis = axis_velocity(et)
        n = np.array([-v_axis[1], v_axis[0]]) / np.linalg.norm(v_axis)
        n3 = n[0] * x_ax + n[1] * y_ax                                  # J2000 unit vector across the track
        axis_pt = ast0 - (ast0 @ z_ax) * z_ax                           # shadow axis point in the plane through the geocentre
        R = spice.pxform('J2000', 'ITRF93', et)
        R1 = spice.pxform('J2000', 'ITRF93', et + 1.0)

        for name, off in offsets.items():
            # start 2 Earth radii out on the star side of the plane and look along -z (the light direction);
            # the first surface intersection is the star-facing side of the Earth
            vertex = axis_pt + off * n3 + 2.0 * a * z_ax
            try:
                point = spice.surfpt(R @ vertex, R @ (-z_ax), a, b, c)
            except NotFoundError:
                continue                                                # this line misses the Earth at this time
            lon, lat, _ = spice.recgeo(point, a, flat)
            dur = None
            if name == 'center':
                v_ground = (M @ (R1.T @ point - R.T @ point))[:2]       # same ground point, one second later
                dur = 2.0 * r_km / np.linalg.norm(v_axis - v_ground)
            out[name].append((et, np.degrees(lon), np.degrees(lat), dur))
    return out


def path_sigma3_km(target_id, utc_time):
    """3-sigma plane-of-sky position uncertainty (RSS) from Horizons, converted to km at the asteroid.

    Returns None if Horizons has no covariance for the object or the query fails.
    """
    from astroquery.jplhorizons import Horizons
    from astropy.time import Time
    try:
        eph = Horizons(id=str(target_id), id_type='smallbody', location='500',
                       epochs=Time(utc_time, scale='utc').jd).ephemerides(quantities='20,38')
        names = list(eph.colnames)
        col = next((c for c in names if 'RSS' in c.upper()), None) or \
              next((c for c in names if '3SIGMA' in c.upper() or 'POS' in c.upper()), None)
        if col is None:
            raise KeyError(f"no 3-sigma position column among {names}")
        rss_arcsec = float(eph[col][0])
        delta_km = float(eph['delta'][0]) * AU_KM
        return rss_arcsec * np.pi / 648000.0 * delta_km
    except Exception as e:                                              # optional lookup: report and fall back
        print(f"No Horizons uncertainty for {target_id}: {e}")
        return None


def write_shadow_kml(paths, filename, title, observer=None, tick_every=10):
    """Write the lines from shadow_path() as KML. observer = (lon_deg, lat_deg) adds a pin.
    Time ticks (UTC, centre-line duration) every tick_every points along the centre line."""
    def line(name, pts, color, width):
        if len(pts) < 2:
            return ""
        coords = " ".join(f"{p[1]:.6f},{p[2]:.6f},0" for p in pts)
        return (f"<Placemark><name>{escape(name)}</name><Style><LineStyle><color>{color}</color>"
                f"<width>{width}</width></LineStyle></Style><LineString><tessellate>1</tessellate>"
                f"<coordinates>{coords}</coordinates></LineString></Placemark>")

    def pin(name, lon, lat, text=""):
        return (f"<Placemark><name>{escape(name)}</name><description>{escape(text)}</description>"
                f"<Point><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point></Placemark>")

    parts = [line("Centre line", paths['center'], "ff00ff00", 3),             # KML colours are aabbggrr
             line("Shadow limit A", paths['edge_plus'], "ff0000ff", 2),
             line("Shadow limit B", paths['edge_minus'], "ff0000ff", 2),
             line("3-sigma limit A", paths['sigma_plus'], "ff00ffff", 2),
             line("3-sigma limit B", paths['sigma_minus'], "ff00ffff", 2)]
    for i, (et, lon, lat, dur) in enumerate(paths['center']):
        if i % tick_every == 0:
            parts.append(pin(spice.et2utc(et, 'ISOC', 0)[11:16] + " UTC", lon, lat,
                             f"max duration {dur:.2f} s" if dur else ""))
    if observer is not None:
        parts.append(pin("Observer", observer[0], observer[1]))

    kml = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           f"<name>{escape(title)}</name>" + "".join(parts) + "</Document></kml>")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(kml)
    return filename
