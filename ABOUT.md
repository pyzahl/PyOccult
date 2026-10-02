# PyOccult: computation reference

How PyOccult computes its predictions, where its data comes from, how it was validated and what is still under active development.
Currently Gaia and Horizons are used.
Usage is in `README.md`. Updated 2026-10-01.

PyOccult is intended as a future and portable Python replacement for the Windows occultation predictor Occult (occult.exe, the engine behind
Occult Watcher Cloud, OWC). It finds asteroid occultations of Gaia stars for one observer site.

---

## Part 1: The tools and how they fit together

| Step | Tool | What it does |
|---|---|---|
| once | `pyoccult_setup.py` | downloads the SPICE kernels, builds the local Gaia catalog and the bright-star index |
| choose | `pyoccult_pick.py` | screens all asteroids for actual events at the site in a window, writes `targets.py` |
| predict | `pyoccult.py` | computes the events of the target asteroids exactly, appends them to `hits_log.csv`, writes KML maps |
| present | `pyoccult_report.py` | turns `hits_log.csv` into an HTML or Markdown event list with an embedded map |
| operate | `pyoccult_gui.py` | local web interface (NiceGUI): sites on a map, runs, live log, results |
| check | `pyoccult_owc_check.py` | reruns an OWC search result you saved (`owc_reference.txt`, private) and compares event by event |

Supporting modules: `pyoccult_corridor.py` (per-asteroid star corridor and candidate scan), `pyoccult_gaia_local.py`
(local Gaia catalog and bright-star index), `pyoccult_screen.py` (the pick tool's event screen),
`pyoccult_orbits.py` (fast orbit integration), `pyoccult_paths.py` (shadow ground track), `pyoccult_sbdb.py` (shared
asteroid size cache), `pyoccult_kernels.py` (kernel download).

---

## Part 2: The prediction (`pyoccult.py`)

### 2.1 Pipeline (corridor mode, the default)

1. Kernels are checked and loaded at start-up (`pyoccult_kernels.py`). The local Gaia catalog is opened before any
   other work; a missing or incomplete catalog stops the run.
2. Pass 1, per target: size, H and G (`get_asteroid_size`, 2.8), the asteroid's orbit file from JPL Horizons
   (`fetch_target_orbit`), and a corridor plan (`pyoccult_corridor.plan_corridor`): the astrometric path every
   `corridor_step_s` over the whole run, the strip half-width and the star magnitude cap (2.3).
3. Pass 2, per target: stars in the strip from the local catalog (2.4), all star/time pairs scanned at once for
   closest approaches to the Earth's centre (2.5), then each candidate solved exactly for the site (2.6) and checked
   (2.7). Hits are appended to `hits_log.csv`; a KML ground track is written for hits close enough to matter (2.10).

The old `"windows"` mode (`search_mode = "windows"`) queries the Gaia archive per hourly window instead. It is kept for
comparison; it shares the per-star solve and checks (`handle_star`).

### 2.2 Fundamental (Besselian) plane: `besselian_offsets`

- Axes in J2000: **z** = unit vector to the star; **x** = (0,0,1) × z, normalised (east); **y** = z × x (north).
- Asteroid: `spkpos(target, et, 'J2000', 'CN', '399')`. 399 is the Earth's centre (3 would be the Earth-Moon
  barycentre). `CN` is converged light time without stellar aberration: astrometric, like Gaia positions.
- Observer: `georec(lon, lat, alt_km, a, f)` with the Earth radii from the kernel, rotated ITRF93 to J2000 with
  `pxform('ITRF93', 'J2000', et)`. Longitude east-positive, geodetic, radians.
- Offsets `(dx, dy)` = the first two components of `M @ (r_asteroid - r_observer)`, km east and north. Miss distance =
  `hypot(dx, dy)`.

### 2.3 Star magnitude cap and corridor width: `plan_corridor`

- A drop of at least `d` needs the star no fainter than `m_ast + 2.5*log10(1/(10^(0.4 d) - 1))`: 2.54 mag for 0.1.
  The cap is `min(MAG_MIN, faintest m_ast in the run + that + 0.5)`. A 15.5 mag asteroid never needs stars past ~18.5.
