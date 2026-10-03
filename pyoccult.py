#!.venv/bin/python3
import sys, base64, functools, os, re, time
T_START = time.time()                    # run statistics: start-up time is measured from here
from datetime import datetime
import numpy as np
import requests
import json
import subprocess
import pandas as pd
from pathlib import Path

from scipy.optimize import minimize_scalar
import spiceypy as spice
from astropy import units as u
from astropy.time import Time
from astropy.coordinates import EarthLocation
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.jplhorizons import Horizons
from astroquery.gaia import Gaia

# to Silence Warnings:
import warnings, erfa
warnings.filterwarnings("ignore", category=erfa.ErfaWarning)

import pyoccult_config as config
from pyoccult_paths import shadow_path, path_sigma3_km, write_shadow_kml
import pyoccult_corridor as corridor
import pyoccult_sbdb as sbdb_cache
import pyoccult_screen as screen          # OWC observability formula, extinction

########################## PROLOGUE KERNEL INIT SECTION


if config.force_cleanup:
    print ('Cleanup old files:')
    for filename in ["naif0012.tls", "de440.bsp", "pck00010.tpc", "earth_latest_high_prec.bpc"]:
        if os.path.exists(filename):
            print ('removing: ', filename)
            os.remove(filename)

# Wipe out old file/memory states completely
spice.clpool()



from pyoccult_kernels import check_file_age, download_kernels, pck_comment_dates


# ==========================================
# KERNEL DOWNLOADING UTILITY
# ==========================================



EARTH_PCK = {}                                     # coverage of the Earth orientation file (run summary)
if download_kernels(config.earth_pck_max_age):
    try:
        print ('* Loading Compute Kernels *')
        # Load all required kernels
        spice.furnsh("naif0012.tls")       # Leapseconds
        spice.furnsh("pck00010.tpc")       # Planetary constants
        spice.furnsh("de440.bsp")          # Major planets base
        spice.furnsh("earth_latest_high_prec.bpc")
        
        cover = spice.stypes.SPICEDOUBLE_CELL(1000)
        spice.pckcov("earth_latest_high_prec.bpc", 3000, cover)      # 3000 = ITRF93 segments, verify
        EARTH_PCK = pck_comment_dates("earth_latest_high_prec.bpc")
        EARTH_PCK["stop"] = spice.et2utc(spice.wnfetd(cover, spice.wncard(cover) - 1)[1], 'ISOC', 0)
        _win_end = spice.et2utc(spice.str2et(str(config.ct)) + config.days * 86400.0, 'ISOC', 0)
        print ('---------------------------------------------')
        print (f"* Earth PCK of {EARTH_PCK['created'] or '?'}: measured to {EARTH_PCK['last_datum'] or '?'}, "
               f"predicted to {EARTH_PCK['stop'][:10]}")
        if _win_end > EARTH_PCK["stop"]:
            sys.exit(f"Search window ends {_win_end[:10]}, after the Earth orientation file ({EARTH_PCK['stop'][:10]}): "
                     f"shorten the window (days) or refresh earth_latest_high_prec.bpc (delete it, rerun)")
        print ('---------------------------------------------')
    
        print ('* Testing Compute Kernels *')
        
        et = spice.str2et("2026-09-28 UTC")
        print(f"🚀 Success! CSPICE Active. Target ET: {et}")
        print ('---------------------------------------------')
        print ('---------- COMPUTE SYSTEM READY -------------')
        print ('---------------------------------------------')
            
    except Exception as e:
        print ('---------------------------------------------')
        print(f"CSPICE Error: {e}")
        print ('---------------------------------------------')
        sys.exit('Exiting as of error.')

########################## PROLOGUE KERNEL INIT SECTION END




### NOW OCCULT CALC AND STAR+ASTEROID EPH MANAGEMENT

PC_KM = 3.0856775814913673e13
def geocentric_star_dir(ra_deg, dec_deg, plx_mas, et):
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    u_bary = np.array([np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)])
    earth, _ = spice.spkpos('399', et, 'J2000', 'NONE', 'SSB')
    v = u_bary * (1000.0 / max(plx_mas, 0.01)) * PC_KM - earth
    return v / np.linalg.norm(v)


def observer_j2000(et, obs_geo):
    radii = spice.bodvrd('EARTH', 'RADII', 3)[1]
    f = (radii[0] - radii[2]) / radii[0]
    itrf = spice.georec(obs_geo['lon'], obs_geo['lat'], obs_geo['alt'], radii[0], f)
    return spice.pxform('ITRF93', 'J2000', et) @ itrf

def moon_info(et, star_dir, obs_geo):
    moon_geo, _ = spice.spkpos('MOON', et, 'J2000', 'LT+S', '399')
    moon_topo = moon_geo - observer_j2000(et, obs_geo)
    sep = np.degrees(spice.vsep(moon_topo, star_dir))

    moon_from_sun, _ = spice.spkpos('MOON', et, 'J2000', 'LT+S', 'SUN')
    alpha = spice.vsep(moon_from_sun, moon_geo)              # phase angle at the Moon
    illum = 100.0 * (1 + np.cos(alpha)) / 2

    sun_geo, _ = spice.spkpos('SUN', et, 'J2000', 'LT+S', '399')
    R = spice.pxform('J2000', 'ECLIPJ2000', et)
    mv, sv = R @ moon_geo, R @ sun_geo
    age = np.degrees(np.arctan2(mv[1], mv[0]) - np.arctan2(sv[1], sv[0])) % 360.0

    return dict(moon_sep_deg=sep, moon_alt_deg=alt_deg(et, moon_topo, obs_geo),
                moon_illum_pct=illum, moon_age_deg=age)

