# PyOccult: stored memory and computation reference

Part 1 is what is stored in memory (verbatim). The other parts are a reference of the computations, data, open points and validation, compiled from your code and our discussion. Memory only holds short project-status lines. The formulas, sources and findings in the later parts come from the code and the conversation, not from memory. Updated 2026-10-01.

---

## Part 1: Stored memory

**Profile:** not yet written.
**Memory files:** one, `/areas/occultation-predictor.md` (about 3.5 KB). `[stated]` means you told me directly.

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
13. [stated] motivation: occult.exe (the reference Windows tool behind OWC) is old and outdated but precise; the goal is a more modern, portable Python-based replacement
14. [stated] next planned piece: a tool plus metrics to build the list of asteroid ids for the targets config; has an extensive asteroid list jpl_asteroids_spice.csv (columns SPICE ID, Full Name, Primary Designation) used for name lookup. Also turns hits_log.csv into an HTML report with map links, viewed via local nginx

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
9. Outside the search: `pyoccult_report.py` turns the CSV into the HTML list (2.11); `pyoccult_pick.py` chooses the targets beforehand (2.12).

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
- **`mag_drop` is the change in combined brightness, not the magnitude you drop to.** The brightness before the event is `m_before = -2.5 * log10(10^(-0.4*m_star) + 10^(-0.4*m_ast))`, during the event it is `m_ast`, and `mag_drop = m_ast - m_before`. It is therefore never smaller than `m_ast - m_star`, and it can be smaller than the star magnitude itself (this is how OWC lists it too).
- `m_star`: Gaia G (a proxy; convert with `bp_rp` for V or R if you compare with Occult or OWC).
- `m_ast` from H, G: `V = H + 5*log10(r*Delta) - 2.5*log10((1-G)*Phi1 + G*Phi2)`
  - `Phi1 = exp(-3.33 * tan(alpha/2)^0.63)`, `Phi2 = exp(-1.87 * tan(alpha/2)^1.22)`
  - `r` = Sun-asteroid and `Delta` = Earth-asteroid distance in AU (SPICE `LT` positions); `alpha = vsep(ast_from_sun, ast_from_earth)` is the phase angle at the asteroid. Default `G = 0.15`.
- Model accuracy is about +/-0.2 to 0.3 mag, plus the rotational lightcurve amplitude.
- If `size['H']` is missing, `m_ast` and `mag_drop` come out NaN (blank in the CSV), not 0. You confirmed the values now flow after `get_asteroid_size` returns H and G in every branch.

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
- Not applied: the geocentric parallax correction (`geocentric_star_dir` exists; roughly 1 km on the plane per mas at 1.4 AU), the star's angular diameter (see Part 5), and diffraction. These matter for bright stars and kilometre-size bodies.

### 2.9 Asteroid size: `get_asteroid_size`

Order of precedence:
1. `SIZE_OVERRIDES` (your curated occultation or shape-model values).
2. SBDB `diameter` with its sigma (15% assumed if missing); radius bounds are +/-3 sigma and are widened by tri-axial `extent` semi-axes.
3. H plus SBDB albedo `p`.
4. H only, albedo 0.14 (range 0.05 to 0.30).

`D = 1329 / sqrt(p) * 10^(-H/5)` km; radius = D/2. Bounds `r_min_km` and `r_max_km` describe size uncertainty only, not ephemeris uncertainty. Clamp `r_min_km` at 0. Every branch must also return `H` and `G`.

### 2.10 Shadow ground track for Google My Maps: `pyoccult_paths.py` (v2)

- Time span and step are derived from the shadow speed: about 1.3 Earth radii of along-track motion on each side of `best_et` (a slow shadow, e.g. 70141, gets a longer span) and about 100 km of track per step (1 to 60 s). Axis point on the plane, shadow velocity from a 1 s finite difference, an in-plane unit vector across the track.
- Five lines: center, +/-r (shadow limits), +/-(r + 3 sigma). Each offset point is projected along -z onto the Earth ellipsoid with `surfpt`, then `recgeo` gives longitude and latitude.
- SpiceyPy's `surfpt` returns only the point and raises `NotFoundError` when the ray misses the Earth. v2 catches it and skips that sample, so lines can differ in length and may be empty (the first version unpacked a `(point, found)` tuple and crashed near the ends of the window).
- Center-line duration at each point: `2r / |v_axis - v_ground|`.
- 3 sigma: `path_sigma3_km` takes the Horizons observer-table RSS 3-sigma position uncertainty (arcsec) times the geocentric distance, in km. The column is found by name (`RSS`, then `3SIGMA`/`POS`); the exact Horizons column names are unverified. Falls back to a config default when no covariance exists.
- Output is KML (colours are `aabbggrr`): center green (width 3), shadow limits red, 3-sigma limits yellow, UTC time ticks with the center-line duration every 10 samples, optional observer pin. Import into Google My Maps.
- Tested against a stand-in `spiceypy` that follows the real contract (exact ellipsoid and rotation geometry, synthetic ephemerides): points lie on the offset shadow axis to 1e-6 km, on the star-facing side, center-line duration matches an independent calculation. Not yet run against real SPICE and Horizons.

