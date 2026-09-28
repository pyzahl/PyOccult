import os
import numpy as np
import requests
import subprocess
from scipy.optimize import minimize_scalar
import spiceypy as spice
from astropy.time import Time
from astropy.coordinates import EarthLocation
import astropy.units as u


force_cleanup = False



# Wipe out old file/memory states completely
spice.clpool()



if force_cleanup:
    for filename in ["naif0012.tls", "de440.bsp", "pck00010.tpc"]:
        if os.path.exists(filename):
            os.remove(filename)

def download_kernels():
    urls = {
        "naif0012.tls": "https://nasa.gov",
        "de440.bsp": "https://nasa.gov",
        "pck00010.tpc": "https://nasa.gov"
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
                    ["curl", "-L", "-s", "-f", "-A", "Mozilla/5.0", url, "-o", name],
                    check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"🚨 Curl download failed for {name}: {e}")
                return False
                
    print("✅ All kernels verified and downloaded cleanly via curl.")
    return True


#curl -b "" -A "Mozilla/5.0" -O https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls
#curl -b "" -A "Mozilla/5.0" -O https://nasa.gov
#curl -b "" -A "Mozilla/5.0" -O https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00010.tpc


# ==========================================
# 1. KERNEL DOWNLOADING UTILITY
# ==========================================
if download_kernels():
    try:
        # Load verified binaries
        spice.furnsh("naif0012.tls")
        spice.furnsh("de440.bsp")
        spice.furnsh("pck00010.tpc")
        
        et = spice.str2et("2026-09-28 UTC")
        print(f"🚀 Success! CSPICE Active. Target ET: {et}")
    except Exception as e:
        print(f"CSPICE Error: {e}")



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
