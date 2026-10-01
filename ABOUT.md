# PyOccult: stored memory and computation reference

Two parts: what is stored in memory (verbatim), and a reference of the computations and data used, compiled from your code and our discussion. Memory only holds short project-status lines. The formulas and sources in part 2 come from the code and the conversation, not from memory.

---

## Part 1: Stored memory

**Profile:** not yet written.
**Memory files:** one, `/areas/occultation-predictor.md` (about 3 KB). `[stated]` means you told me directly.

1. [stated] writing a Python asteroid-occultation predictor using SpiceyPy and Astropy: Besselian fundamental-plane miss distance minimized with scipy minimize_scalar; shared code for review
2. [stated] test case: asteroid 19 Fortuna, star near RA 68.98 deg / Dec 16.50 deg, observer at New York City coordinates, center time 2026-10-01T04:30:00 UTC, 24 h search span
3. [stated] real inputs will come from the Gaia catalog (star) and JPL Horizons (asteroid ephemeris); the default values in the test function are placeholders. Asked for a magnitude-drop estimate and sources for best-known asteroid sizes
4. [stated] batch driver: hourly 1 h windows over 7 days from 2026-10-03, about 8 numbered-asteroid targets, Gaia G mag limit 20, fixed observing site at lat 40.9541 / lon -72.9261; hits appended to hits_log.csv
5. [stated] plans to share the data-loading routines (Horizons fetch, Gaia propagation) last and to add a visibility test next
6. [stated] shared star loader fetch_and_propagate_stars: Gaia DR3 cone query via astroquery, default G<=16, RUWE<1.4, astropy apply_space_motion from J2016.0, CSV cache in /dev/shm; asteroid (Horizons) loader still to come
7. [stated] shared Horizons loader fetch_target_orbit: requests the SPK from the Horizons API using the asteroid number plus ';', caches the .bsp in /dev/shm, furnsh + boddef aliasing the number string to the SPK's NAIF id. Asked to add a best-known-size lookup for each target
8. [stated] shared the complete work-in-progress script for review: kernel download/init, Gaia and Horizons loaders, SBDB size lookup, Besselian solver, star screening, batch driver, plus observable / event_metrics / HG-magnitude helpers; runs under Python 3.14 in a .venv
9. [stated] target_test now has an early window-level visibility gate (window_is_observable, before the Gaia query) plus the final observable() check at best_et; hits logged to hits_log_v2.csv
10. [stated] code lives at github.com/pyzahl/PyOccult (main); a few test predictions matched the reference Occult program (occult.exe) and OWC cloud data. Wants Moon-to-target distance and Moon phase added to the hits log; reports the magnitude drop always comes out zero
11. [stated] added moon_info (Moon separation, altitude, illumination, phase age) to the hits log; hits log now also has an "observable" text column
12. [stated] moved run configuration into pyoccult_config.py (search start 2026-10-01, 10 days, 1 h steps, targets 218001/305580/111287/115181/229912/111286/54653/70141/4272, max_shadow_dist 200 km, star mag limit 20, Earth PCK max age 7 days). Wants max magnitude drop and center-line duration, plus shadow center/edge line coordinates and a 3-sigma edge line to map in Google Maps; unsure about the H/G patch idea

---

## Part 2: Pipeline and key computations

### 2.0 Pipeline order (per target, per hourly window)

1. Load kernels once. Fetch the asteroid SPK once per target (`fetch_target_orbit`). Look up size, H and G (`get_asteroid_size`).
2. Early gate: `window_is_observable` (is it dark enough and is the asteroid high enough at the start, middle or end of the window?).
3. Cone-search center: `get_asteroid_ra_dec` (apparent `LT+S`, used only to pick the Gaia cone).
4. Gaia stars: `gaia_cone` (raw, cached), then `fetch_and_propagate_stars` (propagated to the event time, not cached).
5. Geometric prescreen: `screen_stars`.
6. Exact solve per surviving star: `star_test` (bounded minimization of the miss distance).
7. Window-edge rejection, dedupe (`is_new_hit`), final gate (`observable` at `best_et`).
8. Metrics: magnitude drop, speed, chord, duration, Moon info. Append to the hits CSV. Optionally write the shadow-path KML.

