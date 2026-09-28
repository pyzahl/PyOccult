#!.venv/bin/python3
import os
import sys
import numpy as np
import requests
import base64
import json
import subprocess
import pandas as pd
from pathlib import Path

from scipy.optimize import minimize_scalar
import spiceypy as spice
from astropy.time import Time
from astropy.coordinates import EarthLocation
import astropy.units as u
from astroquery.jplhorizons import Horizons
from astroquery.gaia import Gaia


force_cleanup = False


# The correct endpoint for querying the bulk database
URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"

import json
import pandas as pd
import requests

# The correct endpoint for querying the bulk database
URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"


def get_all_jpl_asteroids_with_spice():
    print("Querying JPL Database for entries and SPICE IDs... (This may take a moment)")
    output_file = "jpl_asteroids_spice.csv"
    fp = Path(output_file)
    if fp.is_file():
        print("JPL db already fetched!")
        return
    
    
    # Added 'spkid' to the requested fields parameter
    params = {
        "sb-kind": "a",  # Limit search results to asteroids-only
        "fields": "spkid,full_name,pdes",  # Fetch SPICE/SPK ID, full name, and primary designation
    }

    try:
        response = requests.get(URL, params=params)
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

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while connecting to JPL: {e}")
    except json.JSONDecodeError:
        print("Failed to parse the response from JPL.")



get_all_jpl_asteroids_with_spice()






def fetch_occultation_stars(ra_deg, dec_deg, radius_arcmin=10.0, mag_limit=16.0):
    """
    Fetches high-precision star data from Gaia DR3 for occultation calculations.
    
    Parameters:
    ra_deg (float): Center Right Ascension in decimal degrees (ICRS)
    dec_deg (float): Center Declination in decimal degrees (ICRS)
    radius_arcmin (float): Cone search radius in arcminutes
    mag_limit (float): Faintest G-band magnitude to include
    """
    print(f"Querying Gaia DR3 around RA={ra_deg}°, DEC={dec_deg}°...")
    
    # Convert arcminutes radius to degrees for ADQL
    radius_deg = radius_arcmin / 60.0
    
    # Precise ADQL query targeting essential variables for occultation propagation:
    # Position, Proper Motions, Parallax, Errors, and Quality Metrics (RUWE)
    query = f"""
    SELECT 
        source_id, ra, ra_error, dec, dec_error, 
        parallax, parallax_error, pmra, pmra_error, pmdec, pmdec_error,
        phot_g_mean_mag, ruwe
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(
        POINT('ICRS', ra, dec), 
        CIRCLE('ICRS', {ra_deg}, {dec_deg}, {radius_deg})
    )
    AND phot_g_mean_mag <= {mag_limit}
    AND ruwe < 1.4  -- Filter out problematic binaries or noisy astrometry solutions
    """
    
    try:
        # Launch synchronous job to Gaia archive
        job = Gaia.launch_job(query)
        astropy_table = job.get_results()
        
        # Convert to Pandas for clean analysis/saving
        df = astropy_table.to_pandas()
        
        # Note the reference epoch information
        print(f"Successfully retrieved {len(df)} reference stars.")
        print("Note: Gaia DR3 base coordinates are tied to Epoch J2016.0.")
        
        # Export data matrix
        output_file = "gaia_occultation_catalog.csv"
        df.to_csv(output_file, index=False)
        print(f"Table saved cleanly to '{output_file}'.")
        return df

    except Exception as e:
        print(f"An error occurred during the registry lookup: {e}")
        return None


    
# Example: Querying a field around a target location 
# (e.g., RA: 10h 0m 0s -> 150.0°, DEC: +02° 00' 00" -> 2.0°)
target_ra = 150.0
target_dec = 2.0
    
star_table = fetch_occultation_stars(target_ra, target_dec, radius_arcmin=15.0, mag_limit=15.5)

print (star_table)