def gaia_cone(ra_deg, dec_deg, radius_arcmin, mag_limit):
    """Archive cone query, used only by the old "windows" search mode (the corridor mode reads the local Gaia copy).
    Not cached. Async: the sync launch_job silently truncates at 2000 rows."""
    query = f"""
    SELECT 
        source_id, ra, dec, parallax, pmra, pmdec, phot_g_mean_mag, ruwe
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra_deg}, {dec_deg}, {radius_arcmin / 60.0}))
    AND phot_g_mean_mag <= {mag_limit}
    AND pmra IS NOT NULL AND pmdec IS NOT NULL -- Required for propagation
    AND ruwe < 1.4
    """
    try:
        return Gaia.launch_job_async(query).get_results().to_pandas()
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# fetch_and_propagate_stars(): df = gaia_cone(...).copy(); then your existing SkyCoord /
# apply_space_motion block, unchanged. Never cache that part.

def fetch_and_propagate_stars(
    ra_deg, dec_deg, event_time_str, radius_arcmin=10.0, mag_limit=16.0
):
    """Fetches Gaia DR3 stars and propagates their RA/Dec to a specific event time.

    Parameters:
    ra_deg (float): Center RA in decimal degrees (ICRS)
    dec_deg (float): Center Dec in decimal degrees (ICRS)
    event_time_str (str): Target date/time in ISO format (e.g., '2026-11-05
    12:00:00')
    radius_arcmin (float): Cone search radius in arcminutes
    mag_limit (float): Faintest G-band magnitude to include
    """
    # Parse target time and define reference epochs
    target_time = Time(event_time_str, scale="utc")
    gaia_epoch = Time("2016-01-01T12:00:00", scale="tcb")  # Gaia DR3 J2016.0 reference
    # gaia_cone(...)      -> raw Gaia table (epoch 2016.0)
    # propagate(df, time) -> adds ra_YYYYMMDD / dec_YYYYMMDD, never cached
    
    print(
        f"Querying Gaia DR3 & propagating positions to: {target_time.iso} UTC..."
    )

    df = gaia_cone(ra_deg, dec_deg, radius_arcmin, mag_limit)
    if df is None:
        return None
        
    # Handle missing or negative parallaxes safely by clipping them to 0 (very distant stars)
    #safe_parallax = np.where(
    #    df["parallax"].isna() | (df["parallax"] < 0), 0, df["parallax"]
    #)
    safe_parallax = np.clip(df["parallax"].fillna(0.0).to_numpy(), 0.01, None)   # mas, i.e. 100 kpc max
    
    # Initialize SkyCoord array at the native Gaia J2016.0 epoch
    stars_j2016 = SkyCoord(
        ra=df["ra"].values * u.deg,
        dec=df["dec"].values * u.deg,
        distance=CoordinateDistance(safe_parallax),
        pm_ra_cosdec=df["pmra"].values * u.mas / u.yr,
        pm_dec=df["pmdec"].values * u.mas / u.yr,
        obstime=gaia_epoch,
        frame="icrs",
    )
    
    # Apply 3D space motion propagation to the target event epoch
    # This handles proper motion and positional changes accurately
    stars_target_epoch = stars_j2016.apply_space_motion(
        new_obstime=target_time
    )
    
    # Append the new highly precise computed coordinates back into the table
    df[f"ra_{target_time.datetime.strftime('%Y%m%d')}"] = (
        stars_target_epoch.ra.deg
    )
    df[f"dec_{target_time.datetime.strftime('%Y%m%d')}"] = (
        stars_target_epoch.dec.deg
    )

    print(f"Successfully processed {len(df)} stars.")
    return df



def CoordinateDistance(parallax_mas):
    """Helper to convert parallax safely to distance."""
    # Where parallax is 0, place the star effectively at infinity (100,000 parsecs)

    # Create a mask for where the parallax is safe
    condition = parallax_mas > 0

    # Compute safely: out fills the fallback value, where restricts execution
    distance_pc = np.divide(1000.0, parallax_mas, out=np.full_like(parallax_mas, 100000.0), where=condition)
    return distance_pc * u.pc


    
    


def list_spk_contents(kernel_path):
    # Find all unique object IDs tracked in the BSP file
    objects = spice.spkobj(kernel_path)
    
    print(f"Found {len(objects)} objects in {kernel_path}:\n")
    print(f"{'Object NAIF ID':<15} | {'Coverage Start (ET)':<20} | {'Coverage End (ET)':<20}")
    print("-" * 62)
    
    for obj_id in objects:
        # Retrieve the coverage windows for each object
        cover = spice.spkcov(kernel_path, obj_id)
        
        # Iterate over the distinct intervals within the window
        num_intervals = spice.wncard(cover)
        for i in range(num_intervals):
            # Extract start and end times in Ephemeris Time (seconds past J2000)
            start_et, end_et = spice.wnfetd(cover, i)
            
            # (Optional) Convert ET to a human-readable UTC string
            # Requires loading a leapseconds kernel (tls) if you want to use spice.et2utc
            
            print(f"{obj_id:<15} | {start_et:<20.3f} | {end_et:<20.3f}")



        
# 20028119, 28119 (1998 SX71),28119

#+20000000
def get_asteroid_name(spk_id):
    """Full name ("218001 (2001 XQ72)") from the SBDB size cache (fetched and cached if missing); the number if SBDB
    cannot be reached. Accepts the asteroid number or its SPK id (20000000 + number)."""
    n = int(spk_id)
    n = n - 20000000 if n >= 20000000 else n
    phys = sbdb_phys(n)
    return ((phys or {}).get("_fullname") or "").strip() or f"({n})"



_loaded = {}    # asteroid number -> NAIF id

