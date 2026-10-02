# Observing sites. Copy this file to sites.py (not in git) and enter your own sites there.
# pyoccult_config.py uses `default_site`, or the site named in the environment variable PYOCCULT_SITE:
#     PYOCCULT_SITE=field ./pyoccult.py
#
# Required: lat, lon (geodetic degrees, longitude east-positive, west is negative), ele (metres).
# Optional (defaults in pyoccult_config.py):
#   view      min_alt (deg, lowest usable star altitude, default 10), max_sun_alt (deg, default -6),
#             reach_km (km you can travel from here, default max_shadow_dist)
#   equipment for OWC's General Observability Criterion, StarMag < 5 log10(aperture_cm)
#             + 2.5 log10(MaxDuration / frames) + 8.5 + mag_adjust:
#             aperture_cm (default 25), frames (detection frames, default 4), mag_adjust (default 0; + for dark sky or
#             a sensitive camera, - for worse), extinction (mag per airmass at the star's altitude, default 0 = off,
#             ~0.2 typical), min_dur_s (hard limit, default 0.4), max_exp_s (longest usable exposure, default 0.64).
#             The faintest star searched follows (25 cm: G 15.0, 50 cm: G 16.5), or set it with mag_limit.
#   camera    focal_mm (default f/10 = 100 x aperture_cm), sensor_mm (width, height; default (5.6, 3.2)):
#             the camera field drawn in the event preview.

sites = {
    "nyc": dict(lat=40.7128, lon=-74.0060, ele=10, name="New York City Hall (example)",
                aperture_cm=25, min_alt=20),
    "field": dict(lat=41.3000, lon=-74.6000, ele=450, name="Dark-sky field (example)",
                  aperture_cm=35, min_alt=10, max_sun_alt=-12, reach_km=50),
}

default_site = "nyc"
