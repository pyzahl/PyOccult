"""shadowtrack.py - the shadow of an asteroid on the Earth from a few stored numbers (pre-screens).

Per event (asteroid, star, closest approach to the Earth's centre at tc) the shadow axis moves across the
fundamental plane (z towards the star, x east, y north, through the Earth's centre) almost uniformly for the few
minutes to hours it takes to cross the Earth. Stored: the star direction and a quadratic in time

    x(t) = x0 + vx dt + ax dt^2,   y(t) = y0 + vy dt + ay dt^2,   dt = t - tc,   |dt| <= half

(km, km/s, km/s^2), fitted to the integrated orbit at -half, 0, +half, with the largest misfit at 9 points (err, km).
This is the idea of Besselian elements (Occult), enough to decide which events can be seen from a site or a region:

- site test: the site's position in the plane at the same times (the Earth's rotation from SPICE on a 1-min grid);
  kept if the shadow line passes within radius + reach + err of it with the star up and the Sun down there;
- region test: the ground track of the shadow axis (the plane point projected onto the Earth along the star
  direction, sampled), kept if it touches a lat/lon box widened by radius + reach + half the sample spacing, with
  the star up and the Sun down at that point.
Both are supersets on purpose (loose margins); the pick then computes every kept asteroid exactly.
"""
import math
import numpy as np

OMEGA = 7.2921150e-5                         # Earth's rotation, rad/s (sidereal)
EARTH_R_KM = 6378.137
TOL_KM = 10.0                                # extra margin of the site test (sampling, site height, geoid)
TOL_DEG = 1.0                                # extra margin of the star and Sun altitude limits
N_SAMPLES = 81                               # samples along +-half: site test (segment distances: exact enough)
N_TRACK = 161                                # samples along +-half: ground tracks (vs 1281: none missed, 13 % extra)

# one event of a global pre-screen: 80 bytes
DTYPE = np.dtype([("number", "i4"), ("star", "i8"), ("et", "f8"), ("g", "f4"), ("m_ast", "f4"), ("geo_miss", "f4"),
                  ("sx", "f4"), ("sy", "f4"), ("sz", "f4"), ("x0", "f4"), ("y0", "f4"), ("vx", "f4"), ("vy", "f4"),
                  ("ax", "f4"), ("ay", "f4"), ("half", "f4"), ("r_km", "f4"), ("err", "f4")])


def in_box(lat, lon, box, margin_km):
    """Boolean array: (lat, lon) within the box widened by margin_km (scalar or broadcastable; longitudes wrap)."""
    dlat = margin_km / 111.2
    ok = (lat >= box["lat_min"] - dlat) & (lat <= box["lat_max"] + dlat)
    dlon = margin_km / (111.2 * np.maximum(np.cos(np.radians(lat)), 0.02))
    width = (box["lon_max"] - box["lon_min"]) % 360.0 or (360.0 if box["lon_max"] != box["lon_min"] else 0.0)
    rel = (lon - box["lon_min"]) % 360.0                         # 0..360 east of the box's west edge
    return ok & ((rel <= width + dlon) | (rel >= 360.0 - dlon))


def plane(sdir):
    """Fundamental-plane basis (x east, y north) for star directions sdir (k,3)."""
    x = np.cross([0.0, 0.0, 1.0], sdir)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    return x, np.cross(sdir, x)


def interp(g, ets, t):
    """Cubic Lagrange interpolation of g (T,3) sampled at the uniform times ets, at times t (any shape) -> (...,3)."""
    t = np.asarray(t, float)
    step = ets[1] - ets[0]
    x = (t.ravel() - ets[0]) / step
    j = np.clip(np.floor(x).astype(int) - 1, 0, len(ets) - 4)
    s = x - j
    w = np.stack([-(s - 1) * (s - 2) * (s - 3) / 6, s * (s - 2) * (s - 3) / 2, -s * (s - 1) * (s - 3) / 2,
                  s * (s - 1) * (s - 2) / 6], 1)
    out = np.einsum("kq,kqx->kx", w, np.stack([g[j + q] for q in range(4)], 1))
    return out.reshape(t.shape + (3,))


def frames(spice, t0, t1, step_s=600.0):
    """Earth orientation and Sun direction on a grid covering t0..t1: dict(ets, rot (T,3,3) J2000->ITRF93,
    sun_u (T,3) geocentric unit vectors)."""
    ets = np.arange(t0 - 2 * step_s, t1 + 3 * step_s, step_s)
    sun = np.asarray(spice.spkpos("10", ets, "J2000", "LT+S", "399")[0])
    rot = np.array([spice.pxform("J2000", "ITRF93", float(t)) for t in ets])
    return dict(ets=ets, rot=rot, sun_u=sun / np.linalg.norm(sun, axis=1, keepdims=True), step=step_s)