def fetch_target_orbit(target_id, epochs, cache_dir=config.cache_path):
    target_id = str(target_id)
    fn = Path(cache_dir) / f"PyOccult_asteroid_{target_id}_{epochs['start']}_{epochs['stop']}.bsp"
    if not fn.is_file():
        resp = requests.get(
            "https://ssd.jpl.nasa.gov/api/horizons.api",
            params={'format': 'json', 'COMMAND': target_id + ';', 'EPHEM_TYPE': 'SPK',
                    'MAKE_EPHEM': 'YES', 'START_TIME': epochs['start'],
                    'STOP_TIME': epochs['stop'], 'OBJ_DATA': 'NO'},
            timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if 'spk' not in data:
            raise RuntimeError(f"Horizons gave no SPK for {target_id}: {str(data.get('result', data))[:300]}")
        fn.write_bytes(base64.b64decode(data['spk']))
    if target_id not in _loaded:
        spice.furnsh(str(fn))
        _loaded[target_id] = int(spice.spkobj(str(fn))[0])
        spice.boddef(target_id, _loaded[target_id])     # keep alias if callers still pass the number
    return _loaded[target_id]                           # NAIF id, safe to use directly in spkpos

SIZE_OVERRIDES = {}   # curate best values here: {"19": (r_km, r_sigma_km, "source note")}; they take priority

# Size bounds: r_km is the nominal radius; r_min_km / r_max_km are about +/-3 sigma, or the albedo range for H-only
# objects, widened by the tri-axial extent if given. They reflect size uncertainty only, not ephemeris uncertainty.

def sbdb_phys(target_id, timeout=30):
    """Raw SBDB physical parameters {name: {value, sigma, ref, ...}} plus '_fullname', from the shared cache
    (pyoccult_sbdb.py; also filled by pyoccult_pick.py) or the SBDB API. Returns None if SBDB cannot be reached and
    nothing is cached (failures are not cached)."""
    n = str(target_id).strip()
    hit, fresh = sbdb_cache.get(n, config.cache_path, getattr(config, "sbdb_max_age_days", 30))
    if fresh:
        return hit["phys"]
    try:
        resp = requests.get("https://ssd-api.jpl.nasa.gov/sbdb.api", params={"sstr": n, "phys-par": 1}, timeout=timeout)
        resp.raise_for_status()
        entry = sbdb_cache.entry_from_api(resp.json())
    except (requests.RequestException, ValueError) as e:
        print(f"SBDB lookup failed for {n}: {e}")
        return hit["phys"] if hit else None                       # stale data beats none
    sbdb_cache.put({n: entry}, config.cache_path)
    return entry["phys"]


@functools.lru_cache(maxsize=None)
def get_asteroid_size(target_id, timeout=30):
    """Return dict(r_km, r_min_km, r_max_km, source, H, G), or None if nothing usable."""
    n = str(target_id).strip()
    pp = sbdb_phys(n, timeout)                 # also for overrides: H and G for the asteroid magnitude

    def num(name, key="value"):
        try:
            return float(pp[name][key])
        except (KeyError, TypeError, ValueError):
            return None

    H, G = (num("H"), num("G")) if pp else (None, None)
    if n in SIZE_OVERRIDES:
        r, sg, src = SIZE_OVERRIDES[n]
        return dict(r_km=r, r_min_km=max(r - 3*sg, 0.0), r_max_km=r + 3*sg, source=src, H=H, G=G)
    if pp is None:
        return None

    D = num("diameter")
    if D:
        sg = num("diameter", "sigma") or num("diameter_sigma") or 0.15 * D   # assume 15% if absent
        out = dict(r_km=D/2, r_min_km=max((D - 3*sg)/2, 0.0), r_max_km=(D + 3*sg)/2,
                   source=f"SBDB diameter (ref {pp['diameter'].get('ref', '?')})", H=H, G=G)
        ext = [float(x) for x in re.findall(r"[\d.]+", str(pp.get("extent", {}).get("value", "")))]
        if len(ext) >= 2:                      # tri-axial full dimensions -> semi-axes
            out["r_min_km"] = min(out["r_min_km"], min(ext)/2)
            out["r_max_km"] = max(out["r_max_km"], max(ext)/2)
        return out

    if H is None:
        return None                            # no diameter and no H: no size estimate possible

    Dp = lambda p: 1329.0 / np.sqrt(p) * 10**(-H/5)
    p = num("albedo")
    if p:
        return dict(r_km=Dp(p)/2, r_min_km=Dp(min(p*1.5, 1))/2, r_max_km=Dp(p/1.5)/2, source="H + SBDB albedo", H=H, G=G)
    return dict(r_km=Dp(0.14)/2, r_min_km=Dp(0.30)/2, r_max_km=Dp(0.05)/2, source="H only, albedo assumed", H=H, G=G)



def get_asteroid_ra_dec(target_id, utc_time, observer="EARTH", ref_frame="J2000", abcorr="LT+S"):
    """Calculates the high-precision RA and Dec of an asteroid using SPICE.

    Parameters:
    target_id (str): SPICE ID of the asteroid (e.g., '2000433' for Eros)
    utc_time (str): Target timestamp (e.g., '2026-11-05 04:15:30')
    observer (str): Observer location frame ('EARTH' or a topocentric ID)
    ref_frame (str): Inertial reference frame (typically 'J2000' or 'ICRF')
    abcorr (str): Aberration correction. Use 'LT+S' for occultations.
    """
    # 1. Load the essential SPICE kernels into the pool
    # Make sure these files are downloaded to your local working directory
    #try:
    #    spice.furnsh("naif0012.tls")  # Leapseconds kernel
    #    spice.furnsh("de440.bsp")  # Planetary ephemeris kernel
        # spice.furnsh("your_asteroid.bsp") # Uncomment and add your asteroid SPK here
    #except Exception as e:
    #    print(f"Kernel loading error: {e}")
    #    print(
    #        "Please ensure 'naif0012.tls' and 'de440.bsp' exist in this path."
    #    )
    #    return

    try:
        # 2. Convert human-readable UTC to Ephemeris Time (seconds past J2000)
        et = spice.str2et(utc_time)

        # 3. Compute the relative state vector (position and velocity)
        # Returns a 6-element list [x, y, z, vx, vy, vz] and light time
        state, lt = spice.spkezr(target_id, et, ref_frame, abcorr, observer)

        # Extract the rectangular position component vector [x, y, z]
        position = state[0:3]

        # 4. Convert rectangular coordinates to Spherical (Range, RA, Dec)
        # Output angles are explicitly returned in radians
        range_km, ra_rad, dec_rad = spice.recrad(position)

        # Convert the radian dimensions cleanly to degrees
        ra_deg = ra_rad * spice.dpr()
        dec_dec = dec_rad * spice.dpr()

        # Print clean results matrix
        print(f"Target SPICE ID   : {target_id}")
        print(f"Observation Time  : {utc_time} UTC")
        print(f"Ephemeris Time(ET): {et:.6f}")
        print("-" * 45)
        print(f"Right Ascension   : {ra_deg:12.6f}°")
        print(f"Declination       : {dec_dec:12.6f}°")
        print(f"Distance (Range)  : {range_km:12.3f} km")
        print(f"One-way Light Time: {lt:12.6f} seconds")

        return {"ra": ra_deg, "dec": dec_dec, "range": range_km, "et": et}

    except spice.utils.support_types.SpiceyError as e:
        print(f"\nSPICE Processing Error: {e}")
        print(
            f"Note: If it says target '{target_id}' was not found, you need to load"
        )
        print("the specific asteroid's .bsp kernel file via spice.furnsh().")
        sys.exit('Exiting as of error.')




AU_KM = 149597870.7

def apparent_mag_HG(et, target, H, G=0.15):
    ast_from_earth, _ = spice.spkpos(target, et, 'J2000', 'LT', '399')
    ast_from_sun, _   = spice.spkpos(target, et, 'J2000', 'LT', 'SUN')
    delta = np.linalg.norm(ast_from_earth) / AU_KM
    r     = np.linalg.norm(ast_from_sun) / AU_KM
    alpha = spice.vsep(ast_from_sun, ast_from_earth)      # phase angle at the asteroid, rad
    t = np.tan(alpha / 2)
    phi1, phi2 = np.exp(-3.33 * t**0.63), np.exp(-1.87 * t**1.22)
    return H + 5*np.log10(r * delta) - 2.5*np.log10((1 - G)*phi1 + G*phi2)


def besselian_offsets(et, star_vector, observer_geo, asteroid_target):
    """Offsets (km) of the shadow axis from the observer on the fundamental plane.
    x points east, y points celestial north; the value is asteroid axis minus observer."""
    # Plane basis: z toward the star, x east, y north
    z_axis = star_vector / np.linalg.norm(star_vector)
    x_axis = np.cross([0.0, 0.0, 1.0], z_axis)
    if np.linalg.norm(x_axis) < 1e-12:          # star at a celestial pole
        x_axis = np.array([1.0, 0.0, 0.0])
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    M = np.vstack((x_axis, y_axis, z_axis))

    # Asteroid relative to Earth's center (399), light time only, no stellar aberration
    ast_pos, _ = spice.spkpos(str(asteroid_target), et, 'J2000', 'CN', '399')

    # Observer, geocentric J2000 (lon/lat in radians, alt in km)
    radii = spice.bodvrd('EARTH', 'RADII', 3)[1]
    flat = (radii[0] - radii[2]) / radii[0]
    obs_itrf = spice.georec(observer_geo['lon'], observer_geo['lat'],
                            observer_geo['alt'], radii[0], flat)
    obs_j2000 = spice.pxform('ITRF93', 'J2000', et) @ obs_itrf

    d = M @ (ast_pos - obs_j2000)
    return d[0], d[1]


def get_besselian_miss_distance(*args):
    return np.hypot(*besselian_offsets(*args))

def event_metrics(et, star_dir, obs_geo, target, r_km, m_star, m_ast, dt=1.0):
    dx0, dy0 = besselian_offsets(et - dt, star_dir, obs_geo, target)
    dx1, dy1 = besselian_offsets(et + dt, star_dir, obs_geo, target)
    dx,  dy  = besselian_offsets(et,      star_dir, obs_geo, target)
    v     = np.hypot(dx1 - dx0, dy1 - dy0) / (2*dt)       # shadow speed vs observer, km/s
    b     = np.hypot(dx, dy)                               # impact parameter, km
    chord = 2*np.sqrt(max(r_km**2 - b**2, 0.0))
    drop  = 2.5*np.log10(1 + 10**(0.4*(m_ast - m_star)))
    return dict(speed_kms=v, chord_km=chord, duration_s=chord/v, mag_drop=drop)



def _up_j2000(et, obs_geo):
    lon, lat = obs_geo['lon'], obs_geo['lat']
    up_itrf = np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
    return spice.pxform('ITRF93', 'J2000', et) @ up_itrf

def sun_alt_deg(et, obs_geo):
    sun, _ = spice.spkpos('SUN', et, 'J2000', 'LT+S', '399')
    return np.degrees(np.arcsin(_up_j2000(et, obs_geo) @ (sun / np.linalg.norm(sun))))

def alt_deg(et, direction, obs_geo):
    return np.degrees(np.arcsin(_up_j2000(et, obs_geo) @ (direction / np.linalg.norm(direction))))


def observable(et, star_dir, obs_geo, min_star_alt=config.MIN_STAR_ALT, max_sun_alt=config.MAX_SUN_ALT):
    star_alt = alt_deg(et, star_dir, obs_geo)
    sun_alt = sun_alt_deg(et, obs_geo)
    return bool(star_alt > min_star_alt and sun_alt < max_sun_alt), star_alt, sun_alt

def window_is_observable(et0, span, obs_geo, target_id, min_star_alt=config.MIN_STAR_ALT, max_sun_alt=config.MAX_SUN_ALT, alt_margin=config.ALT_MARGIN):
    for e in (et0 - span/2, et0, et0 + span/2):
        ast, _ = spice.spkpos(target_id, e, 'J2000', 'CN', '399')
        if (sun_alt_deg(e, obs_geo) < max_sun_alt and
                alt_deg(e, ast, obs_geo) > min_star_alt - alt_margin):
            return True
    return False




# ==========================================
# 3. EXECUTION AND TEST HARNESS
# ==========================================
def star_test (loc = EarthLocation(lat=40.7128*u.deg, lon=-74.0060*u.deg, height=10*u.m),
               center_time_utc = "2026-10-01T04:30:00", time_span = 24*3600,
               star_ra=np.radians(68.98), star_dec=np.radians(16.50),
               asteroid_id = "200019",
               r_asteroid_km = 50.0,
               r_search_km = 0.0):
    # Define Target Star Coordinates (ICRS / J2000)
    # Example: Aldebaran or target star of choice
    #star_ra = np.radians(68.98)   # RA in radians
    #star_dec = np.radians(16.50)  # Dec in radians
    
    # Unit vector pointing to the star
    star_direction = np.array([
        np.cos(star_dec) * np.cos(star_ra),
        np.cos(star_dec) * np.sin(star_ra),
        np.sin(star_dec)
    ])

    # Define Target Asteroid (SPICE ID or Name string if loaded in kernel)
    # For this demonstration template, we fall back to '301' (Moon) if specific asteroid .bsp isn't found
    #asteroid_id = "200019"  # Example SPICE ID for Asteroid 19 Fortuna

    # Define Observer Location via Astropy
    #loc = EarthLocation(lat=40.7128*u.deg, lon=-74.0060*u.deg, height=10*u.m)
    obs_geo = {
        'lon': loc.lon.to(u.rad).value,
        'lat': loc.lat.to(u.rad).value,
        'alt': loc.height.to(u.km).value
    }

    
    # Center-of-window Guess Time (UTC)
    # center_time_utc = "2026-10-01T04:30:00"

    #print (loc, obs_geo, center_time_utc)

    et_center = spice.str2et(center_time_utc)
    
    print(f"Targeting window around: {center_time_utc} UTC")
    print(f"Initial Ephemeris Time (ET): {et_center:.3f}\n")

    # Objective in seconds from et_center: the bounded solver's tolerance is sqrt(eps)*|x| + xatol/3, which for a raw
    # ET (~8.4e8 s) is ~12 s, i.e. tens of km of miss distance. With a small offset xatol really applies.
    def objective_func(dt):
        return get_besselian_miss_distance(et_center + dt, star_direction, obs_geo, asteroid_id)

    time_span2 = time_span/2
    print("Computing exact time of closest approach...")
    result = minimize_scalar(
        objective_func,
        bounds=(-time_span2, time_span2),
        method='bounded',
        options={'xatol': 1e-3, 'maxiter': 1000} # ~1 ms
    )

    if result.success:
        best_et = et_center + result.x
        min_distance = result.fun
        best_utc = spice.et2utc(best_et, "ISOC", 3)
        
        print("\n--- OCCULTATION SOLVER RESULTS ---")
        print(f"Time of Maximum Occultation: {best_utc} UTC")
        print(f"Minimum Shadow Axis Distance to Observer: {min_distance:.3f} km")
        
        # Real-world condition mapping:
        # Assuming an asteroid radius R_ast (e.g., 50 km)
        #r_asteroid_km = 50.0 
        if min_distance < r_asteroid_km:

            print(f"👉 SUCCESS: An occultation is PREDICTED at this site! Observer inside the shadow path.")
            print(f"*** Asterioid ", asteroid_id, " (", get_asteroid_name(asteroid_id), "), with star RA=",star_ra, " DE=", star_dec, " @ET=", best_et, ", UTC=", best_utc, " min dist=", min_distance, " km ", "***")
            if not observable(best_et, star_direction, obs_geo):
                print(f" ** BUT NOT OBSERVABLE, BELOW HORIZON OR LIMITS **")
                return { "best_utc": best_utc, "best_et": best_et, "min_distance": min_distance, "observable": "no" }
            return { "best_utc": best_utc, "best_et": best_et, "min_distance": min_distance,  "observable": "yes" }
            
        else:
            if min_distance < r_asteroid_km+r_search_km:
                if not observable(best_et, star_direction, obs_geo):
                    print(f" ** BUT NOT OBSERVABLE, BELOW HORIZON OR LIMITS **")
                    return { "best_utc": best_utc, "best_et": best_et, "min_distance": min_distance, "observable": "no, in search range" }
                return { "best_utc": best_utc, "best_et": best_et, "min_distance": min_distance,  "observable": "yes, in search range" }
            else:
                print(f"❌ MISS: Shadow path misses observer by {min_distance - r_asteroid_km:.3f} km.")
    else:
        print("Solver failed to converge on an event window.")

    return None



def screen_stars(ra_deg, dec_deg, target, et0, span, margin_km, step=60.0):
    ets = np.arange(et0 - span/2, et0 + span/2 + step, step)
    ast, _ = spice.spkpos(target, ets, 'J2000', 'CN', '399')      # astrometric, matches Gaia
    dist = np.linalg.norm(ast, axis=1)
    u_ast = ast / dist[:, None]
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    s = np.column_stack((np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)))
    chord = np.linalg.norm(s[:, None, :] - u_ast[None, :, :], axis=2)   # (stars, times)
    return np.where((chord * dist).min(axis=1) < margin_km)[0]          # ~plane distance, km




