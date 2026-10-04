"""pyoccult_astrometry.py - astrometric corrections of a star's direction at an event (see ABOUT.md Part 6).

Gaia DR3 gives barycentric directions free of light deflection. The asteroid comes from SPICE ('CN': light-time
corrected, no aberration, no deflection). Two corrections make the star match what the observer really sees relative
to the asteroid:

  stellar parallax   the star seen from the Earth instead of the solar system barycentre (Gaia parallax > 0 only)
  light deflection   the gravitational bending by the Sun, Jupiter and Saturn. The asteroid's light is bent too,
                     less because it is closer; since the asteroid stays undeflected (SPICE), the star is moved by
                     the difference star minus asteroid, which keeps their relative geometry right.

Deflection of a source in direction p seen from an observer at distance E from a body (unit vector e from the body to
the observer), q = unit vector from the body to the source (q = p for a star), PPN formula for a finite source:

    dp = (2 GM / c^2 E) * (e - (p.e) p) / (1 + q.e)

(4.07 mas at elongation 90 deg from the Sun, 1.75" at the solar limb). Pure math; SPICE is passed in, so this module
has no state and the tests can use a stand-in. Used by pyoccult.handle_star.
"""
from pyoccult_version import __version__
import numpy as np

C_KM_S = 299792.458
PC_KM = 3.0856775814913673e13
RAD2MAS = np.degrees(1.0) * 3.6e6
# GM, km^3/s^2 (DE440); planets as system barycentres (de440.bsp has them; mas-level deflection is insensitive to it)
GM = {"10": 1.32712440041279419e11, "5": 1.267127641e8, "6": 3.79405848418e7}
BODY_NAMES = {"10": "Sun", "5": "Jupiter", "6": "Saturn"}


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def angle_mas(a, b):
    """Angle between two unit vectors, mas (accurate for tiny angles)."""
    return float(np.arctan2(np.linalg.norm(np.cross(a, b)), np.dot(a, b)) * RAD2MAS)


def deflect(p, obs_from_body_km, q, gm):
    """Deflection vector (to add to p) of a source in direction p (unit), observer at obs_from_body_km from the body,
    q = unit vector from the body to the source (q = p for a star at infinity)."""
    obs = np.asarray(obs_from_body_km, float)
    E = np.linalg.norm(obs)
    e = obs / E
    den = 1.0 + float(np.dot(q, e))
    if den < 1e-12:                                   # source exactly behind the body: not observable anyway
        return np.zeros(3)
    return (2.0 * gm / (C_KM_S ** 2 * E)) * (e - np.dot(p, e) * p) / den


def parallax_dir(u_bary, plx_mas, earth_from_ssb_km):
    """The star's direction from the Earth instead of the barycentre (unchanged if the parallax is not > 0)."""
    if not plx_mas or not np.isfinite(plx_mas) or plx_mas <= 0:
        return np.asarray(u_bary, float)
    return unit(np.asarray(u_bary, float) * (1000.0 / plx_mas) * PC_KM - np.asarray(earth_from_ssb_km, float))


def corrected_star_dir(spice, u_bary, plx_mas, et, target, parallax=True, deflection=True, bodies=("10", "5", "6")):
    """(direction, info): the star's corrected J2000 direction at et (unit vector) and the sizes of the corrections,
    info = {'parallax_mas', 'deflection_mas', 'deflection_by': {body: mas}}. target: the asteroid's SPICE name/id."""
    p = unit(u_bary)
    info = {"parallax_mas": 0.0, "deflection_mas": 0.0, "deflection_by": {}}
    if parallax:
        earth = np.asarray(spice.spkpos("399", et, "J2000", "NONE", "0")[0])
        p2 = parallax_dir(p, plx_mas, earth)
        info["parallax_mas"] = angle_mas(p, p2)
        p = p2
    if deflection:
        ast = np.asarray(spice.spkpos(str(target), et, "J2000", "CN", "399")[0])   # Earth -> asteroid (as the solver)
        p0, shift = p, np.zeros(3)
        for b in bodies:
            body = np.asarray(spice.spkpos(b, et, "J2000", "CN", "399")[0])        # Earth -> body
            obs_from_body = -body
            d = deflect(p, obs_from_body, p, GM[b]) - deflect(p, obs_from_body, unit(ast - body), GM[b])
            info["deflection_by"][BODY_NAMES.get(b, b)] = float(np.linalg.norm(d) * RAD2MAS)
            shift += d
        p = unit(p0 + shift)
        info["deflection_mas"] = angle_mas(p0, p)
    return p, info
