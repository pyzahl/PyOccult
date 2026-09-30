#!.venv/bin/python3
import sys, base64, functools, os, re
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

### SEARCH FOR

ct, days, spn = "2026-10-01T00:00:00", 10, 3600
targets = ["218001", "305580", "111287", "115181", "229912", "111286", "54653", "70141", "4272"]
max_shadow_dist = 200  ## km

### CONFIG

LAT = 40.9541175
LON = -72.92614552
ELE = 40

MAG_MIN = 20
MIN_STAR_ALT = 10.0     # deg, use the same constants in both gates
MAX_SUN_ALT  = -6.0     # deg, try -12 for faint stars
ALT_MARGIN   = 3.0      # early gate is looser than the final one, so it never rejects a real event


########################## PROLOGUE KERNEL INIT SECTION

# Init, Cleanups, ToDO clean SHM cache?

force_cleanup = False

if force_cleanup:
    print ('Cleanup old files:')
    for filename in ["naif0012.tls", "de440.bsp", "pck00010.tpc"]:
        if os.path.exists(filename):
            print ('removing: ', filename)
            os.remove(filename)

# Wipe out old file/memory states completely
spice.clpool()



# Basic Kerenls and Data
def download_kernels():
    urls = {
        "naif0012.tls": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls",
        "de440.bsp": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp",
        "pck00010.tpc": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00010.tpc",
        "earth_latest_high_prec.bpc": "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_latest_high_prec.bpc",
    }
    
    # Complete browser headers to clear security checks
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    for name, url in urls.items():
        # Clean check: Delete the file if it somehow contains HTML text
        if os.path.exists(name):
            with open(name, 'r', errors='ignore') as f:
                first_line = f.readline()
                if "<!doctype" in first_line.lower() or "<html" in first_line.lower():
                    print(f"Purging old HTML file from cache: {name}")
                    os.remove(name)

        # Download using the system curl pipeline if it doesn't exist
        if not os.path.exists(name):
            print(f"Downloading {name} via system curl...")
            try:
                # -L follows redirects, -s hides progress bar, -f fails silently on server errors
                subprocess.run(
                    ["curl", "-L", "-A", "Mozilla/5.0", url, "-o", name],
                    check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"🚨 Curl download failed for {name}: {e}")
                return False
                
    print("✅ All kernels verified and downloaded cleanly via curl.")
    return True


# ==========================================
# KERNEL DOWNLOADING UTILITY
# ==========================================

# *** The Earth PCK is never refreshed. Once downloaded, earth_latest_high_prec.bpc is reused forever. Its predicted coverage is finite and the predictions degrade, so either pxform fails or you use stale Earth orientation. Re-download if the file is older than a week, and print the coverage after loading:

#cover = spice.stypes.SPICEDOUBLE_CELL(1000)
#spice.pckcov("earth_latest_high_prec.bpc", 3000, cover)      # 3000 = ITRF93 segments, verify
#print("Earth PCK covers to", spice.et2utc(spice.wnfetd(cover, spice.wncard(cover) - 1)[1], 'ISOC', 0))

if download_kernels():
    try:
        print ('* Loading Compute Kernels *')
        # Load all required kernels
        spice.furnsh("naif0012.tls")       # Leapseconds
        spice.furnsh("pck00010.tpc")       # Planetary constants
        spice.furnsh("de440.bsp")          # Major planets base
        spice.furnsh("earth_latest_high_prec.bpc")
        
        print ('* Testing Compute Kernels *')
        
        et = spice.str2et("2026-09-28 UTC")
        print(f"🚀 Success! CSPICE Active. Target ET: {et}")
            
    except Exception as e:
        print(f"CSPICE Error: {e}")
        sys.exit('Exiting as of error.')

########################## PROLOGUE KERNEL INIT SECTION END


## GET DATA FOR INFO AND NAME LOOKUPS, download once!

# The endpoint for querying the bulk database
URL_JPL_SBDBQ = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"

