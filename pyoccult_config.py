### CONFIGURATION AND RUN SETUP FOR PYOCCULT ###

### SEARCH SETUP

ct, days, spn = "2026-10-01T00:00:00", 10, 3600
targets = ["218001", "305580", "111287", "115181", "229912", "111286", "54653", "70141", "4272"]
max_shadow_dist = 200  ## km

### CONFIG OBSERVER

LAT = 40.9541175
LON = -72.92614552
ELE = 40

MAG_MIN = 20
MIN_STAR_ALT = 10.0     # deg, use the same constants in both gates
MAX_SUN_ALT  = -6.0     # deg, try -12 for faint stars
ALT_MARGIN   = 3.0      # early gate is looser than the final one, so it never rejects a real event

### CONFIG OUTPUT

hits_output_cvs_file = 'hits_log.csv'

write_maps = True
map_dir = "maps"
default_sigma3_km = 10.0


### Init, Cleanups, ToDO clean SHM cache?
earth_pck_max_age = 7 ## days for earth pck to expire/auto update
force_cleanup = False