_seen = {}

def is_new_hit(target_id, star_id, et, tol=300.0):
    ets = _seen.setdefault((target_id, star_id), [])
    if any(abs(et - e) < tol for e in ets):
        return False
    ets.append(et)
    return True

def target_test(loc, event_time_utc, time_span, target_id, size, mag_lim=20.0, max_shadow_distance=0.0):
    obs_geo = {'lon': loc.lon.to(u.rad).value, 'lat': loc.lat.to(u.rad).value,
               'alt': loc.height.to(u.km).value}
    r_search = size['r_max_km']
    et0 = spice.str2et(event_time_utc)

    assert target_id in _loaded, f"fetch_target_orbit({target_id}) must run first"
    
    if not window_is_observable(et0, time_span, obs_geo, target_id):
        return          # skips Horizons position, Gaia query, screening, solver
    
    target = get_asteroid_ra_dec(target_id, utc_time=event_time_utc)     # cone centre only

    event_df = fetch_and_propagate_stars(target['ra'], target['dec'], event_time_utc, 10.0, mag_lim)
    if event_df is None or event_df.empty:
        return
    ra_col  = event_df.filter(regex=r'^ra_\d{8}$').columns[0]
    dec_col = event_df.filter(regex=r'^dec_\d{8}$').columns[0]

    idx = screen_stars(event_df[ra_col].to_numpy(), event_df[dec_col].to_numpy(),
                       target_id, et0, time_span, margin_km=6378 + r_search + config.max_shadow_dist) 
    print (f"Pre-Screening: {idx}")
    for row in event_df.iloc[idx].itertuples(index=False):
        handle_star(loc, obs_geo, target_id, size, row, ra_col, dec_col, et0, time_span, r_search, -np.inf, np.inf)