# ---------------------------------------------------------------- elements
def fit(px, py, half):
    """Quadratic elements from plane positions px, py (c,9) at dt = half * linspace(-1, 1, 9). Returns dict of
    x0, y0, vx, vy, ax, ay (c,) and err (c,): the largest misfit (km) at the 9 points."""
    h = half[:, None]
    out = {}
    for a, p in (("x", px), ("y", py)):
        p0, pm, pp = p[:, 4], p[:, 0], p[:, 8]
        out[a + "0"] = p0
        out["v" + a] = (pp - pm) / (2 * half)
        out["a" + a] = (pp - 2 * p0 + pm) / (2 * half * half)
    dt = h * np.linspace(-1, 1, 9)[None, :]
    ex = px - (out["x0"][:, None] + out["vx"][:, None] * dt + out["ax"][:, None] * dt * dt)
    ey = py - (out["y0"][:, None] + out["vy"][:, None] * dt + out["ay"][:, None] * dt * dt)
    out["err"] = np.sqrt(ex * ex + ey * ey).max(axis=1)
    return out


def positions(ev, tau):
    """Plane positions (c,n) of the shadow axis of events ev (DTYPE array) at times tau (c,n)."""
    dt = tau - ev["et"][:, None]
    f = lambda k: ev[k].astype(float)[:, None]
    return f("x0") + f("vx") * dt + f("ax") * dt * dt, f("y0") + f("vy") * dt + f("ay") * dt * dt


def star_dirs(ev):
    s = np.stack([ev["sx"], ev["sy"], ev["sz"]], 1).astype(float)
    return s / np.linalg.norm(s, axis=1, keepdims=True)


def sample_times(tc, half, n=N_SAMPLES):
    return tc[:, None] + half[:, None] * np.linspace(-1, 1, n)[None, :]


# ---------------------------------------------------------------- ground track (build and region test)
def ground_track(px, py, tau, sdir, fr, r_km, box, reach_km, sin_alt, sin_sun):
    """keep (c,) and where (c,4: lat, lon, sun alt, star alt of the first matching sample) for shadow-axis plane
    positions px, py (c,s) at times tau (c,s), star directions sdir (c,3); fr = frames(). Kept if a sample is on the
    Earth (or within radius + reach of its limb) with the star above and the Sun below the limits there and, with a
    box, inside the box widened by radius + reach; all tests widened so that the continuous track is covered (see
    below): a superset. box None: no region test."""
    R = EARTH_R_KM
    ets, rot, sun_u = fr["ets"], fr["rot"], fr["sun_u"]
    ex, ny = plane(sdir)
    r_km = np.broadcast_to(np.asarray(r_km, float), (len(px),))[:, None]
    rho = np.hypot(px, py)
    depth = np.sqrt(np.maximum(R * R - rho * rho, 0.0))                           # towards the star (day side of it)
    scale = np.where(rho > R, R / np.maximum(rho, 1e-9), 1.0)                     # off the limb: the nearest limb point
    s = (px * scale)[..., None] * ex[:, None, :] + (py * scale)[..., None] * ny[:, None, :] \
        + depth[..., None] * sdir[:, None, :]                                      # (c,s,3) J2000, km
    # every test is widened by what can change between two samples (half the step to the neighbours), so a
    # continuous track cannot pass a condition between samples, and the sky test by the distance an observer can be
    # from the axis (radius + reach: their star and Sun altitudes differ by up to that / R radians)
    gs = _half_steps(s)                                                            # (c,s) km on the ground
    ps = _half_steps(np.stack([px, py], 2))                                        # (c,s) km in the plane
    on = rho < R + r_km + reach_km + ps
    tol = (gs + r_km + reach_km) / R                                               # radians (>= change of sin(alt))
    up = s / np.linalg.norm(s, axis=2, keepdims=True)
    star_up = np.einsum("csx,cx->cs", up, sdir)
    i = np.clip(np.round((tau - ets[0]) / fr["step"]).astype(int), 0, len(ets) - 1)
    sun_up = np.einsum("csx,csx->cs", up, sun_u[i])
    ok = on & (star_up > sin_alt - tol) & (sun_up < sin_sun + tol)
    lat = lon = None
    if box is not None:
        ang = OMEGA * (tau - ets[i])                                              # spin since the grid time
        itrf = np.einsum("csij,csj->csi", rot[i], s)
        ca, sa = np.cos(ang), np.sin(ang)
        x, y = ca * itrf[..., 0] + sa * itrf[..., 1], -sa * itrf[..., 0] + ca * itrf[..., 1]
        lat = np.degrees(np.arcsin(np.clip(itrf[..., 2] / R, -1, 1)))
        lon = np.degrees(np.arctan2(y, x))
        ok &= in_box(lat, lon, box, r_km + reach_km + gs)
    first = np.argmax(ok, axis=1)
    c_ = np.arange(len(px))
    if lat is None:
        lat, lon = np.full(px.shape, np.nan), np.full(px.shape, np.nan)
    where = np.stack([lat[c_, first], lon[c_, first], np.degrees(np.arcsin(np.clip(sun_up[c_, first], -1, 1))),
                      np.degrees(np.arcsin(np.clip(star_up[c_, first], -1, 1)))], 1)
    return ok.any(axis=1), where