- Strip half-width per path sample: `margin_km / distance + pad`, with `margin_km = Earth radius + r_max + max_shadow_dist`
  (the observer can be anywhere on the Earth's disc) and a proper-motion pad for stars up to 1500 mas/yr over the time
  since Gaia's epoch 2016.0. Faster stars are added from an all-sky list kept with the catalog.

### 2.4 Local Gaia catalog: `pyoccult_gaia_local.py`

- Built from ESA's bulk Gaia DR3 `gaia_source` files (3386 gzipped CSV files, 753 GB, streamed and not kept). Kept:
  G <= `gaia_local_gmax` (18), 5-parameter astrometry, RUWE < 1.4; columns `source_id, ra, dec, parallax, pmra, pmdec,
  phot_g_mean_mag` as binary. Result for G <= 18: 280.3 M of 1811.7 M stars, 11.2 GB, 101 min at ~1.4 Gbit/s.
- One `.npy` per source file (written last, atomically: its presence marks the file done, so the build resumes), a list
  of the 1 x 1 deg sky cells each file covers (the lookup index; no HEALPix library needed), and its stars faster than
  1500 mas/yr.
- Lookup for a corridor: the cells the strip touches (probed densely enough that no cell is skipped, whole dec bands
  near a pole), then coarse discs along the path (0.05 deg chunks), a superset that the candidate scan narrows down.
  About 1 s per asteroid (2 s in the Galactic bulge).
- Why local: the Gaia archive took 12-14 min per strip query (or never answered) in October 2026 and warns it is
  unstable while DR4 is prepared.

### 2.5 Candidate scan: `find_candidates`

- Stars are moved linearly by proper motion to the middle of the run. The plane distance of every star to every path
  sample is `chord x distance`; local minima below the margin (widened by half a step of motion) are kept.
- Each minimum is refined by quadratic interpolation of the path, giving an estimated time and Earth-centre miss.

### 2.6 Exact closest approach: `star_test`

- `minimize_scalar(method='bounded')` over a time interval around the estimate, solving for the **offset from the
  interval centre**, not the absolute time. The bounded solver's tolerance is `sqrt(eps)*|x| + xatol/3`; with the raw
  ephemeris time (~8.4e8 s) that was ~12 s, i.e. tens of km of miss distance (fixed 2026-10-01; earlier results were
  off by up to ~9 s and ~90 km, median 6 km).
- Interval width (`corridor.solver_bracket_s`): the scan estimates the Earth-centre closest approach, but the observer
  is up to `margin_km` from the centre in the plane, so the local closest approach can be `margin / speed` away
  (10-20 min). Width = 2 x clip(1.3 margin / speed, one path step, 2 h).
- The star is propagated to the event with astropy `apply_space_motion` (distance = 1000/parallax pc, parallax floored
  at 0.01 mas).

### 2.7 Checks before logging: `handle_star`

- Rejected if the minimum lies within 1 s of the interval edge (not a real minimum), outside the run, already logged
  (same asteroid and star within 300 s), not observable (star altitude < `MIN_STAR_ALT` or Sun above `MAX_SUN_ALT`), or
  the drop is below `min_mag_drop`.
- Logged if `min_distance < r_max + max_shadow_dist`; `observable` says "yes" inside `r_max`, "yes, in search range"
  outside it.

### 2.8 Asteroid size: `get_asteroid_size`

Order of precedence:
1. `SIZE_OVERRIDES` (curated values, e.g. from occultation chords or shape models).
2. SBDB `diameter` with its sigma (15 % if missing); bounds +/-3 sigma, widened by the tri-axial `extent`.
3. H plus SBDB albedo `p`.
4. H only, albedo 0.14 (bounds from albedo 0.30 and 0.05).

`D = 1329 / sqrt(p) * 10^(-H/5)` km. `r_min_km` is clamped at 0. The bounds describe size uncertainty only, not orbit
uncertainty. No diameter and no H gives no size (the target is skipped).

The raw SBDB data is cached per asteroid in `<cache_path>/PyOccult_sbdb_phys.json` (`pyoccult_sbdb.py`), refreshed
after `sbdb_max_age_days`; the pick tool fills it for its targets from its bulk download.

### 2.9 Event metrics: `event_metrics`, `apparent_mag_HG`, `moon_info`

- Shadow speed relative to the observer: finite difference of `(dx, dy)` over +/-1 s.
- Chord `2*sqrt(max(r^2 - b^2, 0))` for impact parameter `b`; duration = chord / speed (0 outside the shadow).
  `max_duration_s = 2r / speed` (centre line).
- Asteroid magnitude (H, G system): `V = H + 5 log10(r Delta) - 2.5 log10((1-G) Phi1 + G Phi2)`,
  `Phi1 = exp(-3.33 tan(a/2)^0.63)`, `Phi2 = exp(-1.87 tan(a/2)^1.22)`, `a` = phase angle at the asteroid; G = 0.15
  if unknown. Good to about +/-0.3 mag plus the lightcurve amplitude.
- Drop (star fully covered): `mag_drop = 2.5 log10(1 + 10^(0.4 (m_ast - m_star)))` = `m_ast - m_before`, the change in
  combined brightness (as OWC lists it); never smaller than `m_ast - m_star`. Star magnitude is Gaia G; OWC's star
  column shows the same G values.
- Moon: topocentric separation from the star, altitude, illumination `(1 + cos a)/2`, phase age (ecliptic longitude
  Moon minus Sun).
- `offset_east_km`, `offset_north_km`: shadow axis minus observer on the plane, i.e. how to move to the centre line.
- Observability (logged, not filtered): `airmass` (Kasten & Young), `extinction_mag` = extinction x (airmass - 1), and
  `mag_margin` = OWC limit (3.3, upper size bound) - star magnitude - extinction.
- Run statistics: `calc_s` per hit (from the candidate's start to the logged record, without the map); per run a
  summary (start-up, asteroid data loading = pass 1, search = pass 2, maps, per asteroid, per exact solve, counts,
  site, equipment, limits) printed and appended to `<hits log>.runs.jsonl` for the report header.

### 2.10 Shadow ground track: `pyoccult_paths.py`

- About 1.3 Earth radii of track on each side of the event, ~100 km per step. Five lines: centre, the shadow limits
  (+/-r) and the 3-sigma limits (+/-(r + 3 sigma)); each plane point is projected onto the Earth ellipsoid
  (`surfpt`; a miss raises `NotFoundError` and the point is skipped), with the centre-line duration at each point.
- 3 sigma: the JPL Horizons RSS 3-sigma position uncertainty times the distance, else `default_sigma3_km`.
- KML for Google Earth or Google My Maps; written when the miss distance is below `r + 3 sigma`.

### 2.11 Event preview: `pyoccult_preview.py`

- For every hit, an SVG next to its KML: the local-catalog stars (to `preview_mag_limit`) in a field
  `preview_field_factor` times the camera field (at least 10′), moved linearly by proper motion to the event date;
  gnomonic projection around the target star, north up and east left (as on the sky; a telescope may flip it).
- Camera field `2 atan(sensor / 2 focal)` from the site's `focal_mm` and `sensor_mm`; asteroid track from the SPK
  (`CN`, geocentric) over a span chosen so it covers about a quarter of the field (30 min to 12 h each side).

---

## Part 3: Choosing targets (`pyoccult_pick.py`)

An OWC-style event search over all asteroids (numbered, H < `pick_hmax`, or all with `--all`) for a window, at the site.

### 3.1 Orbits: `pyoccult_orbits.py`

- SBDB bulk query with **full-precision** elements (`full-prec=true`). The default output is rounded (e.g. `a = 2.766`),
  which alone gave ~40" errors.
- Heliocentric ecliptic J2000 elements to an equatorial state, then integrated barycentrically with the Sun and the
  planet-system barycentres from DE440 (Earth-Moon as one body), RK4 with half-day steps, quintic Hermite interpolation
  between steps, one-step light-time correction (astrometric, as `CN`).
- Against the JPL Horizons orbit files of 102 asteroids over 21 days: worst 0.01", median 2 km. 102 asteroids in 0.2 s.
  Not for close Earth approaches (no Moon separately, fixed step).

### 3.2 The screen: `pyoccult_screen.py`

Per chunk of asteroids, positions every 600 s over the window, then per asteroid:
1. Only samples when the asteroid is above `MIN_STAR_ALT - 3` at the site and the Sun below `MAX_SUN_ALT` (both from the
   site) are searched.
2. The faintest useful star follows from the drop rule (2.3) and the observability rule (3.3), so small or fast asteroids
   search only bright stars.
3. Stars along the visible path from the bright-star index (3.4), then the candidate scan (2.5).
4. Each candidate is solved for the site: Newton iteration on the plane offset of the shadow axis from the observer on
   the rotating Earth (asteroid positions by cubic interpolation, observer from `pxform`), within the bracket of 2.6.
5. Kept if the miss is below `r_max + reach`, the star is high enough and the Sun low enough at that time, and the
   detection rules pass.

Against `pyoccult.py` on the same events: same stars, times within 5 s, the same drops and durations.
Stars are moved linearly by proper motion (no parallax), and stars faster than 1500 mas/yr are not searched.

### 3.3 Detection rule

OWC's General Observability Criterion (video recording, aperture and detection frames): an event is observable if
`StarMag < 5 log10(aperture_cm) + 2.5 log10(MaxDuration / frames) + 8.5 + MagAdjust`. With extinction enabled (site
key `extinction`, mag per airmass), the star counts as fainter by `extinction x (airmass - 1)` at its altitude (Kasten &
Young airmass). Hard limits: `min_dur_s` and `min_mag_drop`; OWC also found the drop itself has no significant effect.
All OWC reference events pass at 25 cm, 4 frames, MagAdjust 0 (and some would not if the aperture were in inches).
The site's star limit `MAG_MIN` is the magnitude that passes at the longest usable exposure `max_exp_s` (0.64 s gives
G 15.0 at 25 cm, as in the OWC search). For sizes estimated from H (uncertain by ~1.7x) the duration test uses the
upper size bound, so an event is kept if it *can* be observable; the reported duration is nominal. `mag_margin`
reports how far below the limit the star is.

### 3.4 Bright-star index: `BrightIndex`

All catalog stars with G <= 15 (32.4 M, 1.3 GB), sorted by a 0.25 deg sky cell and, within a cell, by magnitude, so a
lookup with a bright cap reads only the bright end of each cell. Built once from the catalog (~30 s), opened
memory-mapped. A lookup takes 5-50 ms.

### 3.5 Speed and output

465k asteroids (H < 17) over 8 days: 875 s in one process, 318 s with 4 worker processes (each loads its own SPICE
kernels). Output: `pick_events.csv`, a ranked table (brightest star first by default) and `targets.py` with the
asteroids of the best events; their size data goes to the shared size cache.

---

## Part 4: Data sources

| Item | Source | Used for |
|---|---|---|
| `naif0012.tls`, `pck00010.tpc`, `de440.bsp` | NAIF generic kernels | leap seconds, Earth radii, Sun/Moon/planets |
| `earth_latest_high_prec.bpc` | NAIF generic kernels | ITRF93 Earth orientation, refreshed after `earth_pck_max_age` days |
| Asteroid orbit files | JPL Horizons API (`EPHEM_TYPE=SPK`), cached in `cache_path` | `pyoccult.py` positions |
| Asteroid size, H, G | SBDB API (`sbdb.api`, `phys-par=1`), cached per asteroid | `get_asteroid_size` |
| Elements, sizes for all asteroids | SBDB Query API (`sbdb_query.api`, numbered, full precision), cached | `pyoccult_pick.py` |
| Asteroid names | SBDB full name, from the same per-asteroid cache as the size | `get_asteroid_name` |
| Stars | Gaia DR3 bulk files, `cdn.gea.esac.esa.int/Gaia/gdr3/gaia_source/` | local catalog |
| Path uncertainty | Horizons observer table, RSS 3-sigma position | 3-sigma map lines |
| Map | Leaflet 1.9.4 (cdnjs); OpenStreetMap tiles (`--tile-url` for others) | report |
| Reference | Occult / OWC search results, pasted as text into `owc_reference.txt` (private, not in git) | validation |

---

## Part 5: Validation

- **OWC reference** (`python pyoccult_owc_check.py`; 16 events at the observer's site, Oct 2-9 2026, 20 km reach,
  G <= 15, 25 cm, 4 frames): all 16 found with the same stars; times within 5.4 s (13 within 3 s). Drops agree within 0.25 mag below 5 mag (above
  that both are total and differ only by the asteroid's estimated brightness). Durations agree within 10 % wherever
  both use the same diameter; 4 events differ only by diameter (sizes from H, or OWC using another source than
  NEOWISE). 218001 is the open case (Part 6).
- **Corridor vs the old windows search** (23 asteroids, 20 days, 200 km reach): all 40 old hits with G <= 18 found,
  within 1.4 ms and 0.8 m (after the solver fix); 10 more real hits. The other old hits were on stars fainter than the
  catalog's G 18.
- **Pick screen** (blind, 465k asteroids): all 13 OWC reference events with H < 17 among its 39 events; the 14th
  (819762, H 18.45) with `--all`.
- **Orbits**: 102 asteroids against JPL Horizons, worst 0.01" (3.1).
- **Tests** (`python tests/<name>.py`, stand-ins for SPICE, astropy and the network): corridor and loop recall, local
  catalog build and lookup, solver convergence at realistic ephemeris times, size cache, pick tool, paths.

---

## Part 6: Open items

- **218001**: OWC lists a 1.56 mag drop and 0.51 s, PyOccult 12.97 mag and 0.25 s. The duration difference is the
  diameter (OWC 3.56 km, PyOccult 1.77 km from H). The drop is unexplained; hypothesis (unverified): the 5.6 mag star's
  angular diameter is comparable to the shadow, making the event partial. Idea: Gaia `radius_gspphot` and
  `distance_gspphot` (angle in mas ~ 9.305 R / d_pc), a partial-coverage drop, and a flag when the star is larger than
  about 30 % of the shadow.
- **Stellar parallax** is not applied to the star direction (`geocentric_star_dir` exists but is not called). Up to
  ~15 km on the plane for a 10 mas star at 2 AU; matters for nearby (often bright) stars.
- **`star_test`'s `observable` text column**: `if not observable(...)` tests a tuple (always true), so the text never
  says "no". Harmless today, because `handle_star` rejects unobservable events with `observable(...)[0]`.
- **Unverified**: the Horizons RSS 3-sigma column names in `pyoccult_paths.py` (falls back to `default_sigma3_km`), and
  the Earth-PCK body id 3000 used for the coverage message at start-up.
- **Report**: the map uses OpenStreetMap tiles, which need the page served by a web server (a `file://` page sends no
  Referer, so the tiles are refused); `--tile-url` selects another tile server.
- **Ideas**: `m_before` / `m_during` columns in the log; process-level parallelism by target in `pyoccult.py`.

---

## Part 7: Future plans

### Major solar-system bodies as targets (not started)

Can the Moon, the planets and the major moons be targets, as an option? Partly: the Moon is close to straightforward,
planets and their moons are doable but each needs a few real additions.

**What already fits.** The solver is the standard fundamental-plane method, which works for any occulting body: a star,
a body position from SPICE and a radius. The corridor scan, the local Gaia catalog, the visibility checks, metrics,
maps and the report do not care what the occulting body is.

| Body | Orbit data | Effort and caveats |
|---|---|---|
| **Moon** | already in `de440.bsp` | Small: SPICE knows "MOON", its radius is in the kernels. Lunar occultations are IOTA's most common events. Caveats: hundreds of events per month at G <= 10 (needs its own magnitude limit); grazes need the lunar limb profile, which we do not have; bright-limb and daylight events need filtering. |
| **Planets** (Mars to Neptune) and **Pluto** | `de440` has only the barycentres; planet centres come from NAIF's satellite kernels (mar097, jup365, sat441, ura111, nep097, plu058; tens of MB up to about 1 GB for Jupiter; sizes unverified) | Medium: download these kernels as an option in setup. The giant planets are flattened (Jupiter ~7 %), so the shadow edge should come from the real limb ellipse (SPICE `edlimb`), not a circle. Rings and atmospheres (gradual drops, central flashes) are not modelled. The planet's glare limits detection, so the drop and observability rules need care. |
| **Major moons** (Galilean moons, Titan, Triton, Charon, ...) | the same satellite kernels | Like asteroids once the kernels are there: nearly spherical, radii from the kernels. They need a brightness table (their H is not in SBDB) for the drop, and handling of the nearby planet's glare. |

**Target names.** Asteroids are plain numbers, and NAIF moon ids collide with them (Io is 501, so is asteroid (501)).
Major bodies would be given by name in `targets`, e.g. `["218001", "Moon", "Io", "Titan"]`; SPICE resolves the names.

**Suggested order.**
1. The Moon as an optional target: about half a day; no new data; many events to cross-check against Occult.
2. Planets and major moons by name: optional kernel downloads in setup, ellipsoid limbs, a brightness table; a day or
   two, with clear caveats about rings, atmospheres and glare.

The pick tool would not need to change: there are only a handful of major bodies, so they would simply be listed as
targets.