RUN = dict(candidates=0, gated=0, solves=0, hits=0, maps_s=0.0, calc_s=0.0)      # run statistics (see run_summary)
LOCAL = None             # the local Gaia catalog (set by the driver), for the event previews


def write_preview(record, target_id, stem):
    """Event preview SVG (pyoccult_preview.py): stars of the local catalog around the target star at the event date,
    camera frame, asteroid track +/- 1 h. Written to <map_dir>/<stem>.svg next to the KML."""
    import pyoccult_preview as preview
    fov = preview.camera_fov_arcmin(config.camera_focal_mm, config.camera_sensor_mm)
    field = max(config.preview_field_factor * max(fov), 10.0)
    et = record["best_et"]
    stars = LOCAL.cone(record["star_ra"], record["star_dec"], field / 60 * 0.75, config.preview_mag_limit)
    ra, de = corridor.propagate_linear(stars, 2000.0 + et / (365.25 * 86400) - corridor.GAIA_EPOCH_YEAR)
    def radec(t):
        _, a, d = spice.recrad(spice.spkpos(target_id, t, 'J2000', 'CN', '399')[0])
        return np.degrees(a), np.degrees(d)
    # track span: about a quarter of the field, between 30 min and 12 h each side
    (a0, d0), (a1, d1) = radec(et - 600.0), radec(et + 600.0)
    rate = np.hypot((a1 - a0) * np.cos(np.radians(d0)), d1 - d0) * 60 / 20.0            # arcmin per minute
    span = int(np.clip(field / 4 / max(rate, 1e-9), 30, 720))
    track = [(m, *radec(et + 60.0 * m)) for m in np.linspace(-span, span, 13)]
    svg = preview.render_svg(dict(ra=ra, dec=de, g=stars.phot_g_mean_mag.to_numpy()),
                             dict(ra=record["star_ra"], dec=record["star_dec"], g=record["mag"]), track, fov,
                             config.preview_field_factor,
                             title=f"{record['target_name']}  {record['best_utc'][:19].replace('T', ' ')} UT",
                             subtitle=f"Gaia DR3 {record['star']} \u00b7 G {record['mag']:.2f} \u00b7 drop "
                                      f"{record['mag_drop']:.2f} mag \u00b7 max {record['max_duration_s']:.2f} s \u00b7 "
                                      f"miss {record['min_distance']:.1f} km")
    os.makedirs(config.map_dir, exist_ok=True)
    with open(f"{config.map_dir}/{stem}.svg", "w", encoding="utf-8") as f:
        f.write(svg)