### 2.1 Fundamental (Besselian) plane: `besselian_offsets`

- Axes in J2000: **z** = unit vector to the star; **x** = (0,0,1) × z, normalized (points east); **y** = z × x (points north). `M = [x; y; z]`.
- Asteroid position: `spkpos(target, et, 'J2000', 'CN', '399')`. Earth center is 399 (not `'3'`, which is the Earth-Moon barycenter). `CN` is converged light time with no stellar aberration, so it matches astrometric Gaia positions.
- Observer: `georec(lon, lat, alt_km, a, f)` with `a` and `f = (a - c)/a` from `bodvrd('EARTH','RADII',3)`, rotated ITRF93 to J2000 with `pxform('ITRF93','J2000',et)`.
- Offsets: `d = M @ (r_asteroid - r_observer)`, so `(dx, dy) = (d[0], d[1])` (km, east and north). Miss distance = `hypot(dx, dy)`.
- Inputs: `lon`, `lat` in radians, east positive and geodetic; `alt` in km.

### 2.2 Closest approach and hit logic: `star_test`, `target_test`

- `scipy.optimize.minimize_scalar(..., method='bounded')` over `[et_center - span/2, et_center + span/2]`, `xatol = 1e-5` s. Windows are `spn + 600` s long, so neighbouring windows overlap by 10 minutes.
- A solution within 1 s of the window edge is rejected (the neighbouring window finds the real minimum). Duplicates are dropped by `is_new_hit` (same target and star within 300 s).
- Hit: `min_distance < r_search`. "In search range": `min_distance < r_search + max_shadow_dist` (config, 200 km). `r_search = r_max_km` from the size lookup.

### 2.3 Star prescreen: `screen_stars`

- Sample the asteroid's astrometric direction every 60 s across the window. For each star, take the chord distance between its unit vector and each asteroid unit vector and multiply by the asteroid distance, which gives roughly the plane distance in km. Keep stars whose minimum is below the margin.
- Margin in the code is `6378 + r_search + max_shadow_dist` km (Earth radius plus shadow radius and max allowed distance)

### 2.4 Event metrics: `event_metrics`

- Shadow speed `v = hypot(dx(t+1s) - dx(t-1s), dy(t+1s) - dy(t-1s)) / 2` (km/s, shadow relative to the observer).
- Impact parameter `b = hypot(dx, dy)`.
- Chord `= 2 * sqrt(max(r^2 - b^2, 0))`; duration `= chord / v` (zero for any observer outside the shadow).
- `max_duration_s = 2 * r / v` (center-line duration).
- Logged `offset_east_km` and `offset_north_km` are the axis minus the observer on the plane, i.e. how far to move to get on the center line (plane distances, not ground distances).

### 2.5 Magnitude drop: `event_metrics`, `apparent_mag_HG`

- Drop (star fully covered): `dm = 2.5 * log10(1 + 10^(0.4 * (m_ast - m_star)))`. Near zero when the asteroid is much brighter than the star.
- `m_star`: Gaia G (a proxy; convert with `bp_rp` for V or R if you compare with Occult or OWC).
- `m_ast` from H, G: `V = H + 5*log10(r*Delta) - 2.5*log10((1-G)*Phi1 + G*Phi2)`
  - `Phi1 = exp(-3.33 * tan(alpha/2)^0.63)`, `Phi2 = exp(-1.87 * tan(alpha/2)^1.22)`
  - `r` = Sun-asteroid and `Delta` = Earth-asteroid distance in AU (SPICE `LT` positions); `alpha = vsep(ast_from_sun, ast_from_earth)` is the phase angle at the asteroid. Default `G = 0.15`.