def _half_steps(p):
    """Half the distance from each sample to the farther of its neighbours along axis 1: p (c,s,k) -> (c,s)."""
    d = np.linalg.norm(np.diff(p, axis=1), axis=2) if p.shape[1] > 1 else np.zeros((p.shape[0], 0))
    out = np.zeros(p.shape[:2])
    if d.shape[1]:
        out[:, :-1] = d
        out[:, 1:] = np.maximum(out[:, 1:], d)
    return 0.5 * out


def region_mask(spice, ev, box, reach_km, min_alt, max_sun_alt, block=5000):
    """Events (DTYPE array) whose ground track touches the box (see ground_track): keep (c,), where (c,4)."""
    keep, where = np.zeros(len(ev), bool), np.full((len(ev), 4), np.nan)
    if not len(ev):
        return keep, where
    sin_alt = math.sin(math.radians(min_alt - TOL_DEG))
    sin_sun = math.sin(math.radians(max_sun_alt + TOL_DEG))
    for b0 in range(0, len(ev), block):
        e = ev[b0:b0 + block]
        tau = sample_times(e["et"], e["half"].astype(float), N_TRACK)
        fr = frames(spice, tau.min(), tau.max())
        px, py = positions(e, tau)
        r = e["r_km"].astype(float) + e["err"].astype(float)
        keep[b0:b0 + block], where[b0:b0 + block] = ground_track(px, py, tau, star_dirs(e), fr, r, box, reach_km,
                                                                 sin_alt, sin_sun)
    return keep, where


# ---------------------------------------------------------------- site test
def site_mask(spice, ev, lat, lon, ele_m, reach_km, min_alt, max_sun_alt, block=20000):
    """Events (DTYPE array) whose shadow passes within radius + reach (+ err + TOL_KM) of the site while the star is
    above min_alt and the Sun below max_sun_alt there (limits widened by TOL_DEG). Returns keep (c,)."""
    from pyoccult import screen as SC
    keep = np.zeros(len(ev), bool)
    if not len(ev):
        return keep
    site = SC.Site(spice, lat, lon, ele_m)
    sin_alt = math.sin(math.radians(min_alt - TOL_DEG))
    sin_sun = math.sin(math.radians(max_sun_alt + TOL_DEG))
    t_lo = float((ev["et"] - ev["half"]).min()) - 120.0
    t_hi = float((ev["et"] + ev["half"]).max()) + 120.0
    grid = np.arange(t_lo - 180.0, t_hi + 240.0, 60.0)                             # site position every minute
    pos, up = site.at(grid)
    sgrid = np.arange(t_lo - 1200.0, t_hi + 1800.0, 600.0)
    sun = np.asarray(spice.spkpos("10", sgrid, "J2000", "LT+S", "399")[0])
    sun /= np.linalg.norm(sun, axis=1, keepdims=True)
    for b0 in range(0, len(ev), block):
        e = ev[b0:b0 + block]
        tau = sample_times(e["et"], e["half"].astype(float))                       # (c,n)
        px, py = positions(e, tau)
        sdir = star_dirs(e)
        ex, ny = plane(sdir)
        S = interp(pos, grid, tau)                                                  # (c,n,3)
        U = interp(up, grid, tau)
        U /= np.linalg.norm(U, axis=2, keepdims=True)
        rx = px - np.einsum("cnx,cx->cn", S, ex)
        ry = py - np.einsum("cnx,cx->cn", S, ny)
        # closest distance on each segment between samples (relative motion linear there)
        ax_, ay_ = rx[:, :-1], ry[:, :-1]
        dx, dy = np.diff(rx, axis=1), np.diff(ry, axis=1)
        u = np.clip(-(ax_ * dx + ay_ * dy) / np.maximum(dx * dx + dy * dy, 1e-12), 0.0, 1.0)
        dist = np.hypot(ax_ + u * dx, ay_ + u * dy)                                 # (c,n-1)
        star_up = np.einsum("cnx,cx->cn", U, sdir)
        sun_up = np.einsum("cnx,cnx->cn", U, interp(sun, sgrid, tau))
        ok_end = (star_up > sin_alt) & (sun_up < sin_sun)
        thr = (e["r_km"].astype(float) + e["err"].astype(float) + reach_km + TOL_KM)[:, None]
        keep[b0:b0 + block] = ((dist <= thr) & (ok_end[:, :-1] | ok_end[:, 1:])).any(axis=1)
    return keep