def get_all_jpl_asteroids_with_spice():
    print("Querying JPL Database for entries and SPICE IDs... (This may take a moment)")
    output_file = "jpl_asteroids_spice.csv"
    fp = Path(output_file)
    if fp.is_file():
        print("JPL db already fetched!")
        print(f"Found and reading cached asteroid list: '{output_file}'.")
        df = pd.read_csv(output_file)
        return df
    
    
    # Added 'spkid' to the requested fields parameter
    params = {
        "sb-kind": "a",  # Limit search results to asteroids-only
        "fields": "spkid,full_name,pdes",  # Fetch SPICE/SPK ID, full name, and primary designation
    }

    try:
        response = requests.get(URL_JPL_SBDBQ, params=params)
        response.raise_for_status()
        data = response.json()

        # Check if data was returned
        if "data" not in data:
            print("No data returned from the API.")
            return

        # Extract fields and data rows
        columns = data["fields"]
        rows = data["data"]

        # Build the DataFrame
        df = pd.DataFrame(rows, columns=columns)

        # Rename columns to clear human-readable names
        df.columns = ["SPICE ID", "Full Name", "Primary Designation"]

        # Ensure the SPICE IDs are stored clearly (they arrive as string representations of the integer codes)
        df["SPICE ID"] = pd.to_numeric(df["SPICE ID"], errors="coerce")

        # Save to CSV
        df.to_csv(output_file, index=False)

        print(f"Success! Fetched {len(df):,} minor planets and asteroids.")
        print(f"Data saved cleanly to '{output_file}'.")
        return df
        
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while connecting to JPL: {e}")
    except json.JSONDecodeError:
        print("Failed to parse the response from JPL.")

# Fetch to numpy
asteroids_df = get_all_jpl_asteroids_with_spice()
spice_ids = asteroids_df["SPICE ID"].to_numpy()
names = asteroids_df["Full Name"].to_numpy()


### NOW OCCULT CALC AND STAR+ASTEROID EPH MANAGEMENT


#3. Possible silent row truncation. As far as I know, Gaia.launch_job (synchronous) is capped at about 2,000 rows, but check the current astroquery docs. At G≤20 a 10′ cone in a dense field can exceed that, and you'd lose stars with no error. Use launch_job_async, and warn if len(df) hits a suspicious round number.

#4. Parallax handling. Clipping to 0 means infinite distance. Depending on your astropy version that gives NaN or an odd code path. Use a floor instead, such as np.clip(parallax, 0.01, None) (100 kpc), build the distance with Distance(parallax=... * u.mas) (I assume CoordinateDistance is that alias), and assert the output is finite.

#5. Barycentric vs geocentric direction. apply_space_motion returns the barycentric position, but the shadow axis is parallel to the star direction as seen from Earth. At an asteroid distance of about 1.4 AU, 1 mas of parallax shifts the shadow by about 1 km. That is small for a 100 km body but matters for a 5 km one. Fix it once per window:

PC_KM = 3.0856775814913673e13
def geocentric_star_dir(ra_deg, dec_deg, plx_mas, et):
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    u_bary = np.array([np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)])
    earth, _ = spice.spkpos('399', et, 'J2000', 'NONE', 'SSB')
    v = u_bary * (1000.0 / max(plx_mas, 0.01)) * PC_KM - earth
    return v / np.linalg.norm(v)


#6. Failure handling. On any error you print and return None, so the caller's event_df.columns raises AttributeError and kills the whole 7-day batch. The blanket except Exception would also hide code bugs, such as the Distance issue above, as "an error occurred". Catch only network and TAP errors, retry with backoff, and return an empty DataFrame (with the expected columns) if there are no stars. In a run of over a thousand queries, one hiccup will happen.

#7. Columns to add to the SELECT.

#ra_error, dec_error, pmra_error, pmdec_error for the position uncertainty at the event epoch (propagated as sqrt(σ² + (Δt·σ_pm)²)).
#bp_rp, which you need for the G→V or G→R conversion in the magnitude-drop estimate.
#ruwe is already there. Consider flagging RUWE > 1.4 instead of excluding it, since those are often unresolved doubles, which are interesting occultation targets, though their positions are less certain.

#Once you add ra_error, dec_error and similar, my earlier startswith('ra_') warning becomes a real bug, so use the exact regexes ^ra_\d{8}$ and ^dec_\d{8}$ in the driver.

#Minor.