### 2.11 Report: `pyoccult_report.py`

- Reads `hits_log.csv` (tolerates repeated headers and short rows), drops duplicates, and optionally filters by `--max-miss` and `--min-drop`. Output is HTML (default) or Markdown.
- Columns, as in OWC: asteroid (number and name), event time (UT), star mag, mag drop, max duration, altitude with compass direction, Moon distance (Moon icon only when it is above the horizon), offset (miss distance, "inside shadow" or "N km outside"), map.
- Compass azimuth at the event time uses only the standard library: J2000 star position precessed to the date (Meeus, IAU 1976) and Greenwich mean sidereal time. Checked against the logged altitude to 0.002 deg.
- KML for each event is found by `<asteroid>_<YYYYMMDDTHHMM>*.kml` in the maps folder (`--kml-dir`, else `map_dir` from the config, else `./maps`), converted to compact JSON and embedded in the page.
- Map viewer: Leaflet 1.9.4 from cdnjs; basemaps Carto light (default), Esri satellite, OpenStreetMap, with a layer switcher; `--tile-url` replaces them with one template. The initial view fits the observer and the nearest point of the center line (equirectangular segment projection), with "Zoom to observer" and "Whole path" buttons and a Google Maps link to that nearest point (`https://www.google.com/maps/search/?api=1&query=lat,lon`).
- Line styles: center `#15803d` (width 3), shadow limit `#dc2626` (2), 3-sigma `#d97706` (dashed).
- A banner appears if tiles fail to load, and a message if Leaflet itself cannot load (offline).
- Why a web server: OpenStreetMap's tile policy expects a Referer, which pages opened from `file://` do not send. You confirmed the map renders when the report is served by a local nginx from `/var/www/html`.

### 2.12 Target picker: `pyoccult_pick.py`

- Names come from `jpl_asteroids_spice.csv`; properties (H, G, diameter, albedo, orbit elements, condition code, NEO flag, class) come from one SBDB bulk query (`sbdb_query.api`, numbered asteroids with H below `--hmax`), cached as `sbdb_cache.json`.
- Sky path: two-body Kepler propagation from the osculating elements, daily samples over the window; Earth position from low-precision Sun elements (corrected to J2000). Accuracy is a fraction of a degree, enough for a statistical screen.
- Usable star: drop of at least `--min-drop` requires `m_star <= m_ast + dm_cut` with `dm_cut = -2.5*log10(10^(0.4*min_drop) - 1)` (1.25 mag for 0.3), and the star must also be brighter than `--cam-limit`.
- Star density: analytic Gaia-like average cumulative counts per deg^2 (log-log interpolation, G 8 to 20) times a galactic-latitude factor `0.3 + 4 exp(-|b|/10)` normalized to a sky mean of 1. Approximate, for ranking only.
- Expected events per day = `density * sky motion (deg/day) * corridor width (deg)`, with corridor `= 2*max_shadow_dist + diameter` divided by the geocentric distance. Each day is weighted by the fraction of the day with the Sun below `MAX_SUN_ALT` and the asteroid above `MIN_STAR_ALT` (events then occur while the star is up), and zeroed when the central chord `D / shadow speed` is shorter than `--min-dur`.
- Score: events per year times weights: 1.5 for a diameter estimated only from H, 1.3 for condition code of 3 or more, 1.5 for NEOs (`WEIGHTS` at the top of the file).
- Outputs: ranked table, `pick_candidates.csv`, and `targets.py` (`targets` list of strings, best first, plus a `target_names` dict).
- Tested with synthetic data: galactic frame, equinox Sun longitude (J2000 frame), Kepler period, radius bounds and speed, H-G brightness, diameter formula, star-density sky mean, day/night fraction against the analytic result, and a 12,000-object run in about 5 s. The SBDB query (including the `sb-cdata` constraint syntax) has not been run against the live service.

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
| Names and SPK ids | SBDB Query API (`sbdb_query.api`), cached in `jpl_asteroids_spice.csv` (`SPICE ID` = 20000000 + number, `Full Name`, `Primary Designation`) | `get_asteroid_name`, `pyoccult_pick.py` |
| Bulk properties and orbits | SBDB Query API, `sb-kind=a`, `sb-ns=n`, fields `spkid, full_name, H, G, diameter, diameter_sigma, albedo, a, e, i, om, w, ma, epoch, condition_code, neo, class` | `pyoccult_pick.py` (cache `sbdb_cache.json`) |
| Stars | Gaia DR3 via astroquery TAP | Star positions, G magnitude |
| Path uncertainty | Horizons observer table (RSS 3-sigma position) | 3-sigma limit lines |
| Map library and tiles | Leaflet 1.9.4 (cdnjs); Carto light, Esri World Imagery, OpenStreetMap tiles | Embedded map in the report |
| Reference results | Occult (occult.exe) and OWC cloud predictions | Accuracy comparison, Part 5 |

