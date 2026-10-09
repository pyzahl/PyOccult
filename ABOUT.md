# PyOccult: computation reference

How PyOccult computes its predictions, where its data comes from, how it was validated ([VERIFICATION.md](VERIFICATION.md)) and what is still under active development.
Data comes from Gaia DR3 (stars), JPL Horizons and SBDB (asteroid orbits and sizes) and NAIF SPICE kernels
(planets, Earth orientation); see Part 4. Usage is in `README.md`; to contribute, see `CONTRIBUTING.md`.
Updated 2026-10-08.

PyOccult is intended as a future and portable Python replacement for the Windows occultation predictor Occult (occult.exe, the engine behind
Occult Watcher Cloud, OWC). It finds asteroid occultations of Gaia stars for one observer site.

---

## Contents

- [Part 1: The tools and how they fit together](#part-1-the-tools-and-how-they-fit-together)
- [Part 2: The prediction (pyoccult/search.py)](#part-2-the-prediction-pyoccultsearchpy)
  - [2.1 Pipeline (corridor mode, the default)](#21-pipeline-corridor-mode-the-default)
  - [2.2 Fundamental (Besselian) plane: besselian_offsets](#22-fundamental-besselian-plane-besselian_offsets)
  - [2.3 Star magnitude cap and corridor width: plan_corridor](#23-star-magnitude-cap-and-corridor-width-plan_corridor)
  - [2.4 Local Gaia catalog: pyoccult/gaia_local.py](#24-local-gaia-catalog-pyoccultgaia_localpy)
  - [2.5 Candidate scan: find_candidates](#25-candidate-scan-find_candidates)
  - [2.6 Exact closest approach: star_test](#26-exact-closest-approach-star_test)
  - [2.7 Checks before logging: handle_star](#27-checks-before-logging-handle_star)
  - [2.8 Asteroid size: get_asteroid_size](#28-asteroid-size-get_asteroid_size)
  - [2.9 Event metrics: event_metrics, apparent_mag_HG, moon_info](#29-event-metrics-event_metrics-apparent_mag_hg-moon_info)
  - [2.10 Shadow ground track: pyoccult/paths.py](#210-shadow-ground-track-pyoccultpathspy)
  - [2.11 Event preview: pyoccult/preview.py](#211-event-preview-pyoccultpreviewpy)
  - [2.12 Globe plot: pyoccult/globe.py (0.11.0)](#212-globe-plot-pyoccultglobepy-0110)
- [Part 3: Choosing targets (pyoccult/pick.py)](#part-3-choosing-targets-pyoccultpickpy)
  - [3.1 Orbits: pyoccult/orbits.py](#31-orbits-pyoccultorbitspy)
  - [3.2 The screen: pyoccult/screen.py](#32-the-screen-pyoccultscreenpy)
  - [3.3 Detection rule](#33-detection-rule)
  - [3.4 Bright-star index: BrightIndex](#34-bright-star-index-brightindex)
  - [3.5 Speed and output](#35-speed-and-output)
  - [3.6 Saved picks: pyoccult/picks.py](#36-saved-picks-pyoccultpickspy)
- [Part 4: Data sources](#part-4-data-sources)
  - [4.1 Sizes: what Horizons/SBDB has, and what occultations measured](#41-sizes-what-horizonssbdb-has-and-what-occultations-measured)
  - [4.2 Asteroid satellites](#42-asteroid-satellites)
- [Part 5: Validation](#part-5-validation) (summary; all checks in [VERIFICATION.md](VERIFICATION.md))
- [Part 6: Open items](#part-6-open-items)
  - [Gravitational light deflection and stellar parallax (built in 0.10.0, 2026-10-04)](#gravitational-light-deflection-and-stellar-parallax-built-in-0100-2026-10-04)
- [Part 7: Future plans](#part-7-future-plans)
  - [Major solar-system bodies as targets (planets and moons built in 0.14.0; Earth's Moon open)](#major-solar-system-bodies-as-targets-planets-and-moons-built-in-0140-earths-moon-open)

---

## Part 1: The tools and how they fit together

| Step | Tool | What it does |
|---|---|---|
| once | `pyoccult/setup.py` | downloads the SPICE kernels, installs the local Gaia catalog (ready-made from Zenodo, or built from ESA's files) and builds the bright-star index |
| choose | `pyoccult/pick.py` | screens all asteroids for actual events at the site in a window, writes `targets.py` and saves the pick per site and window in `picks/` |
| predict | `pyoccult/search.py` | computes the events of the target asteroids exactly, appends them to `hits_log.csv`, writes KML maps |
| present | `pyoccult/report.py` | turns `hits_log.csv` into an HTML or Markdown event list with an embedded map |
| operate | `pyoccult/gui.py` | local web interface (NiceGUI): sites on a map, runs, live log, results |
| check | `pyoccult/owc_check.py` | reruns an OWC search result you saved (`owc_reference.txt`, private) and compares event by event |

Supporting modules: `pyoccult/corridor.py` (per-asteroid star corridor and candidate scan), `pyoccult/gaia_local.py`
(local Gaia catalog and bright-star index), `pyoccult/screen.py` (the pick tool's event screen),
`pyoccult/orbits.py` (fast orbit integration), `pyoccult/paths.py` (shadow ground track), `pyoccult/sbdb.py` (shared
asteroid size cache), `pyoccult/kernels.py` (kernel download, Earth orientation coverage), `pyoccult/picks.py` (saved
picks: which one a search uses), `pyoccult/kstars.py` (points KStars at an event over D-Bus, Linux), `pyoccult/favorites.py` (starred events with their
own copies of map and preview).

---

## Part 2: The prediction (`pyoccult/search.py`)

### 2.1 Pipeline (corridor mode, the default)

1. Kernels are checked and loaded at start-up (`pyoccult/kernels.py`). The local Gaia catalog is opened before any
   other work; a missing or incomplete catalog stops the run.
2. Pass 1, per target: size, H and G (`get_asteroid_size`, 2.8), the asteroid's orbit file from JPL Horizons
   (`fetch_target_orbit`), and a corridor plan (`pyoccult.corridor.plan_corridor`): the astrometric path every
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

### 2.4 Local Gaia catalog: `pyoccult/gaia_local.py`

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
- Ready-made copies for G <= 16 and G <= 18 (the same files a build writes, without the bright-star index) are on
  Zenodo, [doi:10.5281/zenodo.23113337](https://doi.org/10.5281/zenodo.23113337) (CC BY-NC 4.0, the terms of the Gaia data it contains): `gaia_dr3_g16.tar.xz`
  (2.1 GB) and `gaia_dr3_g18.tar.xz` (8.2 GB), each with a `.sha256`. `fetch_zenodo` downloads one (resumable), checks
  the SHA-256 and unpacks it into any folder name; `pyoccult/setup.py` offers it before the ESA build.

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
4. H only, albedo 0.14 (bounds from albedo 0.30 and 0.05). The tables mark these asteroids with "*": the diameter
   is uncertain by a factor of about 1.7 (sqrt(0.30/0.14), sqrt(0.14/0.05)).

`D = 1329 / sqrt(p) * 10^(-H/5)` km. `r_min_km` is clamped at 0. The bounds describe size uncertainty only, not orbit
uncertainty. No diameter and no H gives no size (the target is skipped).

The raw SBDB data is cached per asteroid in `<cache_path>/PyOccult_sbdb_phys.json` (`pyoccult/sbdb.py`), refreshed
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

### 2.10 Shadow ground track: `pyoccult/paths.py`

- About 1.3 Earth radii of track on each side of the event, ~100 km per step. Seven lines: centre, the shadow limits
  (+/-r), the 1-sigma limits (+/-(r + sigma)) and the 3-sigma limits (+/-(r + 3 sigma)); each plane point is projected onto the Earth ellipsoid
  (`surfpt`; a miss raises `NotFoundError` and the point is skipped), with the centre-line duration at each point.
- The 1- and 3-sigma lines describe the uncertainty of the asteroid's **position** (orbit), not of its size: the
  size enters only through r (the red shadow limits use the best radius); its uncertainty (r_min .. r_max) sets the
  search range and is not drawn.
- Sigma: `path_sigma3_km` asks JPL Horizons for the plane-of-sky 3-sigma position uncertainty at the event
  (`RSS_3sigma`, arcsec) and converts it to km at the asteroid's distance; sigma = that / 3. Without a Horizons
  covariance it uses `default_sigma3_km` (10 km, so sigma 3.3 km). Only the orbit counts: the star's position error is
  not added. Gaia DR3 positions carried from 2016 to 2026 with their proper-motion errors are good to about 1 mas
  for bright stars (~1 km at 1.2 AU) and several mas for faint ones (G 17-18: several km), so for faint stars the
  real band is wider than drawn.
- RSS is the size of the whole error ellipse, dominated by its long axis. What moves the path on the ground is the
  part across the track; the part along the track only shifts the time. So the 1- and 3-sigma lines are as wide as
  the long axis whichever way it points: right when the long axis lies across the track, too wide when it lies along
  it. Example, 172559 on 2026-10-19 (1.21 AU): long axis 0.03" (3 sigma) at position angle -4 deg, short axis 0.004",
  track to the east-north-east, so the long axis lies nearly across the track and sigma ~9 km is the real cross-track
  value there (3 sigma 26 km).
- Occult/OWC draw the same kind of diagram (shadow, then the 1-sigma band, then 2- and 3-sigma lines), but take the
  uncertainty from their own orbit data, not from Horizons, so their band can be narrower or wider than ours for the
  same event (e.g. an OWC event with a 9 km shadow and a 1-sigma band of ~2 km on each side).
- KML for Google Earth or Google My Maps; written for every logged event, i.e. when the miss distance is below
  `r_max + max_shadow_dist` (the shadow plus the distance you can travel), also when the site lies outside the
  3-sigma band: then the map shows where to go.

### 2.11 Event preview: `pyoccult/preview.py`

- For every hit, an SVG next to its KML: the local-catalog stars (to `preview_mag_limit`) in a field
  `preview_field_factor` times the camera field (at least 10′), moved linearly by proper motion to the event date;
  gnomonic projection around the target star, north up and east left (as on the sky; a telescope may flip it).
- Camera field `2 atan(sensor / 2 focal)` from the site's `focal_mm` and `sensor_mm`; asteroid track from the SPK
  (`CN`, geocentric) over a span chosen so it covers about a quarter of the field (30 min to 12 h each side).

### 2.12 Globe plot: `pyoccult/globe.py` (0.11.0)

- The whole Earth as seen from the star at the event time (orthographic, east right, north up), as on Occult's
  plot: the shadow path from `shadow_path` (centre line, shadow limits, 1- and 3-sigma limits) with dots and labels
  at whole minutes, the shadow axis beyond the Earth (fundamental plane, dashed, minute ticks), the site, and either
  sea, land and the night side (`globe_style = "color"`, like OWC's globe) or a line drawing with the day side
  (`"lines"`). Land is drawn with an extended orthographic projection (r = sin c on the visible side, 2 - sin c
  beyond the limb) clipped to the disk; a land mass containing the far-side point is filled as the outside of its
  outline (detected by its orientation).
- Header with Occult's parameter set: star (Gaia id, G, RA/Dec as used and of date via astropy TETE, the applied
  parallax and deflection), maximum duration, time per km and per mas, drop, Sun and Moon distance and Moon
  illumination, 1-sigma error (Horizons RSS, in km and mas), asteroid magnitude, diameter (range, mas), horizontal
  parallax, hourly motion in RA (s) and Dec ("), distance. Inset: 2 deg chart to star G + 1.5 with the asteroid's
  motion in 24 h steps.
- Checked on 30819 (Oct 11 2026) against Occult's plot: star position, asteroid parallax 8.227" (equal), hourly
  motion -2.083 s / -28.67" (Occult -2.087 s / -28.62"), 1 km and 1 mas times, diameter, Sun and Moon all agree;
  the path crosses the same countries at the same minutes.
- Coastlines, borders and land: `data/ne_110m_earth.json` (Natural Earth 1:110m, public domain, 166 KB).

---

## Part 3: Choosing targets (`pyoccult/pick.py`)

An OWC-style event search over all asteroids (numbered, H < `pick_hmax`, or all with `--all`) for a window, at the site.

### 3.1 Orbits: `pyoccult/orbits.py`

- SBDB bulk query with **full-precision** elements (`full-prec=true`). The default output is rounded (e.g. `a = 2.766`),
  which alone gave ~40" errors.
- Heliocentric ecliptic J2000 elements to an equatorial state, then integrated barycentrically with the Sun and the
  planet-system barycentres from DE440 (Earth-Moon as one body), RK4 with half-day steps, quintic Hermite interpolation
  between steps, one-step light-time correction (astrometric, as `CN`).
- Against the JPL Horizons orbit files of 102 asteroids over 21 days: worst 0.01", median 2 km. 102 asteroids in 0.2 s.
  Not for close Earth approaches (no Moon separately, fixed step).

### 3.2 The screen: `pyoccult/screen.py`

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

Against `pyoccult/search.py` on the same events: same stars, times within 5 s, the same drops and durations.
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
lookup with a bright cap reads only the bright end of each cell. Built once from the catalog (~30-70 s), opened
memory-mapped. A lookup takes 5-50 ms. A star limit above G 15 needs a deeper index, in whole magnitudes
(`bright_G16.0.v2.npy`: ~90 M stars, ~3.7 GB; G 18 would be the whole catalog again, ~11 GB). The pick builds a
missing one once, in the main process before the workers start, with little memory: it counts the stars per cell,
writes each catalog file's stars into their cell's slots of a memory-mapped file and then sorts each cell by G, a
block at a time (peak about one catalog file or block, not the whole index).

### 3.5 Speed and output

465k asteroids (H < 17) over 8 days: 875 s in one process, 318 s with 4 worker processes (each loads its own SPICE
kernels).

**Memory.** Each worker screens the asteroids in chunks of 2000. For a chunk it holds, for every asteroid and every
10-minute step of the window (144 per day), its barycentric position and velocity, its direction and distance from
the Earth, its heliocentric vector, phase angle, shadow speed and visibility: about 200 bytes per asteroid and step.
So, per worker:

| part | size | grows with |
|---|---|---|
| Python, SPICE kernels, pandas | ~0.5 GB | fixed |
| chunk arrays | ~55-60 MB per day of window | days (linear) |
| stars near one asteroid's path | small, temporary | path length (days) and star limit (~2.5-3x per magnitude) |

That is about 0.7 GB per worker for 3 days, 1.6-2 GB for 20 days, ~4 GB for 60 days; the total is that times the
number of workers (seen: 4 workers at ~1.9 GB each). Rule of thumb, to stay out of swap:
workers x (0.5 GB + 55 MB x days) well below the free memory.

* **H limit**: almost no effect on memory, only on time. More asteroids are more chunks, and a worker handles one
  chunk at a time. Only the main process grows a little with the asteroid list (well under 1 GB, even for all
  numbered asteroids).
* **Star limit (G)**: mostly shared memory. The bright-star index is memory-mapped, so the workers share it in the
  file cache (it shows as SHR in `top`, and the system can free it): 1.3 GB for G <= 15, ~3.7 GB for G <= 16. Per
  asteroid, the list of stars near its path grows ~2.5-3x per magnitude, but it is temporary and small next to the
  chunk arrays.
* **Days**: the per-worker chunk arrays (above) and longer star lists. For long windows use fewer workers, or split
  the window into several picks (each is saved and reused by searches).

**CPU.** NumPy's linear algebra may run several threads of its own in each worker. With many workers that
oversubscribes the CPU (seen: load 18 on 8 threads, single workers at 320 %), which costs time rather than gaining
it. One math thread per worker is usually faster:
`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 pyoccult` (or before `pyoccult pick`).
Workers up to the number of physical cores; the GUI default is half the logical CPUs.

Output: `pick_events.csv`, a ranked table (brightest star first by default) and `targets.py` with the
asteroids of the best events; their size data goes to the shared size cache.

### 3.6 Saved picks: `pyoccult/picks.py`

The pick is the slow step, so each run for a named site is also saved as `picks/<site>__<start>_<days>d.py` (targets,
names and `pick_meta`: site, position, window, settings, time of the pick) plus the `.csv` of its events. With
`targets_source = "auto"` (default) `pyoccult/search.py` takes the newest saved pick of its site whose window covers the
search window and that was made at the site's current position (within 0.01 deg); otherwise `targets.py` or the
config list. An explicit target list (GUI text field, a run override, the OWC check) always wins. The run summary
records which list was used, and the report header shows it.

---

## Part 4: Data sources

| Item | Source | Used for |
|---|---|---|
| `naif0012.tls`, `pck00010.tpc`, `de440.bsp` | NAIF generic kernels | leap seconds, Earth radii, Sun/Moon/planets |
| `earth_latest_high_prec.bpc` | NAIF generic kernels | ITRF93 Earth orientation, refreshed after `earth_pck_max_age` days; measured to its "last datum", predicted ~3 months beyond (both shown at start-up and in the report header; a window past the coverage is refused) |
| Asteroid orbit files | JPL Horizons API (`EPHEM_TYPE=SPK`), cached in `cache_path` | `pyoccult/search.py` positions |
| Asteroid size, H, G | SBDB API (`sbdb.api`, `phys-par=1`), cached per asteroid | `get_asteroid_size` |
| Elements, sizes for all asteroids | SBDB Query API (`sbdb_query.api`, numbered, full precision), cached | `pyoccult/pick.py` |
| Asteroid names | SBDB full name, from the same per-asteroid cache as the size | `get_asteroid_name` |
| Stars | Gaia DR3 bulk files, `cdn.gea.esac.esa.int/Gaia/gdr3/gaia_source/` | local catalog |
| Stars, ready-made | Zenodo [doi:10.5281/zenodo.23113337](https://doi.org/10.5281/zenodo.23113337) (G <= 16, G <= 18) | local catalog without the build |
| Path uncertainty | Horizons observer table, RSS 3-sigma position | 3-sigma map lines |
| Asteroid satellites | W. R. Johnston, Binary Minor Planets Compilation V3.0 (NASA PDS 2019, [doi:10.26033/bb68-pw96](https://doi.org/10.26033/bb68-pw96)) plus satellites seen in occultations (archive below); extract `pyoccult/data/binaries.json` | "+moon" in the tables, satellite line in the favorites panel, satellite zone on the maps |
| Earlier occultations | NASA PDS Small Bodies Node, "Small Bodies Occultations" V4.0 (Herald, Dunham et al., [doi:10.26033/ehqs-jp27](https://doi.org/10.26033/ehqs-jp27)), extract shipped as `pyoccult/data/occultations_pds.json` | reference line in the favorites panel (not used for the prediction) |
| Map | Leaflet 1.9.4 (cdnjs); OpenStreetMap tiles (`--tile-url` for others) | report |
| Reference | Occult / OWC search results, pasted as text into `owc_reference.txt` (private, not in git) | validation |

### 4.1 Sizes: what Horizons/SBDB has, and what occultations measured

Horizons and the Small-Body Database hold no occultation chords or profiles. Their physical data is one summary per
asteroid: `diameter` (+- sigma, mostly from NEOWISE, AKARI, IRAS or radar), `extent` (three axes, only for a few dozen
well-studied bodies), albedo, rotation period, pole, taxonomic type. Occultation results reach Horizons only through
the orbit: an occultation gives a precise position, reported to the Minor Planet Center as astrometry.

The accepted occultation results are archived by NASA's Planetary Data System, Small Bodies Node: "Small Bodies
Occultations" (D. Herald, D. W. Dunham et al., about yearly; https://sbn.psi.edu/pds/resource/occ.html). Version 4.0
(2024-04-22) holds 9645 asteroid events of 2907 asteroids, 1958 to 2023-12:

* `AsteroidSummary`: per event the fitted ellipse (major/minor axis, position angle, uncertainties), a flag when the
  diameter was assumed rather than measured, and a quality code: 0 no reliable position or size (399 events),
  1 astrometry only (7374), 2 limits on size but no shape (1261), 3 reliable size (521), 4 resolution better than
  shape models (77).
* `AsteroidDiameters`: for 512 asteroids, the volume-equivalent diameter from fitting all their events to 3-D shape
  models (DAMIT, ISAM), with uncertainty: the best sizes available.
* `AsteroidTimes`: the chords (every observer's disappearance and reappearance), with names and positions.

Reliable measured sizes (codes 3-4, size not assumed) exist for 343 asteroids, median 120 km (90 % above 52 km): the
archive improves the large asteroids, while the small typical targets (a few km) mostly have no measured size, or
only astrometry. PyOccult ships a compact extract (`pyoccult/occultations.py`, `data/occultations_pds.json`, 387 kB:
per asteroid the number of events and years, quality counts, the best measured profile and the shape-model diameter;
no chords, no observer data) and shows it as a reference line with the size in the favorites panel. Using it as a
size source (before NEOWISE) is a possible next step; Occult's own archive (D. Herald) is newer than the PDS version.

### 4.2 Asteroid satellites

About 650 asteroids and TNOs have known companions (W. R. Johnston, "Asteroids with satellites", kept current at
https://www.johnstonsarchive.net/astro/asteroidmoons.html). The citable, downloadable version is his Binary Minor
Planets Compilation in NASA's PDS (V3.0, complete to 2019-03-31: 370 companions in 351 systems): per companion the
primary's and the companion's diameter, the distance (semimajor axis, km) and the orbital period. The occultation
archive (4.1) adds satellites seen in occultations (57 events of 40 asteroids: date, separation in mas, position
angle, size), including old reports that were never confirmed (e.g. Hebe 1977, Juno 1978).

PyOccult ships an extract of both (`pyoccult/binaries.py`, `data/binaries.json`, 325 numbered systems, 43 kB) and
shows it as reference information: "+moon" (or "+2 moons"; "+moon?" when only reported in an occultation and not in
Johnston's list) after the asteroid in the Results and Favorites tables, a "Satellites" line in the favorites panel,
and on the event maps (KML, report map, globe plot) a dotted **satellite zone** at the primary's shadow edge plus
the largest known moon distance plus its radius: a satellite's own shadow passes somewhere inside it. The satellite's
position at the event is not predicted: that needs its orbit (orientation and phase), known well for only a few
systems. Moons found after 2019 are not in the extract (Johnston's Archive has them).

---

## Part 5: Validation

All checks, with their numbers and the discussion of the differences, are in
**[VERIFICATION.md](VERIFICATION.md)**. In short:

- **Against OWC** (five search results at two sites, Oct 2-11 2026, 6 to 50 events each): the same stars (our Gaia G
  equals OWC's magnitude column), times within a few seconds (mostly under 2 s), drops within 0.25 mag below 5 mag,
  durations within 10 % where both use the same diameter. Latest set (Oct 8-11, 0.14.0): 44 of 50; the rest are two
  Gaia 2-parameter stars missing from the local catalog, one small asteroid's orbit and three drops (asteroid
  brightness).
- **Against Occult's plots:** star positions agree within Occult's 1-sigma since stellar parallax and light deflection
  were added (0.10.0).
- **Internal and geometric checks:** the corridor search against the old windows search, the pick screen, the pick's
  orbits against Horizons, planet and moon ephemerides and contact times, and the test suite.

---

## Part 6: Open items

- **Close and double stars** (since 2026-10-06 partly handled, `pyoccult/doubles.py`): every event checks the local
  catalog for neighbours within `companion_radius_arcsec` (4") that are at most 5 mag fainter; their light stays in
  the camera image when the star is covered, so the drop is recomputed with it (`mag_drop_blended`), and noted with
  a warning sign in the report when it is at least 0.1 mag smaller. With `gaia_online_check` (default on) one query
  per run to the Gaia DR3 archive adds what the local catalog lacks: Gaia's hints that the star itself is double
  (`non_single_star`, `ipd_frac_multi_peak` > 2 %, `duplicated_source`, `ruwe`) and neighbours it leaves out (fainter
  than its limit, or RUWE >= 1.4). Still open, in order of value:
  1. Known doubles: match the event stars with the occultation-discovered doubles of the PDS archive
     (`DoubleStars` table; 76 discoveries before 2020, 61 closer than 50 mas) and the Washington Double Star Catalog.
  2. Events on stars the local catalogs leave out: Gaia 2-parameter sources (position only, no parallax or proper
     motion) and poorly measured stars (RUWE >= 1.4, often unresolved doubles). Their events are never predicted;
     OWC lists them. Seen in the OWC set of Oct 8-11 2026: 2 of 50 events, both on 2-parameter stars of G 11.6 and
     12.0 (VERIFICATION.md, 1.5). Fix: keep them in the catalogs, flagged (a 2-parameter star's position error grows
     with the years since 2016), as a catalog rebuild or a small supplementary file (new Zenodo versions).
  3. Step events: for a known pair, the two shadows (offset by separation x distance) and the drop of each step.

- **218001**: OWC lists a 1.56 mag drop and 0.51 s, PyOccult 12.97 mag and 0.25 s. The duration difference is the
  diameter (OWC 3.56 km, PyOccult 1.77 km from H). The drop is unexplained; hypothesis (unverified): the 5.6 mag star's
  angular diameter is comparable to the shadow, making the event partial. Idea: Gaia `radius_gspphot` and
  `distance_gspphot` (angle in mas ~ 9.305 R / d_pc), a partial-coverage drop, and a flag when the star is larger than
  about 30 % of the shadow.
- **Stellar parallax**: applied since 0.10.0 together with the light deflection (see below); the old unused
  `geocentric_star_dir` in pyoccult/search.py did the same and is superseded by `pyoccult.astrometry.parallax_dir`.
- **`star_test`'s `observable` text column**: `if not observable(...)` tests a tuple (always true), so the text never
  says "no". Harmless today, because `handle_star` rejects unobservable events with `observable(...)[0]`.
- **Path uncertainty (sigma)**: use the part of the Horizons error ellipse across the track (quantity 37: `SMAA_3sigma`,
  `SMIA_3sigma`, `Theta_3sigma`, projected onto the direction across the shadow's motion) instead of the RSS value, which
  overstates the path width whenever the long axis lies along the track. Also: Horizons gives these values to 0.01"
  only, which is coarse for well-known orbits (0.01" is ~10 km at 1.4 AU), and a value that rounds to 0.00 falls back to
  the 10 km default. Then compare with OWC event by event; the OWC orbit uncertainty comes from another source, so an
  exact match is not expected.
- **Verified 2026-10-03**: the Horizons column is `RSS_3sigma` (matched by `path_sigma3_km`), and the Earth-PCK body
  id 3000 gives the coverage message at start-up.
- **Report**: the map uses OpenStreetMap tiles, which need the page served by a web server (a `file://` page sends no
  Referer, so the tiles are refused); `--tile-url` selects another tile server.
- **Ideas**: `m_before` / `m_during` columns in the log; process-level parallelism by target in `pyoccult/search.py`.

### Gravitational light deflection and stellar parallax (built in 0.10.0, 2026-10-04)

**What PyOccult does now.** The asteroid comes from `spkpos(..., 'CN', '399')`: light-time corrected, astrometric,
with no stellar aberration and no gravitational light deflection. The star direction is the Gaia DR3 catalog
direction, propagated with its proper motion; Gaia directions are by definition free of light deflection (the
catalog removes it). Aberration is consistent: neither source gets it, and it would shift both the same way, so it
cancels. Light deflection does not cancel: the star's light and the asteroid's reflected light are bent by
different amounts, because the asteroid is much closer.

**Size.** For a source in direction u seen from an observer at distance E from the Sun (unit vector e from the Sun
to the observer), with q the unit vector from the Sun to the source (q = u for a star):

    deflection = (2GM/c^2) / E * |e - (u.e) u| / (1 + q.e)          (2GM/c^2 = 2.95 km for the Sun)

For a star this is 4.07 mas x (1 + cos eps) / sin eps at elongation eps (1.75" at the solar limb). What moves the
shadow path is the difference between the star's and the asteroid's deflection, times the asteroid's distance.

Sun, typical main-belt asteroid (2.5 AU from the Sun), observer at 1 AU:

| Elongation | Star | Asteroid | Difference | Asteroid distance | Shift of the path on the ground |
|---|---|---|---|---|---|
| 60 deg (twilight) | 7.05 mas | 4.24 mas | 2.81 mas | 2.85 AU | 5.8 km |
| 90 deg | 4.07 mas | 2.91 mas | 1.16 mas | 2.29 AU | 1.9 km |
| 120 deg | 2.35 mas | 1.99 mas | 0.36 mas | 1.85 AU | 0.5 km |
| 150 deg | 1.09 mas | 1.04 mas | 0.05 mas | 1.58 AU | 0.05 km |
| 170 deg and beyond | <= 0.36 mas | about the same | ~0 | 1.5 AU | negligible |

Jupiter (2GM/c^2 = 2.8 m, 4.2 AU away), a star at angular distance chi from Jupiter's centre, asteroid at 1.5 AU
(much closer than Jupiter, so its light is not bent by Jupiter):

| chi | Star deflection | Shift of the path |
|---|---|---|
| 20" (Jupiter's limb) | 19.1 mas | 21 km |
| 30" | 12.7 mas | 14 km |
| 1' | 6.4 mas | 7 km |
| 5' | 1.3 mas | 1.4 km |
| 10' | 0.6 mas | 0.7 km |
| 1 deg | 0.1 mas | 0.1 km |

Saturn gives about a third of Jupiter's effect at the same angle; Earth and Moon only micro-arcseconds. For an
asteroid beyond the deflecting planet (for Jupiter: Trojans, outer objects) both lights are bent and the difference
shrinks.

**What this means.**
- The Sun term is not an extreme case: away from opposition (morning and evening sky, elongation below ~120 deg)
  the path shifts by 0.5 to 6 km, the size of a small asteroid's shadow and of the 1-sigma band of a well-known
  orbit. Near opposition, where most good events are, it is negligible.
- The planet term matters only within a few arc-minutes of Jupiter (or closer for Saturn). Such events are rare,
  and the planet's glare makes them hard to observe, but they are scientifically interesting (appulses, the
  deflection itself) and should then be predicted correctly.
- The OWC comparison (Part 5, VERIFICATION.md) compared times (agreement 1-5 s); a few km along the track is well under a second.
  The cross-track position of the path, where this shift shows, has not been compared. As far as known, Occult
  includes light deflection (to be confirmed); then OWC paths of events away from opposition would differ from ours
  by the amounts above.

**Real events.** For an OWC search at the second site (50 events, Oct 4-7 2026, with twilight events) the expected
shift was computed for every event: 16556 at elongation 65 deg (morning twilight) 4.6 km, 22336 at 79 deg (evening
twilight) 3.1 km, four events at 87-92 deg about 2.3 km, and below 0.1 km from elongation 150 deg on. So it is not
only twilight: events around elongation 90 deg in the dark evening or morning sky shift by about 2 km. These are the
events for a cross-track comparison with OWC.

**Occult applies it (checked 2026-10-04 on 16556).** Occult's printed star position for 16556 (elongation 65 deg)
differed from PyOccult's (then Gaia with proper motion only) by 4.5 mas, nearly away from the Sun, as expected if
Occult applies the light deflection and the stellar parallax; with both added (0.10.0) the difference fell to 0.9 mas,
within Occult's 1-sigma. Details and a control case near opposition: [VERIFICATION.md](VERIFICATION.md), section 2.

**Implemented in 0.10.0 (2026-10-04).** `pyoccult/astrometry.py` corrects the star direction once per candidate in
`handle_star`, at the estimated event time (both corrections change by micro-arcseconds within the solver window):
stellar parallax (Gaia parallax > 0) and the light deflection by the Sun, Jupiter and Saturn (GM from DE440),
applied as star minus asteroid since the asteroid (SPICE 'CN') stays undeflected. Everything after it (time, offset,
map, preview) uses the corrected direction; `star_ra`/`star_dec` in the log are that direction, and the log columns
`corr_parallax_mas`, `corr_deflection_mas` give the size of each correction. Switches in pyoccult_config.py:
`star_parallax`, `light_deflection` (both default on); the run summary records them and the report header shows them.
Not yet in the pick screen (its ~2 km screening accuracy hides them).

Checks: `tests/test_astrometry.py` (4.07 mas at elongation 90 deg, 1.75" at the solar limb, the differences star
minus asteroid of the table above, Jupiter 6.36 mas at 1', parallax size and direction, switches off = unchanged);
switches off reproduce the previous results exactly; with the corrections an OWC set of 50 events gained two matches
and every path moved by the predicted amount; Occult's star positions now agree within its 1-sigma. Numbers:
[VERIFICATION.md](VERIFICATION.md), sections 1.4 and 2.

---|---|---|
  | Gaia only | 4.52 | 0.09 |
  | Gaia + parallax | 5.60 | 0.87 |
  | Gaia + deflection | 1.91 | 0.66 |
  | Gaia + parallax + deflection (0.10.0) | 0.90 | 0.29 |

  Only parallax plus deflection fits both within sub-mas and within Occult's 1-sigma (0.9 and 4.0 mas). 30819 alone
  is a weak test: near opposition the parallax (towards the Sun) and the deflection (away from it) partly cancel.
  A sharper test would be a star with parallax > 3 mas at elongation ~90 deg.

---

## Part 7: Future plans

### Major solar-system bodies as targets (planets and moons built in 0.14.0; Earth's Moon open)

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

**User side (plan of 2026-10-08).** A GUI tab **Planets & Moons** after Pick, choosing targets in groups (no pick
needed: only a few dozen bodies): Moon · Mars system · Jupiter system (planet + Galilean moons) · Saturn system
(planet + major moons) · Uranus · Neptune + Triton · Pluto + Charon. A group's satellite kernel is downloaded the
first time it is chosen. The targets go into the same list, with a readable type prefix that cannot collide with
asteroid numbers: `L:Moon`, `P:Jupiter`, `M:Io`, `M:Titan` (not a letter plus a NAIF number). They run as their
own search (own limits: bright stars, glare, long windows); only the target preparation differs (no Horizons SPK,
no SBDB size: radii from the kernels, brightness from a table). The hit log marks the target type, so the report
can show planet events with or apart from asteroid events. Order: Moon first, then the Jupiter system, then the
rest.

**Suggested order.**
1. The Moon as an optional target: about half a day; no new data; many events to cross-check against Occult.
2. Planets and major moons by name: optional kernel downloads in setup, ellipsoid limbs, a brightness table; a day or
   two, with clear caveats about rings, atmospheres and glare.

The pick tool would not need to change: there are only a handful of major bodies, so they would simply be listed as
targets.

**Status (0.14.0, 2026-10-08): planets and moons are built** (`pyoccult/bodies.py`; usage in README, "Planets and
moons"; checks in VERIFICATION.md, section 3): Mars to Neptune, Pluto and 91 of their 458 known moons, a GUI tab
with groups per system, D/R contact times, a results list and report layout of their own, previews with the
system's disks. Of the items below, 1-5, 7 and 8 are done (the preview without phase and glare halo); open are 6
(the limb ellipse: the limb is a circle of the equatorial radius, so a graze near a pole of Jupiter or Saturn may be
a miss; rings not modelled) and the Moon (`L:Moon`: bright limb, daylight, its 30' disk). One change to the plan:
the positions come from JPL Horizons (the same ephemeris as NAIF's satellite kernels), written into a small type 13
kernel per search window (~1 m); NAIF's kernels are an optional download (`pyoccult setup --planet-kernels`).

**Implementation notes (2026-10-08, from a review of the current search).** The search loop itself works unchanged
for major bodies: corridor scan, solver (`besselian_offsets`, `star_test`), local Gaia catalog, star corrections,
visibility (`observable`), Moon info, maps, globe and report only ask SPICE for the target's position (`spkpos` with
`IO`, `MOON`, `599`, ... once the kernel is loaded). What a "target kind" check (asteroid / planet / moon / Moon,
from the `L:`/`P:`/`M:` prefix) has to change, most important first:

1. **Brightness, drop, star limit.** `corridor.limiting_star_mag` caps the star magnitude from the asteroid's H and G
   and the minimum drop, and `event_metrics` computes the drop from star + target light. Against Jupiter (mag -2)
   or the Moon (-12) every drop is ~0, so these filters would reject every event. Planets and the Moon: no drop
   filter and no H/G cap, a plain star limit instead (later: glare, i.e. how bright the star must be at a given
   distance from the limb). Major moons: a brightness table (V or G at opposition, phase law) in place of SBDB H/G;
   the drop formula then works as for asteroids.
2. **Contact times.** We log the moment of closest approach, which is enough for asteroids (seconds). For the
   Moon and planets, disappearance (D) and reappearance (R) are minutes to an hour apart, and those are what
   observers need: solve |offset(t)| = radius on both sides of the closest approach (same distance function,
   e.g. `brentq` on [t_ca - T, t_ca] and [t_ca, t_ca + T]); log `d_utc`, `r_utc`, and show them in the report.
   Bright or dark limb at D and R (Moon: position angle vs the terminator) is a useful extra.
3. **Light deflection.** `astrometry.corrected_star_dir` deflects by the Sun, Jupiter and Saturn as star minus
   target (`deflect(..., unit(ast - body), ...)`). With the target in that body's own system (Jupiter itself or a
   Galilean moon) the target-minus-body vector is ~0 or tiny: skip the target's own planet for the planet itself,
   and check the formula's validity for its moons (close to the planet the deflection of the star is real, mas).
4. **Target preparation** (`fetch_target_orbit`, `get_asteroid_size`, `get_asteroid_name` in `search.py`): no
   Horizons SPK and no SBDB. Load the group's satellite kernel (downloaded the first time, like the Gaia catalog;
   names and sizes to verify at NAIF), radius from the PCK (`bodvrd RADII`: mean for a circle, or the ellipsoid),
   name from a table.
5. **Path uncertainty.** `paths.path_sigma3_km` asks Horizons for the small-body RSS uncertainty, default
   `default_sigma3_km` (10 km). Planets and major moons are known to well below a km (Moon: metres): use a
   per-kind value, else the sigma lines and the Chance column are wrong.
6. **Shape.** The shadow is a circle of one radius. Fine for the Moon and the major moons; Jupiter and Saturn are
   flattened (6-10 %): first version with the mean radius and a note, later the limb ellipse (SPICE `edlimb`)
   projected on the fundamental plane. Rings and atmospheres (gradual drops, central flashes) are not modelled.
7. **Report and lookups.** The asteroid cell links to JPL SBDB and adds "+moon", the earlier-occultations line, the
   close-star check and OWC, all keyed by asteroid number: skip them for major bodies (or link to a suitable page,
   e.g. NASA/JPL's body page), and show the kind (e.g. a "planet" / "moon" badge). `observable`'s Sun limit stays;
   the Moon also needs a daylight/bright-limb filter.
8. **Preview image** (`preview.render_svg` via `search.write_preview`): it draws the target as a point with its
   track. For planets and the Moon draw the disk at its angular size (radius / distance) with the phase (lit side
   from the Sun direction), the planet's major moons at their positions in the field (from the same kernel), and
   optionally a glare halo; for a moon target also its planet if it is in or near the field. The field size must
   grow with the disk (the Moon is 30').

Hit log: a `target_kind` column (asteroid, planet, moon, moon_earth) so the report can list planet events with or
apart from asteroid events. The OWC check, the pick tool and the saved picks stay asteroid-only.