def owc_opt():
    """The chosen site's equipment for screen.owc_limit / extinction_loss (from pyoccult_config, i.e. sites.py)."""
    return dict(aperture=config.pick_aperture_cm, frames=config.pick_frames, mag_adjust=config.pick_mag_adjust,
                extinction=config.pick_extinction)


def handle_star(loc, obs_geo, target_id, size, row, ra_col, dec_col, et_guess, bracket_s, r_search, win_lo, win_hi,
                t_start=None):
    """Refine one candidate star with the exact solver, log it (CSV, KML map) if it is a real, observable hit.
    The solver searches et_guess +/- bracket_s/2. win_lo / win_hi: ET limits of the run (an event outside them
    belongs to a neighbouring run). t_start: when work on this candidate began (for calc_s). Returns True if logged."""
    t_start = t_start or time.time()
    RUN["solves"] += 1
    ra, dec = np.radians(getattr(row, ra_col)), np.radians(getattr(row, dec_col))
    res = star_test(loc, spice.et2utc(et_guess, "ISOC", 3), bracket_s, ra, dec, target_id, r_search, config.max_shadow_dist)
    if res is None:
        print (f" --- miss --- ")
        return False
    # minimum on the bracket edge is not a real minimum; a neighbouring window/candidate finds it
    if min(res['best_et'] - (et_guess - bracket_s/2), (et_guess + bracket_s/2) - res['best_et']) < 1.0:
        print (f" --- not real --- ")
        return False
    if not (win_lo <= res['best_et'] <= win_hi):
        print (f" --- outside run window --- ")
        return False
    if not is_new_hit(target_id, row.source_id, res['best_et']):
        print (f" --- not a hit --- ")
        return False
    star_dir = np.array([np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)])
    ok, star_alt, sun_alt = observable(res['best_et'], star_dir, obs_geo)
    if not ok:
        print (f" --- not visible --- ")
        return False                                   # drop this line to log invisible events too
    m_ast = (apparent_mag_HG(res['best_et'], target_id, size['H'], size.get('G') or 0.15)
             if size.get('H') is not None else np.nan)
    met = event_metrics(res['best_et'], star_dir, obs_geo, target_id, size['r_km'], row.phot_g_mean_mag, m_ast)
    if np.isfinite(met['mag_drop']) and met['mag_drop'] < getattr(config, "min_mag_drop", 0.1):
        print (f" --- too low mag drop dM = {met['mag_drop']} --- ")
        return False
    moon = moon_info(res['best_et'], star_dir, obs_geo)

    record = dict(target_id=target_id, target_name=get_asteroid_name(target_id),
                  best_utc=res['best_utc'], best_et=res['best_et'],
                  min_distance=res['min_distance'], margin_km=res['min_distance'] - size['r_km'],
                  r_km=size['r_km'], r_min_km=size['r_min_km'], r_max_km=size['r_max_km'],
                  r_search_km=r_search, size_source=size['source'],
                  star=row.source_id, mag=row.phot_g_mean_mag,
                  star_ra=np.degrees(ra), star_dec=np.degrees(dec),
                  star_alt=star_alt, sun_alt=sun_alt, m_ast=m_ast, **met, **moon,
                  observable=res['observable'])
    dx, dy = besselian_offsets(res['best_et'], star_dir, obs_geo, target_id)
    record.update(offset_east_km=dx, offset_north_km=dy,
                  max_duration_s=2*size['r_km']/met['speed_kms'])
    # OWC observability with atmospheric extinction at the star's altitude (upper size bound, as the pick tool)
    opt = owc_opt()
    ext = float(screen.extinction_loss(star_alt, opt))
    record.update(airmass=float(screen.airmass(star_alt)), extinction_mag=ext,
                  mag_margin=float(screen.owc_limit(2*size['r_max_km']/met['speed_kms'], opt)) - row.phot_g_mean_mag - ext,
                  calc_s=time.time() - t_start)
    print(record)
    pd.DataFrame([record]).to_csv(config.hits_output_cvs_file, mode='a', index=False,
                                  header=not os.path.isfile(config.hits_output_cvs_file))
    RUN["hits"] += 1
    RUN["calc_s"] += record["calc_s"]

    t_map = time.time()
    stem = f"{target_id}_{res['best_utc'][:16].replace(':','').replace('-','')}"     # file name of KML and preview
    sigma3 = path_sigma3_km(target_id, res['best_utc']) or config.default_sigma3_km
    if config.write_maps and res['min_distance'] < r_search + config.max_shadow_dist:   # shadow + reach, as logged
        os.makedirs(config.map_dir, exist_ok=True)
        paths = shadow_path(target_id, star_dir, res['best_et'], size['r_km'], sigma3)
        write_shadow_kml(paths, f"{config.map_dir}/{stem}.kml",
                         f"{record['target_name']} / Gaia {row.source_id}", observer=(config.LON, config.LAT))
    if getattr(config, "write_previews", False) and LOCAL is not None:
        try:
            write_preview(record, target_id, stem)
        except Exception as ex:                                       # a preview must never stop the search
            print(f" --- no preview: {ex}")
    RUN["maps_s"] += time.time() - t_map
    return True