- Model accuracy is about +/-0.2 to 0.3 mag, plus the rotational lightcurve amplitude.
- If `size['H']` is missing, `m_ast` and `mag_drop` come out NaN (blank in the CSV), not 0.

### 2.6 Visibility gates: `observable`, `window_is_observable`

- Local vertical: geodetic normal `(cos lat cos lon, cos lat sin lon, sin lat)` in ITRF, rotated to J2000.
- Altitude `= asin(up . direction)`. Sun direction from `spkpos('SUN', ..., 'LT+S', '399')`.
- Config thresholds: `MIN_STAR_ALT = 10`, `MAX_SUN_ALT = -6` (try -12 for faint stars), `ALT_MARGIN = 3`.
- Early gate uses the asteroid direction as a stand-in for the star and is looser by `ALT_MARGIN`; the final gate uses the real star direction at `best_et`.

### 2.7 Moon: `moon_info`

- Separation: `vsep(moon_geo - observer_j2000, star_dir)`, topocentric because the Moon's parallax is about 1 deg.
- Illumination: `(1 + cos(alpha)) / 2` with `alpha = vsep(moon_from_sun, moon_geo)`, the phase angle at the Moon.
- Phase age: ecliptic-longitude difference Moon minus Sun, mod 360 (0 new, 90 first quarter, 180 full, 270 last quarter).
- Also logged: Moon altitude from the observer.

### 2.8 Star positions: `gaia_cone`, `fetch_and_propagate_stars`

- Gaia DR3, `gaiadr3.gaia_source`: `source_id, ra, dec, parallax, pmra, pmdec, phot_g_mean_mag, ruwe`. Filters: `G <= mag_limit`, proper motion not null, `RUWE < 1.4`. Cone radius 10 arcmin around a 5-arcmin tile center. The raw table is cached in `/dev/shm`.
- Reference epoch J2016.0 = 2016-01-01 12:00 TCB. Distance `= 1000 / parallax` pc with the parallax floored at 0.01 mas (avoids the ERFA "distance overridden" warning). `apply_space_motion` brings positions to the event time (UTC) and adds `ra_YYYYMMDD` and `dec_YYYYMMDD`.
- Not applied: the geocentric parallax correction (`geocentric_star_dir` exists; roughly 1 km on the plane per mas at 1.4 AU), the star's angular diameter, and diffraction. These matter for bright stars and kilometre-size bodies.

### 2.9 Asteroid size: `get_asteroid_size`

Order of precedence:
1. `SIZE_OVERRIDES` (your curated occultation or shape-model values).
2. SBDB `diameter` with its sigma (15% assumed if missing); radius bounds are +/-3 sigma and are widened by tri-axial `extent` semi-axes.
3. H plus SBDB albedo `p`.
4. H only, albedo 0.14 (range 0.05 to 0.30).

`D = 1329 / sqrt(p) * 10^(-H/5)` km; radius = D/2. Bounds `r_min_km` and `r_max_km` describe size uncertainty only, not ephemeris uncertainty. Clamp `r_min_km` at 0.

### 2.10 Shadow ground track for Google My Maps: `pyoccult_paths.py`

- Every 30 s over +/-30 min around `best_et`: axis point on the plane, shadow velocity from a 1 s finite difference, an in-plane unit vector across the track.
- Five lines: center, +/-r (shadow limits), +/-(r + 3 sigma). Each offset point is projected along -z onto the Earth ellipsoid with `surfpt`, then `recgeo` gives longitude and latitude.
- Center-line duration at each point: `2r / |v_axis - v_ground|`.
- 3 sigma: Horizons observer table `RSS_3sigma` (arcsec) times the geocentric distance, converted to km. Falls back to a config default when no covariance exists.
- Output is KML with UTC time ticks, an observer pin, and the five lines. Import into Google My Maps.

---