import numpy as np
import pandas as pd
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astroquery.gaia import Gaia


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

    print(
        f"Querying Gaia DR3 & propagating positions to: {target_time.iso} UTC..."
    )

    radius_deg = radius_arcmin / 60.0
    query = f"""
    SELECT 
        source_id, ra, dec, parallax, pmra, pmdec, phot_g_mean_mag, ruwe
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra_deg}, {dec_deg}, {radius_deg}))
    AND phot_g_mean_mag <= {mag_limit}
    AND pmra IS NOT NULL AND pmdec IS NOT NULL -- Required for propagation
    AND ruwe < 1.4
    """

    try:
        job = Gaia.launch_job(query)
        df = job.get_results().to_pandas()

        # Handle missing or negative parallaxes safely by clipping them to 0 (very distant stars)
        safe_parallax = np.where(
            df["parallax"].isna() | (df["parallax"] < 0), 0, df["parallax"]
        )

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

        output_file = "propagated_occultation_catalog.csv"
        df.to_csv(output_file, index=False)
        print(f"Successfully processed {len(df)} stars.")
        print(f"Saved computed coordinates cleanly to '{output_file}'.")
        return df

    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def CoordinateDistance(parallax_mas):
    """Helper to convert parallax safely to distance."""
    # Where parallax is 0, place the star effectively at infinity (100,000 parsecs)
    distance_pc = np.where(parallax_mas > 0, 1000.0 / parallax_mas, 100000.0)
    return distance_pc * u.pc





# Wipe out old file/memory states completely
spice.clpool()



if force_cleanup:
    print ('Cleanup old files:')
    for filename in ["naif0012.tls", "de440.bsp", "pck00010.tpc"]:
        if os.path.exists(filename):
            print ('removing: ', filename)
            os.remove(filename)



# 1. Define the precise API parameters for 19 Fortuna (SPK-ID: 2000019)
url = "https://ssd.jpl.nasa.gov/api/horizons.api"
params = {
    "format": "json",
    "COMMAND": "'19;'",  # '19;' targets asteroid 19 Fortuna directly
    "EPHEM_TYPE": "SPK",
    "OBJ_DATA": "NO",
    "START_TIME": "2026-01-01",
    "STOP_TIME": "2027-01-01",
}

print("Fetching precise data stream from NASA JPL Horizons...")
response = requests.get(url, params=params)
result = response.json()

# 2. Extract and decode the raw binary file payload
if "spk" in result:
    print("Decoding binary file payload...")
    binary_data = base64.b64decode(result["spk"])

    with open("19_fortuna.bsp", "wb") as f:
        f.close_write = f.write(binary_data)
    print("Success! File saved precisely as '19_fortuna.bsp'")
else:
    print("Error generating SPK. Server returned:")
    print(json.dumps(result, indent=2))


  
# Configure the request for asteroid 200019

# 1. Define the JPL Horizons API endpoint
url = "https://nasa.gov"


# 2. Configure parameters for a small-body SPK file
params = {
    "COMMAND": "'200019;'",       # Asteroid target body sequence
    "OBJ_DATA": "NO",             # Turn off text metadata summaries
    "MAKE_EPHEM": "YES",          # Request ephemeris generation
    "EPHEM_TYPE": "SPK",          # Requests the raw binary BSP stream
    "START_TIME": "2026-01-01",
    "STOP_TIME": "2027-01-01",
}

print("Requesting SPK file from JPL Horizons...")

# 3. Use stream=True to handle the binary file download safely
response = requests.get(url, params=params, stream=True)

# 4. Check for success and write the binary content directly to a file
if response.status_code == 200:
    output_filename = "asteroid_200019.bsp"
    
    with open(output_filename, "wb") as f:
        # Read the raw binary content chunks and write to disk
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    if os.path.getsize(output_filename) > 500:  # Simple check to make sure it isn't an error message
        print(f"Success! Saved SPK file to: {os.path.abspath(output_filename)}")
    else:
        # If the file is tiny, it means JPL returned a text error message instead of an SPK
        with open(output_filename, "r") as f:
            print("\nJPL Error Message:")
            print(f.read())
        os.remove(output_filename) # Clean up the broken text file
else:
    print(f"Server error: HTTP {response.status_code}")




# 1. Official JPL Horizons API Endpoint
url = "https://ssd.jpl.nasa.gov/api/horizons.api"

# 2. Configure parameters
# For a numbered asteroid, the ID must have a trailing semicolon inside the quotes
params = {
    'format': 'json',
    'COMMAND': '200019;',
    'EPHEM_TYPE': 'SPK',
    'MAKE_EPHEM': 'YES',
    'START_TIME': '2026-01-01',
    'STOP_TIME': '2027-01-01',
    "OBJ_DATA": "NO",
}

print("Querying JPL API...")
response = requests.get(url, params=params)