def run_summary(mode, t_main, t_pass1, t_pass2, n_targets):
    """Print the run statistics and the site/limits, and append them as one JSON line to <hits log>.runs.jsonl
    (read by pyoccult_report.py for the page header)."""
    t_end = time.time()
    n_ok = max(n_targets, 1)
    s = dict(run_utc=datetime.fromtimestamp(T_START, tz=__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), mode=mode,
             window_start=str(config.ct), window_days=config.days, targets=n_targets,
             candidates=RUN["candidates"], gated=RUN["gated"], solves=RUN["solves"], hits=RUN["hits"],
             total_s=t_end - T_START, startup_s=t_main - T_START, init_s=t_pass1, search_s=t_pass2,
             maps_s=RUN["maps_s"], per_asteroid_s=(t_pass1 + t_pass2) / n_ok, search_per_asteroid_s=t_pass2 / n_ok,
             per_solve_s=(t_pass2 - RUN["maps_s"]) / max(RUN["solves"], 1),
             calc_per_hit_s=RUN["calc_s"] / max(RUN["hits"], 1),
             site=dict(name=config.site_name, desc=config.site.get("name", ""), lat=config.LAT, lon=config.LON,
                       ele=config.ELE, aperture_cm=config.pick_aperture_cm, frames=config.pick_frames,
                       mag_adjust=config.pick_mag_adjust, extinction=config.pick_extinction),
             limits=dict(mag_limit=config.MAG_MIN, min_star_alt=config.MIN_STAR_ALT, max_sun_alt=config.MAX_SUN_ALT,
                         reach_km=config.max_shadow_dist, min_mag_drop=getattr(config, "min_mag_drop", 0.1),
                         min_dur_s=config.pick_min_dur_s),
             earth_pck=EARTH_PCK, targets_from=globals().get("TARGETS_FROM", ""))
    print(f"\nRun summary ({mode}): {n_targets} asteroids, {s['candidates']} candidates, {s['solves']} exact solves, "
          f"{s['hits']} hits")
    print(f"  total {s['total_s']:.1f} s = start-up {s['startup_s']:.1f} s + asteroid data {t_pass1:.1f} s + search "
          f"{t_pass2:.1f} s (of it maps {s['maps_s']:.1f} s)")
    print(f"  per asteroid {s['per_asteroid_s']:.2f} s (search {s['search_per_asteroid_s']:.2f} s); search time per "
          f"exact solve {s['per_solve_s'] * 1000:.0f} ms (with star lookup and scan); calculation per hit "
          f"{s['calc_per_hit_s'] * 1000:.0f} ms")
    stem = os.path.splitext(config.hits_output_cvs_file)[0]
    with open(stem + ".runs.jsonl", "a") as f:
        f.write(json.dumps(s) + "\n")
    return s