## Part 3: Data sources and kernels

| Item | Source | Used for |
|---|---|---|
| `naif0012.tls` | NAIF generic kernels (LSK) | Leap seconds, `str2et` |
| `pck00010.tpc` | NAIF generic kernels (PCK) | Planetary constants, Earth radii |
| `de440.bsp` | NAIF generic kernels (SPK) | Earth, Sun, Moon, planets |
| `earth_latest_high_prec.bpc` | NAIF generic kernels (binary PCK) | ITRF93 Earth orientation; refreshed after `earth_pck_max_age` (7 days) |
| Asteroid SPK | Horizons API, `ssd.jpl.nasa.gov/api/horizons.api` (`COMMAND=<number>;`, `EPHEM_TYPE=SPK`), cached in `/dev/shm` | Asteroid position |
| Size, H, G, albedo, extent | SBDB API, `ssd-api.jpl.nasa.gov/sbdb.api?sstr=<n>&phys-par=1` | `get_asteroid_size` |
| Names and SPK ids | SBDB Query API (`sbdb_query.api`), cached in `jpl_asteroids_spice.csv` | `get_asteroid_name` |
| Stars | Gaia DR3 via astroquery TAP | Star positions, G magnitude |
| Path uncertainty | Horizons observer table (`RSS_3sigma`) | 3-sigma limit lines |

### Config (`pyoccult_config.py`)

| Setting | Value |
|---|---|
| Search start / length / step | 2026-10-01T00:00:00, 10 days, 3600 s |
| Targets | 218001, 305580, 111287, 115181, 229912, 111286, 54653, 70141, 4272 |
| `max_shadow_dist` | 200 km |
| Observer | lat 40.9541175, lon -72.92614552, 40 m |
| Star magnitude limit | 20 |
| Altitude thresholds | `MIN_STAR_ALT` 10, `MAX_SUN_ALT` -6, `ALT_MARGIN` 3 |
| Output | `hits_log.csv` |

### Hits log columns

`target_id, target_name, best_utc, best_et, min_distance, margin_km` (distance minus radius), `r_km, r_min_km, r_max_km, r_search_km, size_source, star` (Gaia id), `mag` (G), `star_ra, star_dec, star_alt, sun_alt, m_ast, speed_kms, chord_km, duration_s, mag_drop, moon_sep_deg, moon_alt_deg, moon_illum_pct, moon_age_deg, observable, offset_east_km, offset_north_km, max_duration_s`. With the maps module: `sigma3_km, margin_in_sigma`.

---

## Part 4: Open items and unverified points (as of the last review)

- `target_test` record had literal `...` placeholders for `r_min_km`, `r_max_km`, `source`, which become `Ellipsis` in the CSV. Replace with `size['r_min_km']` and `size['r_max_km']`, and drop `source`.
- `get_asteroid_size` must return `H` and `G` in every branch (the diameter branch returns before they are read), otherwise `m_ast` and `mag_drop` stay NaN.
- `star_test` uses `if not observable(...)`, but `observable` returns a tuple (always truthy). Use `observable(...)[0]`.
- `screen_stars` margin does not yet include `max_shadow_dist`.
- `gaia_cone` still uses `launch_job` (synchronous, possibly capped at about 2000 rows; unverified), queries `radius_arcmin` without the `+5` tile padding its comment mentions, and returns `None` on failure (the caller then crashes on `.copy()`).
- The ADQL string still has an inline `--` comment.
- Unverified (written from memory of the APIs, not run against the real services): SBDB `phys_par` field names; Horizons `RSS_3sigma` and `delta` column names; `surfpt` and `recgeo` argument handling in `pyoccult_paths.py` (tested only against a mock spherical Earth); the Earth-PCK body id (3000) for `pckcov`.
- Validation: a few predictions matched Occult (occult.exe) and OWC cloud data, as stated by you. The magnitude-drop, Moon and shadow-path outputs have not yet been compared against them.