# 3. Handle response content-type safely
if response.status_code == 200:
    content_type = response.headers.get("Content-Type", "")
    
    if "application/json" in content_type:
        data = response.json()
        
        if "spk" in data:
            print("SPK data block found. Decoding Base64 stream...")
            # JPL packages the binary BSP stream inside a base64-encoded string
            spk_binary = base64.b64decode(data["spk"])
            
            output_filename = "asteroid_200019.bsp"
            with open(output_filename, "wb") as f:
                f.write(spk_binary)
                
            print(f"Success! Saved binary SPK to: {os.path.abspath(output_filename)}")
        else:
            print("❌ JPL returned JSON, but it didn't contain an SPK file.")
            print("JPL Message:", data.get("result", "No details available."))
            
    else:
        print("❌ Received non-JSON response (likely an HTML webpage or raw configuration text).")
        print("First 300 characters of response:")
        print(response.text[:300])
       
else:
    print(f"❌ HTTP Error: Server responded with status code {response.status_code}")


    
    
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


# ==========================================
# 1. KERNEL DOWNLOADING UTILITY
# ==========================================
if download_kernels():
    try:
        print ('* Loading Compute Kernels *')
        # Load all required kernels
        spice.furnsh("naif0012.tls")       # Leapseconds
        spice.furnsh("pck00010.tpc")       # Planetary constants
        spice.furnsh("de440.bsp")          # Major planets base
        spice.furnsh("earth_latest_high_prec.bpc")
        spice.furnsh("19_fortuna.bsp")     # specific asteroid data
        spice.furnsh("asteroid_200019.bsp")
        # 2. Force SPICE to map the name string "200019" to the internal NAIF ID 2200019
        spice.boddef("200019", 2200019)
        
        print ('* Testing Compute Kernels *')
        
        et = spice.str2et("2026-09-28 UTC")
        print(f"🚀 Success! CSPICE Active. Target ET: {et}")



        # 2. Extract the exact hidden NAIF ID code from your SPK file cover
        # spkobj returns an array of all integer IDs present in the file
        spk_ids = spice.spkobj("asteroid_200019.bsp")

        if spk_ids:
            actual_jpl_id = int(spk_ids[0])
            print(f" Detected ID inside file: {actual_jpl_id}")

            # 3. Explicitly alias all variations to this detected ID code
            spice.boddef("200019", actual_jpl_id)
            spice.boddef("2200019", actual_jpl_id)

            # 4. Perform the evaluation safely using the mapped string name
            et = spice.str2et("2026 SEP 28 00:01:09.182")
            state, lt = spice.spkezr("200019",et, "J2000", "NONE", "0")
            print("\n✅ Success! State Vector relative to SSB (0):")
            print(state)
        else:
            print("❌ Critical: The asteroid_200019.bsp file appears empty or corrupted.")


        print ('List of Asterioids:')
        # Execute the iteration
        list_spk_contents("asteroid_200019.bsp")


            
    except Exception as e:
        print(f"CSPICE Error: {e}")
        sys.exit('Exiting as of error.')


print ('* Ready *')
        

# Note: For a real asteroid, you would also download its specific orbital .bsp kernel
# from JPL Horizons and load it here: spice.furnsh("asteroid_name.bsp")

# ==========================================
# 2. BESSELIAN PLANE SOLVER ENGINE
# ==========================================
def get_besselian_miss_distance(et, star_vector, observer_geo, asteroid_target):
    """
    Calculates the distance between the observer and the center of the asteroid's
    shadow axis on the Besselian Fundamental Plane at Ephemeris Time (et).
    """
    # 1. Direction vector from Earth center to the Star (z-axis of Besselian plane)
    z_axis = star_vector / np.linalg.norm(star_vector)

    # 2. Construct the rest of the fundamental plane coordinate system (x and y axes)
    # Define a temporary vector to cross with to get equatorial perpendiculars
    temp_vec = np.array([0.0, 0.0, 1.0]) if abs(z_axis[2]) < 0.99 else np.array([0.0, 1.0, 0.0])
    x_axis = np.cross(temp_vec, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)

    # Transform matrix from J2000 to Besselian Plane
    M_bessel = np.vstack((x_axis, y_axis, z_axis))

    # 3. Position of Asteroid relative to Earth Center (J2000), corrected for light time
    # (Using '3' for Earth Center, 'CN+S' for converged Newtonian light time + stellar aberration)
    try:
        ast_pos, _ = spice.spkpos(asteroid_target, et, 'J2000', 'CN+S', '3')
    except spice.stypes.SpiceException:
        # Fallback to an available body (e.g., Moon '301') if running this as a test mock
        ast_pos, _ = spice.spkpos('301', et, 'J2000', 'CN+S', '3')

    # 4. Position of Observer relative to Earth Center (ITRF93 converted to J2000 at time et)
    # Convert geodetic to body-fixed XYZ
    r_earth = 6378.137  # Earth equatorial radius
    f_earth = 1.0 / 298.257223563  # Flattening factor
    obs_itrf = spice.georec(observer_geo['lon'], observer_geo['lat'], observer_geo['alt'], r_earth, f_earth)
    
    # Get rotation matrix from Earth-fixed frame to J2000 inertial frame
    m_rot = spice.pxform('ITRF93', 'J2000', et)
    obs_j2000 = spice.mxv(m_rot, obs_itrf)

    # 5. Project both vectors onto the Besselian Plane
    ast_bessel = spice.mxv(M_bessel, ast_pos)
    obs_bessel = spice.mxv(M_bessel, obs_j2000)

    # On the Fundamental Plane, we only care about the x and y coordinates
    # The shadow axis passes through the asteroid's x, y coordinates
    dx = ast_bessel[0] - obs_bessel[0]
    dy = ast_bessel[1] - obs_bessel[1]
    
    # Return the scalar distance (miss distance of shadow center to observer)
    return np.sqrt(dx**2 + dy**2)