def target_test_corridor(loc, plan, target_id, size, local=None, stars_cands=None):
    """Replacement for the per-window target_test(): one call per asteroid for the whole run.
    plan = corridor.plan_corridor(...) (needs SPICE, build serially). local = pyoccult_gaia_local.LocalGaia.
    stars_cands = (stars, candidates) if already computed. Returns the number of logged hits."""
    obs_geo = {'lon': loc.lon.to(u.rad).value, 'lat': loc.lat.to(u.rad).value, 'alt': loc.height.to(u.km).value}
    r_search = size['r_max_km']
    stars, cands = stars_cands or corridor.corridor_candidates(plan, local)
    if cands.empty:
        return 0
    ets = plan['path']['ets']
    win_lo, win_hi = float(ets[0]), float(ets[-1])
    n_log = 0
    RUN["candidates"] += len(cands)
    for cand in cands.sort_values('et_guess').itertuples(index=False):
        t_start = time.time()
        # the observer's closest approach can be up to margin/speed away from the Earth-centre estimate
        bracket = corridor.solver_bracket_s(plan, cand.j)
        # cheap early gate (Sun and asteroid altitude) before any solver work
        if not window_is_observable(cand.et_guess, bracket, obs_geo, target_id):
            RUN["gated"] += 1
            continue
        # only the candidates need exact space motion: propagate each to its own event time
        prop = corridor.propagate_exact(stars.iloc[[cand.star]], spice.et2utc(cand.et_guess, "ISOC", 0))
        ra_col = prop.filter(regex=r'^ra_\d{8}$').columns[0]
        dec_col = prop.filter(regex=r'^dec_\d{8}$').columns[0]
        row = next(prop.itertuples(index=False))
        n_log += handle_star(loc, obs_geo, target_id, size, row, ra_col, dec_col, cand.et_guess, bracket,
                             r_search, win_lo, win_hi, t_start)
    return n_log


def resolve_targets():
    """targets_source "auto": the saved pick of this site covering the search window (pyoccult_picks), else the
    config list (targets.py or the manual one). Sets config.targets; returns a description for the run summary."""
    if getattr(config, "targets_source", "auto") != "auto":
        return f"list ({len(config.targets)} targets)"
    import pyoccult_picks
    p = pyoccult_picks.best_for(config.site_name, str(config.ct)[:10], config.days, getattr(config, "picks_dir", "picks"),
                                config.LAT, config.LON)
    if p is None:
        print(f"* No saved pick for site {config.site_name} covers {str(config.ct)[:10]} + {config.days:g} d: "
              f"using the config list / targets.py ({len(config.targets)} targets)")
        return f"targets.py / config list ({len(config.targets)} targets)"
    config.targets = p["targets"]
    config.target_names = p["names"]
    print(f"* Targets: {pyoccult_picks.describe(p)}")
    return pyoccult_picks.describe(p)


if __name__ == "__main__":
    t_main = time.time()
    mag_min = config.MAG_MIN
    TARGETS_FROM = resolve_targets()
    obs_loc = EarthLocation(lat=config.LAT*u.deg, lon=config.LON*u.deg, height=config.ELE*u.m)


    t0 = pd.Timestamp(config.ct)
    epochs = {'start': (t0 - pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
              'stop':  (t0 + pd.Timedelta(days=config.days + 1)).strftime('%Y-%m-%d')}
    periods = (pd.date_range(start=config.ct, periods=int(config.days*86400/config.spn), freq=f"{config.spn}s")
                 .strftime("%Y-%m-%d %H:%M:%S").tolist())

    if getattr(config, "search_mode", "corridor") == "windows":    # old path: ~200 Gaia cones per asteroid
        t_w = time.time()
        for t in config.targets:
            size = get_asteroid_size(t)
            if size is None:
                print(f"No size data for {t}, skipping")
                continue
            print(f"Estimated/known target {t} size data: {size}")
            fetch_target_orbit(t, epochs)                          # once per target
            for ctp in periods:
                target_test(obs_loc, ctp, config.spn + 600, t, size, mag_min)   # +10 min so windows overlap
        run_summary("windows", t_main, 0.0, time.time() - t_w, len(config.targets))
        spice.kclear()
        sys.exit(0)

    # stars come from the local Gaia copy (python pyoccult_gaia_local.py build); checked first, before any SPK work
    if not getattr(config, "gaia_local_dir", None):
        sys.exit("corridor mode needs the local Gaia catalog: set gaia_local_dir and run  python pyoccult_setup.py")
    import pyoccult_gaia_local
    local = pyoccult_gaia_local.LocalGaia(config.gaia_local_dir)         # raises if the catalog is incomplete
    LOCAL = local
    print(f"Using local Gaia catalog {config.gaia_local_dir} (G <= {local.gmax})")

    et0 = spice.str2et(t0.strftime("%Y-%m-%dT%H:%M:%S"))
    et1 = et0 + config.days * 86400.0

    # pass 1 (serial, SPICE): sizes, SPKs and one corridor plan per target

    print(
        f"Pass 1 (serial, SPICE): sizes, SPKs and one corridor plan per target"
    )

    t_p1 = time.time()
    plans = {}
    for t in config.targets:
        size = get_asteroid_size(t)
        if size is None:
            print(f"No size data for {t}, skipping")
            continue
        print(f"Estimated/known target {t} size data: {size}")
        fetch_target_orbit(t, epochs)                              # once per target
        plans[t] = (size, corridor.plan_corridor(t, et0, et1, size, mag_min, config.max_shadow_dist,
                                                 min_drop=getattr(config, "min_mag_drop", 0.1),
                                                 step_s=getattr(config, "corridor_step_s", 600.0)))

    t_p1 = time.time() - t_p1

    # pass 2 (serial, SPICE): stars from the local catalog, scan and solve
    t_p2 = time.time()
    print(
        f"Pass 2 (serial, SPICE): stars from the local catalog, scan and solve"
    )
    for t, (size, plan) in plans.items():
        n = target_test_corridor(obs_loc, plan, t, size, local=local)
        print(f"{t}: {n} hit(s) logged")
    run_summary("corridor", t_main, t_p1, time.time() - t_p2, len(plans))
    spice.kclear()
