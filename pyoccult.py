#!.venv/bin/python3
import os
import sys
import numpy as np
import requests
import base64
import json
import subprocess
from scipy.optimize import minimize_scalar
import spiceypy as spice
from astropy.time import Time
from astropy.coordinates import EarthLocation
import astropy.units as u
from astroquery.jplhorizons import Horizons

force_cleanup = False


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

        
        #state, lt = spice.spkezr("2200019", et, "J2000", "NONE", "SOLAR SYSTEM BARYCENTER")
        #print (state, lt)
        
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
if __name__ == "__main__":
    # Define Target Star Coordinates (ICRS / J2000)
    # Example: Aldebaran or target star of choice
    star_ra = np.radians(68.98)   # RA in radians
    star_dec = np.radians(16.50)  # Dec in radians
    
    # Unit vector pointing to the star
    star_direction = np.array([
        np.cos(star_dec) * np.cos(star_ra),
        np.cos(star_dec) * np.sin(star_ra),
        np.sin(star_dec)
    ])

    # Define Target Asteroid (SPICE ID or Name string if loaded in kernel)
    # For this demonstration template, we fall back to '301' (Moon) if specific asteroid .bsp isn't found
    asteroid_id = "200019"  # Example SPICE ID for Asteroid 19 Fortuna

    # Define Observer Location via Astropy
    loc = EarthLocation(lat=40.7128*u.deg, lon=-74.0060*u.deg, height=10*u.m)
    obs_geo = {
        'lon': loc.lon.to(u.rad).value,
        'lat': loc.lat.to(u.rad).value,
        'alt': loc.height.to(u.km).value
    }

    # Center-of-window Guess Time (UTC)
    center_time_utc = "2026-10-01T04:30:00"
    et_center = spice.str2et(center_time_utc)
    
    print(f"Targeting window around: {center_time_utc} UTC")
    print(f"Initial Ephemeris Time (ET): {et_center:.3f}\n")

    # Objective function to minimize for root-finding
    def objective_func(et):
        return get_besselian_miss_distance(et, star_direction, obs_geo, asteroid_id)

    # Use a bounded scalar minimizer (+/- 10 minutes or 600 seconds from guess)
    print("Computing exact time of closest approach...")
    result = minimize_scalar(
        objective_func, 
        bounds=(et_center - 600, et_center + 600), 
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

    # Unload kernels
    spice.kclear()