### Config (`pyoccult_config.py`)

| Setting | Value |
|---|---|
| Search start / length / step | 2026-10-01T00:00:00, 10 days, 3600 s |
| Targets | 218001, 305580, 111287, 115181, 229912, 111286, 54653, 70141, 4272 (or `from targets import targets`, see the README) |
| `max_shadow_dist` | 200 km |
| Observer | lat 40.9541175, lon -72.92614552, 40 m |
| Star magnitude limit | 20 |
| Altitude thresholds | `MIN_STAR_ALT` 10, `MAX_SUN_ALT` -6, `ALT_MARGIN` 3 |
| Output | `hits_log.csv` |
| Optional | `map_dir` (KML folder, default `maps`), used by the report |

### Hits log columns

`target_id, target_name, best_utc, best_et, min_distance, margin_km` (distance minus radius), `r_km, r_min_km, r_max_km, r_search_km, size_source, star` (Gaia id), `mag` (G), `star_ra, star_dec, star_alt, sun_alt, m_ast, speed_kms, chord_km, duration_s, mag_drop, moon_sep_deg, moon_alt_deg, moon_illum_pct, moon_age_deg, observable, offset_east_km, offset_north_km, max_duration_s`. With the maps module: `sigma3_km, margin_in_sigma`.

---

## Part 4: Open items and unverified points

- **Star angular diameter.** Not modelled. For event 218001 OWC lists a drop of 1.56 mag and about twice our duration, against our 12.97 mag and 0.25 s. Hypothesis (unverified): the star's angular size is comparable to the shadow, which reduces the drop and stretches the event. Proposed: Gaia `radius_gspphot` and `distance_gspphot` (angle in mas about 9.305 * R / d_pc), a partial-coverage drop, and a flag when the star diameter exceeds about 30% of the shadow.
- Regression test using the OWC list as fixtures (time within 10 s, drop within 0.25 mag, duration within 10%, 218001 marked as a known gap): offered, not built.
- Optional `m_before` and `m_during` columns in the log: offered.
- `pyoccult_paths.py` has not been run against real SPICE and Horizons; the Horizons RSS 3-sigma and `delta` column names are written from memory.
- `pyoccult_pick.py` has not been run against the live SBDB API; the `sb-cdata` constraint syntax is from memory. The star-density model is analytic, and the Keplerian paths ignore planetary perturbations.
- The report's embedded map was tested only against a Leaflet stand-in in a headless browser, and the Carto and Esri basemaps have not been tried from `file://`. It works through nginx.
- Suggested fixes in your own code whose status I do not know (apply if not yet done):
  - `target_test` record had literal `...` placeholders for `r_min_km`, `r_max_km`, `source`, which become `Ellipsis` in the CSV: use `size['r_min_km']` and `size['r_max_km']`, and drop `source`.
  - `star_test` uses `if not observable(...)`, but `observable` returns a tuple (always truthy): use `observable(...)[0]`.
  - `screen_stars` margin does not yet include `max_shadow_dist`.
  - `gaia_cone` uses `launch_job` (synchronous, possibly capped at about 2000 rows; unverified), queries `radius_arcmin` without the `+5` tile padding its comment mentions, and returns `None` on failure (the caller then crashes on `.copy()`).
  - The ADQL string has an inline `--` comment.
  - Unverified: SBDB `phys_par` field names, and the Earth-PCK body id (3000) for `pckcov`.