# ==========================================
# 3. EXECUTION AND TEST HARNESS
# ==========================================
def test_star (loc = EarthLocation(lat=40.7128*u.deg, lon=-74.0060*u.deg, height=10*u.m),
               center_time_utc = "2026-10-01T04:30:00", time_span = 24*3600,
               star_ra=np.radians(68.98), star_dec=np.radians(16.50),
               asteroid_id = "200019"):
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
        r_asteroid = 50.0 
        if min_distance < r_asteroid:
            print(f"👉 SUCCESS: An occultation is PREDICTED at this site! Observer inside the shadow path.")
        else:
            print(f"❌ MISS: Shadow path misses observer by {min_distance - r_asteroid:.3f} km.")
    else:
        print("Solver failed to converge on an event window.")




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


    #finally:
    #    # Always clear loaded files to prevent pool contamination on repeated execution loops
    #    spice.unload("de440.bsp")
    #    spice.unload("naif0012.tls")



def test_target (loc = EarthLocation(lat=40.7128*u.deg, lon=-74.0060*u.deg, height=10*u.m),
                 event_search_center_time_utc = "2026-10-01T04:30:00", time_span=24*3600,
                 target_id="200019",
                 mag_lim = 20.0):
        
    # Define column shortcut headers based on your target date
    # (Assumes the column name dynamically created by the script, e.g., 'ra_20261105')
    ra_col = "ra_20261105"
    dec_col = "dec_20261105"

    # fix me
    ra_col = "ra_20261001"
    dec_col = "dec_20261001"

    
    target = get_asteroid_ra_dec(target_id,
                                 utc_time=event_search_center_time_utc, #"2026-11-05 04:15:30",
                                 observer="EARTH",
                                 ref_frame="J2000",
                                 abcorr="LT+S",  # Critical light-time + stellar aberration for real sky coordinates
                                 )

    print ('Target: ', target_id, target)
    
    # Example: A path center coordinate and a specific target event time

    event_df = fetch_and_propagate_stars(
        target['ra'], target['dec'], event_time_str=event_search_center_time_utc, radius_arcmin=10.0
    )
 
    
    print("\nIterating through propagated star positions:")
    for row in event_df.itertuples(index=False):
        # Access attributes cleanly by column header names
        star_id = row.source_id
        mag = row.phot_g_mean_mag

        print (row, star_id)
        
        if mag <= mag_lim:
            # Retrieve the exact propagated coordinates for your event time
            propagated_ra  = getattr(row, ra_col)
            propagated_dec = getattr(row, dec_col)

            print(f"Star ID: {star_id} | Mag: {mag:.2f} | Propagated RA: {propagated_ra:.6f}° | Dec: {propagated_dec:.6f}°")
            test_star (loc,
                       event_search_center_time_utc, time_span,
                       np.radians (propagated_ra), np.radians (propagated_dec), "200019")


## TEST MAIN
    
if __name__ == "__main__":

    test_target (EarthLocation(lat=40.7128*u.deg, lon=-74.0060*u.deg, height=10*u.m), # Observer Location
                 "2026-10-01T04:30:00", # Center of search time interval UTC
                 24*3600,               # Search Time Interval in sec
                 target_id="200019",    # asteriod target to check (Fortuna 19)
                 mag_lim = 20.0)        # star mag limit
    
    # Unload kernels
    spice.kclear()

            

    