#The inline -- Required for propagation comment sits in the middle of a multi-line ADQL string. If a server collapses newlines, it will comment out AND ruwe < 1.4, so remove it.
#Colons and spaces in filenames are legal on Linux but awkward. Build keys from rounded numbers, not raw time strings.



def tile_center(ra_deg, dec_deg, tile_arcmin=5.0):
    t = tile_arcmin / 60.0
    dec_c = round(dec_deg / t) * t
    step = t / max(np.cos(np.radians(dec_c)), 0.05)
    return (round(ra_deg / step) * step) % 360.0, dec_c

def gaia_cone(ra_deg, dec_deg, radius_arcmin, mag_limit):
    ra_c, dec_c = tile_center(ra_deg, dec_deg)
    fp = Path(f"/dev/shm/PyOccult_gaia_{ra_c:.4f}_{dec_c:.4f}_{radius_arcmin:g}_{mag_limit:g}.csv")
    if fp.is_file():
        return pd.read_csv(fp)
    # ADQL query centered on (ra_c, dec_c), radius = radius_arcmin + 5 (tile size), via Gaia.launch_job_async

    radius_deg = radius_arcmin / 60.0
    query = f"""
    SELECT 
        source_id, ra, dec, parallax, pmra, pmdec, phot_g_mean_mag, ruwe
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra_c}, {dec_c}, {radius_deg}))
    AND phot_g_mean_mag <= {mag_limit}
    AND pmra IS NOT NULL AND pmdec IS NOT NULL -- Required for propagation
    AND ruwe < 1.4
    """

    try:
        job = Gaia.launch_job(query)
        df = job.get_results().to_pandas()

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    df.to_csv(fp, index=False)
    return df

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
    # gaia_cone(...)      -> cached raw Gaia table (epoch 2016.0)
    # propagate(df, time) -> adds ra_YYYYMMDD / dec_YYYYMMDD, never cached
    
    print(
        f"Querying Gaia DR3 & propagating positions to: {target_time.iso} UTC..."
    )

    df = gaia_cone(ra_deg, dec_deg, radius_arcmin, mag_limit).copy(); 
        
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
    
    spk_id = int(spk_id)
    if spk_id < 20000000:
        spk_id = spk_id + 20000000

    idx = np.where(spice_ids == spk_id)[0]
    if idx.size > 0:
        return names[idx[0]]

    try:
        # Attempt native SPICE resolution
        name = spice.bodc2n(spk_id)
        return name
    except spice.utils.support_types.SpiceyError as e:
        print(f"\nSPICE Processing Error: {e}")
        # If not in the loaded SPICE pool, fall back to calculating the IAU number
        if 20000000 <= spk_id < 30000000:
            iau_number = spk_id - 20000000
            return f"Numbered Asteroid IAU: ({iau_number})"
        else:
            return f"Unnumbered / Provisional Asteroid SPK Target ID: {spk_id}"



_loaded = {}    # asteroid number -> NAIF id

def fetch_target_orbit(target_id, epochs, cache_dir="/dev/shm"):
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

SIZE_OVERRIDES = {}   # curate best values here: {"19": (r_km, r_sigma_km, "source note")}



#Things to check:

#SBDB field names. I'm going from memory of the phys_par layout (name, value, sigma, ref). Print resp.json() for one target to confirm, and adjust num() if needed. extent should be the full dimensions in km.
#Source labels. The ref string tells you which survey the diameter came from. Where you have better values (occultation chords, DAMIT shape models), put them in SIZE_OVERRIDES and they take priority.
#What the bounds mean. r_km is the nominal radius. r_min_km and r_max_km are approximately ±3σ, or the albedo range for H-only objects, and are wider if the triaxial extents are bigger. The bounds reflect size uncertainty only, not ephemeris uncertainty.

