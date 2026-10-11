"""earth.py - the reference ellipsoid for geodetic coordinates: WGS84, as GPS positions and Occult's paths use.

Geodetic longitude, latitude and height (sites, shadow paths) are always converted with these constants, not with the
SPICE kernel's Earth radii (pck00010: a = 6378.1366 km, c = 6356.7519 km, the IAU values, each ~0.4 m off WGS84).
Shadow paths are the points on this ellipsoid's surface (height 0 m), like Occult's default output.
"""
A_KM = 6378.137                               # WGS84 semi-major axis, km
F = 1.0 / 298.257223563                       # WGS84 flattening
C_KM = A_KM * (1.0 - F)                       # semi-minor (polar) axis, 6356.752314 km
NAME = "WGS84"