---

## Part 5: Validation against OWC and Occult

Compared against the OWC list you gave as reference data (OWC uses occult.exe):

- Star magnitude, altitude, compass direction and Moon distance agree.
- Event times agree within 9 s.
- Maximum durations agree within about +/-8%.
- 218001 is the outlier (drop and duration, see Part 4).
- Moon, shadow-path and magnitude-drop outputs have so far been compared only through this list; a systematic comparison has not been done.




## Optimazation Potentials

Your four ideas are all reasonable, but I'd reorder them. One of them also points at a possible correctness problem. These numbers come from reading your code and from estimates, not from profiling a run.

Check first: possible silent truncation at MAG_MIN = 20. A 10′ cone is about 0.09 deg², and at G ≤ 20 that holds thousands of stars, more near the Milky Way. If the synchronous Gaia.launch_job is capped at about 2000 rows (I flagged that as unverified earlier), dense cones lose stars without any error. Print len(df) after the query and warn if it is exactly 2000. If it is, switch to launch_job_async.

Your four ideas

D, a smaller cone: yes, but the 5′ tile snapping limits it. Your cone is centred on the tile centre, not the asteroid, so it needs about 3.5′ of slack. The asteroid moves only 0.6–1.3′ per window, and the Earth-reach corridor is about ±0.05–0.13′ wide. Shrinking the cone means shrinking the tiles too, which gives you more queries, not fewer.

C, the Gaia query: this is where the large gain is. Over 20 days an asteroid sweeps a path a few degrees long. The corridor that matters is under 0.5′ wide, but today you query about 200 overlapping 10′ cones per asteroid. That is hundreds of thousands of rows, or tens of millions across 100 asteroids, to keep a few thousand. The fix is one query per asteroid per run: a thin strip polygon along the 20-day path (or a few ≤1° segments), padded by about 1′ because the cone centre is the apparent position (LT+S) while the prescreen uses CN. This also makes the cache per asteroid and date range, so the tile logic goes away.

B, longer windows: a small gain, and the star field isn't the limit. Stars are propagated to the window centre, so the leftover error is proper motion × the time offset. For a 1″/yr star and a 3 h window that is about 0.2 mas, roughly 0.3 km at the asteroid. Even a full day stays under about 5 km for all but the highest-proper-motion stars. The real limits are the cone coverage and having one minimum per star, which holds for a shadow faster than the observer's roughly 0.35 km/s ground speed and so fails only near stationary points. Your 10 min overlap is also more than needed, since the is_new_hit dedupe already handles repeats. I'd treat B as a stepping stone to the restructure below.

A, parallel by target: yes, as a last step. It scales almost linearly for the CPU part, but a few things need handling:

Use processes, not threads, because SPICE isn't thread-safe. Each worker loads its own kernels.
Do the kernel checks, the Horizons SPK fetches and the Gaia queries once in the parent, so workers do no network work (the archives throttle concurrent users).
Write cache files atomically (temp file plus os.replace) and have workers return records so the parent writes hits_log.csv.
Your _seen dedupe is per target, so splitting by target keeps it correct.
Two free reductions
Cap the Gaia magnitude per target. Your code drops events with mag_drop < 0.1, which requires the star to be no fainter than m_ast + 2.5. A 15.5-mag asteroid therefore never needs G > 18, and for a 14-mag one G ≤ 16.5 is enough. Query min(MAG_MIN, m_ast_max + 2.5). Taking G ≤ 20 down to about 17 cuts rows by roughly 4×.
Propagate only the survivors. Run screen_stars on the raw J2016 positions with about 30″ of padding, then run apply_space_motion only on those few. Right now every window propagates the whole cone.
The restructure I'd suggest

For each asteroid, make one pass over the whole run:

Compute the path vectorized at about 10 min steps.
Do one strip query.
Scan every star's plane distance over the whole interval at once and find the local minima below the margin.
Refine each candidate with minimize_scalar in a ±10 min bracket, then apply the existing observable and metric code.

That replaces about 480 window iterations per asteroid with one vector operation and one query. It makes B, C and D moot, and A becomes a simple per-target split.

Before any of this, run python -m cProfile -s cumtime pyoccult.py | head -30 on 2 targets and 1 day. The split between Gaia, apply_space_motion and star_test decides how much each step matters.

Want me to write the per-asteroid version as a drop-in alternative to your driver loop, starting with the strip query and the vectorized scan?