@functools.lru_cache(maxsize=None)
def get_asteroid_size(target_id, timeout=30):
    """Return dict(r_km, r_min_km, r_max_km, source), or None if nothing usable."""
    n = str(target_id).strip()
    if n in SIZE_OVERRIDES:
        r, s, src = SIZE_OVERRIDES[n]
        return dict(r_km=r, r_min_km=r - 3*s, r_max_km=r + 3*s, source=src)

    try:
        resp = requests.get("https://ssd-api.jpl.nasa.gov/sbdb.api",
                            params={"sstr": n, "phys-par": 1}, timeout=timeout)
        resp.raise_for_status()
        pp = {p["name"]: p for p in resp.json().get("phys_par", [])}
    except (requests.RequestException, ValueError) as e:
        print(f"SBDB lookup failed for {n}: {e}")
        return None

    def num(name, key="value"):
        try:
            return float(pp[name][key])
        except (KeyError, TypeError, ValueError):
            return None

    D = num("diameter")
    if D:
        s = num("diameter", "sigma") or num("diameter_sigma") or 0.15 * D   # assume 15% if absent
        out = dict(r_km=D/2, r_min_km=(D - 3*s)/2, r_max_km=(D + 3*s)/2,
                   source=f"SBDB diameter (ref {pp['diameter'].get('ref', '?')})")
        ext = [float(x) for x in re.findall(r"[\d.]+", str(pp.get("extent", {}).get("value", "")))]
        if len(ext) >= 2:                      # tri-axial full dimensions -> semi-axes
            out["r_min_km"] = min(out["r_min_km"], min(ext)/2)
            out["r_max_km"] = max(out["r_max_km"], max(ext)/2)
        return out

    H = num("H")
    if H is None:
        return None
    Dp = lambda p: 1329.0 / np.sqrt(p) * 10**(-H/5)
    p = num("albedo")
    if p:
        return dict(r_km=Dp(p)/2, r_min_km=Dp(min(p*1.5, 1))/2, r_max_km=Dp(p/1.5)/2, source="H + SBDB albedo")
    return dict(r_km=Dp(0.14)/2, r_min_km=Dp(0.30)/2, r_max_km=Dp(0.05)/2, source="H only, albedo assumed")



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


def observable(et, star_dir, obs_geo, min_star_alt=MIN_STAR_ALT, max_sun_alt=MAX_SUN_ALT):
    star_alt = alt_deg(et, star_dir, obs_geo)
    sun_alt = sun_alt_deg(et, obs_geo)
    return bool(star_alt > min_star_alt and sun_alt < max_sun_alt), star_alt, sun_alt

def window_is_observable(et0, span, obs_geo, target_id, min_star_alt=MIN_STAR_ALT, max_sun_alt=MAX_SUN_ALT, alt_margin=ALT_MARGIN):
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

    # Objective function to minimize for root-finding
    def objective_func(et):
        return get_besselian_miss_distance(et, star_direction, obs_geo, asteroid_id)

    # Use a bounded scalar minimizer (+/- 10 minutes or 600 seconds from guess)
    #time_span2 = (24*3600) / 2 # in sec
    time_span2 = time_span/2
    print("Computing exact time of closest approach...")
    result = minimize_scalar(
        objective_func, 
        bounds=(et_center - time_span2, et_center + time_span2), 
        method='bounded',
        options={'xatol': 1e-5} # sub-millisecond convergence tolerance
    )

    if result.success:
        best_et = result.x
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
                    return { "best_utc": best_utc, "best_et": best_et, "min_distance": min_distance, "observable": "no, in serach range" }
                return { "best_utc": best_utc, "best_et": best_et, "min_distance": min_distance,  "observable": "yes, in serach range" }
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





#Written but not wired in

#observable, event_metrics and apparent_mag_HG are never called. apparent_mag_HG needs H and G, so make get_asteroid_size return them: compute H, G = num("H"), num("G") after num is defined, and add H=H, G=G to every returned dict (None in the override branch). For m_star, Gaia G is fine as a proxy. Add bp_rp to the SELECT if you want a proper V or R conversion. observable's default max_sun_alt=-6 is civil twilight, so use -12 or lower for faint stars.

#Still open from earlier notes
#targets is still a set with a duplicate.
#epochs is hardcoded, and fetch_target_orbit still runs per window.
#There's no retry or backoff on the network calls.
#sys.exit inside get_asteroid_ra_dec kills the whole batch, so raise or return None instead.
#spice.utils.support_types.SpiceyError is only evaluated when an exception fires, so if that attribute doesn't exist in your spiceypy you'd get an AttributeError hiding the real SPICE error. Check it in a REPL, or use from spiceypy.utils.exceptions import SpiceyError.
#The inline -- comment in the ADQL is still there.

#Housekeeping. get_besselian_miss_distance is defined three times (the last wins). Delete Xget_besselian_miss_distance and Xfetch_target_orbit, the unused Horizons import and headers dict, and add -f to the curl call so a 404 doesn't save an HTML page.



HITS_CSV = "hits_log_v2.csv"
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
                       target_id, et0, time_span, margin_km=6378 + r_search) 
    print (f"Pre-Screening: {idx}")
    for row in event_df.iloc[idx].itertuples(index=False):
        print (row)
        ra, dec = np.radians(getattr(row, ra_col)), np.radians(getattr(row, dec_col))
        res = star_test(loc, event_time_utc, time_span, ra, dec, target_id, r_search, max_shadow_dist)
        if res is None:
            print (f" --- miss --- ")
            continue
        # minimum on the window edge is not a real minimum; the overlapping neighbour finds it
        if min(res['best_et'] - (et0 - time_span/2), (et0 + time_span/2) - res['best_et']) < 1.0:
            print (f" --- not real --- ")
            continue
        if not is_new_hit(target_id, row.source_id, res['best_et']):
            print (f" --- not a hit --- ")
            continue
        star_dir = np.array([np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)])
        ok, star_alt, sun_alt = observable(res['best_et'], star_dir, obs_geo)
        if not ok:
            print (f" --- not visible --- ")
            continue                                   # drop this line to log invisible events too
        m_ast = (apparent_mag_HG(res['best_et'], target_id, size['H'], size.get('G') or 0.15)
                 if size.get('H') is not None else np.nan)
        met = event_metrics(res['best_et'], star_dir, obs_geo, target_id, size['r_km'],
                            row.phot_g_mean_mag, m_ast)

        if np.isfinite(met['mag_drop']) and met['mag_drop'] < 0.1:
            print (f" --- too low mag drop dM = {met['mag_drop']} --- ")
            continue
        
        record = dict(target_id=target_id, target_name=get_asteroid_name(target_id),
                      best_utc=res['best_utc'], best_et=res['best_et'],
                      min_distance=res['min_distance'], margin_km=res['min_distance'] - size['r_km'],
                      r_km=size['r_km'], r_search_km=r_search, size_source=size['source'],
                      star=row.source_id, mag=row.phot_g_mean_mag,
                      star_ra=np.degrees(ra), star_dec=np.degrees(dec),
                      star_alt=star_alt, sun_alt=sun_alt, m_ast=m_ast, **met, observable=res['observable'])
        print(record)
        pd.DataFrame([record]).to_csv(HITS_CSV, mode='a', index=False,
                                      header=not os.path.isfile(HITS_CSV))


if __name__ == "__main__":
    mag_min = MAG_MIN
    obs_loc = EarthLocation(lat=LAT*u.deg, lon=LON*u.deg, height=ELE*u.m)


    t0 = pd.Timestamp(ct)
    epochs = {'start': (t0 - pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
              'stop':  (t0 + pd.Timedelta(days=days + 1)).strftime('%Y-%m-%d')}
    periods = (pd.date_range(start=ct, periods=int(days*86400/spn), freq=f"{spn}s")
                 .strftime("%Y-%m-%d %H:%M:%S").tolist())

    for t in targets:
        size = get_asteroid_size(t)
        if size is None:
            print(f"No size data for {t}, skipping")
            continue

        #If you'd rather use a fallback radius than skip targets with no size, build a complete dict (r_km, r_max_km, source, H=None, G=None) so the downstream code doesn't break.
        ## Estimated/known target 200019 size: {'r_km': 1.9965, 'r_min_km': -0.052500000000000435, 'r_max_km': 4.0455000000000005, 'source': 'SBDB diameter (ref urn:nasa:pds:neowise_diameters_albedos::2.0[mainbelt] (http://adsabs.harvard.edu/abs/2011ApJ...741...68M))'}

        print(f"Estimated/known target {t} size data: {size}")
        
        fetch_target_orbit(t, epochs)                          # once per target
        for ctp in periods:
            target_test(obs_loc, ctp, spn + 600, t, size, mag_min)   # +10 min so windows overlap
    spice.kclear()
