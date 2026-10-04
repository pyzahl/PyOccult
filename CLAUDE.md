# PyOccult: project notes for Claude Code

Portable Python replacement for the old Windows occultation predictor (Occult / occult.exe, behind OWC). Finds asteroid
occultations of Gaia stars for one observer site. Read `ABOUT.md` for the computations and sources, `README.md` for usage.

## Files
- `pyoccult.py`: main search script. Kernel setup runs at import time (not import-safe). Driver is the `__main__` block.
- `sites.py` (private, not in git; layout `sites_example.py`): named observing sites with view (min_alt, max_sun_alt,
  reach_km) and equipment (aperture_cm, frames, mag_adjust, extinction, ...); `pyoccult_config.py` derives `LAT`, `LON`,
  `ELE`, `MIN_STAR_ALT`, `MAX_SUN_ALT`, `MAG_MIN`, `pick_*` from `default_site` or env `PYOCCULT_SITE`. Never put real coordinates in tracked files.
  Env `PYOCCULT_CATALOG=<folder>` overrides `gaia_local_dir` for one run (GUI header selector sets it).
- `pyoccult_config.py`: run config (targets, window, site, thresholds). Optional: `map_dir`, `min_mag_drop`, `search_mode` (`corridor`/`windows`), `corridor_step_s`,
  `gaia_local_dir` (required by corridor mode), `gaia_local_gmax`.
- `pyoccult_paths.py`: shadow ground track (centre, limits, 3-sigma) as KML.
- `pyoccult_report.py`: `hits_log.csv` (+ last run of `hits_log.runs.jsonl` for the header) to HTML/Markdown with an embedded Leaflet map. Standard library only.
- `pyoccult_pick.py`: event finder over all asteroids (OWC-style) for a window; writes `pick_events.csv` and
  `targets.py`, and saves both per site + window in `picks/` (`pyoccult_picks.py`; pyoccult.py with
  `targets_source = "auto"` uses the newest saved pick of its site covering the search window; an explicit
  `targets` override sets `"list"`). Engine `pyoccult_screen.py` (site solve, OWC observability formula), orbits `pyoccult_orbits.py` (SBDB full-precision
  elements + planets, RK4, ~0.01" vs Horizons), stars `BrightIndex` (G <= 15, cells sorted by G). Worker processes.
- `pyoccult_corridor.py`: per-asteroid path, magnitude cap and vectorized candidate scan; `corridor_candidates(plan, local)`
  takes the stars from `LocalGaia`. No archive access (removed 2026-10-01: archive too slow).
- `pyoccult_setup.py`: one-time bootstrap (kernels via `pyoccult_kernels.py`, local Gaia catalog, bright-star index);
  rerunnable, resumes. `pyoccult_kernels.py`: the kernel download, also called by pyoccult.py at start-up.
- `pyoccult_gaia_local.py`: builds/reads a local G-limited Gaia DR3 copy from ESA's CDN bulk files (`build`, `status`);
  one `.npy` per source file plus `.cells.npy` (1x1 deg cell index) and `.hpm.npy` (pm > 1500 mas/yr). No healpy.
  Ready-made copies (G <= 16, 18; no bright index) on Zenodo, concept DOI 10.5281/zenodo.23113337 (first version
  ...338, packed by `release/pack.sh`, untracked): `fetch_zenodo` (resumable, SHA-256, unpacks into any folder name);
  setup `--source auto|zenodo|esa` (auto: ask, Enter = zenodo; resumes a partial ESA build; esa for other limits).
- `pyoccult_sbdb.py`: shared per-asteroid SBDB cache (raw diameter/extent/H/G/albedo/name, not derived sizes). Filled by
  `pyoccult.sbdb_phys()` (per-object API) and by `pyoccult_pick.py` for its top targets (bulk rows); standard library only.
- `pyoccult_gui.py`: NiceGUI web interface (127.0.0.1 only); runs scripts as subprocesses via `pyoccult_runner.py`
  (JSON config overrides per run). `pyoccult_geo.py`: IP/place/elevation lookups (setup + GUI). `pyoccult_preview.py`:
  event preview SVG per hit (`maps/<target>_<stamp>.svg`), shown by the report's Preview button.
- `pyoccult_kstars.py`: KStars D-Bus control (Linux only, `gdbus` with `--` before args, else `dbus-send`; never raises).
  setGPSLocation(site) -> setLocalTime (KStars local time: re-read `tz` from location(), it follows DST of the shown
  date) -> setRaDecJ2000 (RA in hours) -> setTracking -> setApproxFOV. `set_location` (GUI Results checkbox,
  `KSTARS_OPT`): move KStars to the site (message names the old place) or keep it (warn if > 50 km). KStars ignores
  the tz passed to setGPSLocation and picks its own (Long Island got -6): label only, UT is right. GUI routes `/api/kstars/status|show`; the report's
  hidden `.ksbtn` buttons appear only if the status call succeeds (not from file://). Verified with KStars 3.6.2.
- `pyoccult_favorites.py`: favorites in `favorites/` (private, gitignored): `favorites.json` (entry = hits_log record,
  site and run context from the run summary, status, note) and `favorites/<target>_<YYYYMMDDTHHMM>/` with copies of
  KML and preview SVG. Report: hidden `.favbtn` stars, shown only via the GUI (`/api/favorites/keys|add`; add looks
  the event up in hits_log.csv by target + minute, site from the last run summary). GUI tab Favorites: iframe of
  `favorites/favorites.html` (`write_page`: report `to_html` with `meta["favorites"]`, rows get `e["fav"]`/`e["site"]`;
  select boxes, Site/Status/Note/Added, per-row KStars site) rebuilt after every change; mass actions call
  `/api/favorites/update|remove|cleanup`; row click -> `parent.emitEvent('fav_select', key)` -> detail panel (preview,
  map from the KML copy, size line, status, note). Entry key `phys`: the pyoccult_sbdb cache data (H, G, diameter,
  diameter_sigma, extent, albedo as (value, ref)) copied at add time (/dev/shm cache is volatile); GUI start
  backfills it for older entries. `favorites.csv` is rewritten by every `_save` (flat: key/status/note/added/site,
  all record columns, sbdb_*, file paths).
- `pyoccult_owc_check.py` + `owc_reference.txt` (private, not in git: names the site): an OWC search result pasted as
  text; the script parses events and filter settings, reruns pyoccult.py at the sites.py site and compares.
- `owc_refs/` (private, not in git): stored OWC search results (`<site>_<date>_<filter>.txt`, `--ref` for
  pyoccult_owc_check.py) with the matching pick runs (`.pick.csv/.log`) and a README of settings and findings. Keep
  adding sets there; never delete them.
- `CONTRIBUTING.md`: fork/branch workflow, setup, tests, working with Claude Code, private files, pull requests,
  GPL-3.0-or-later for contributions. `LICENSE` (GPL-3.0 text), `CITATION.cff` (validated with cffconvert).
- `tests/`: stand-in based tests, run each with `python tests/<name>.py` (no SPICE, astropy or network needed).

## Conventions that matter
- Asteroid position: `spkpos(id, et, 'J2000', 'CN', '399')`. Earth centre is 399, not 3. `CN` is astrometric (matches Gaia).
- Fundamental plane: z toward the star, x east = (0,0,1) x z, y north. Miss distance = hypot(dx, dy) in km.
- Observer longitude is east-positive, geodetic, radians inside the solver.
- Target ids are strings of the asteroid number ('218001'); the SPK is aliased with `boddef` in `fetch_target_orbit`.
- `observable()` returns a tuple `(ok, star_alt, sun_alt)`; always index it. `if not observable(...)` is always False.
- `mag_drop` is the change in combined brightness (`m_ast - m_before`), never smaller than `m_ast - m_star`.
- Drop of at least `d` needs the star no fainter than `m_ast + 2.5*log10(1/(10^(0.4 d) - 1))` (2.54 mag for 0.1).
- SPICE is not thread-safe: use processes, load kernels per process, never call spice from threads. Network-only code
  (Gaia/Horizons fetches) may use a few threads.
- Gaia bulk files: `https://cdn.gea.esac.esa.int/Gaia/gdr3/gaia_source/` (note `esac`); the listing is an S3 bucket at
  `https://gaia.eu-1.cdn77-storage.com/?prefix=Gaia/gdr3/gaia_source/&delimiter=/`. Files are `csv.gz` with `#` comment
  lines and `null` for missing values.
- Gaia archive (windows mode only): never use synchronous `Gaia.launch_job`; it silently truncates at 2000 rows. Use
  `launch_job_async`. `Gaia.ROW_LIMIT = -1` does not lift the sync cap.
- Write cache files atomically (temp file + `os.replace`). Every cache (asteroid SPKs, SBDB bulk list, per-asteroid SBDB size data
  `PyOccult_sbdb_phys.json`; both SBDB caches refetched after `sbdb_max_age_days`) goes to `config.cache_path`
  (`/dev/shm` if present, else the system temp folder); never hard-code a path. Gaia is not cached: corridor mode
  reads the local catalog, the old windows mode queries the archive uncached.
- Earth PCK coverage: `pck_comment_dates` reads "Creation date" and "UTC Epoch of last datum" (end of measured EOP)
  from the file's comment block; `pckcov` gives the end of the prediction. Run summary key `earth_pck`; a search window
  past the end exits at start-up.
- SpiceyPy `surfpt` returns only the point and raises `NotFoundError` on a miss.
- Tests use stand-ins for spiceypy/astropy/astroquery that follow the real call contracts; keep them honest when changing
  signatures.

## Status
- Validated 2026-10-02 (`python pyoccult_owc_check.py`, 16 OWC events at the user's site, Oct 2-9): all 16 found, same
  stars (our G equals OWC's "V" column to 0.01, so OWC shows Gaia G), times within 5.4 s (13 within 3 s). Drops match within
  0.25 mag below 5 mag. Durations match within 10 % wherever both use the same diameter; 4 events differ only by
  diameter (H+albedo estimates, or OWC using another source than NEOWISE). Open: 218001 (OWC drop 1.56 mag, ours 12.97;
  OWC diameter 3.56 km, ours 1.77 km from H). Hypothesis, unverified: the 5.6 mag star's angular diameter makes it
  partial; not modelled yet (idea: Gaia `radius_gspphot`, `distance_gspphot`).
- Corridor search is merged into `pyoccult.py` (`handle_star` shared by both modes, `target_test_corridor`, 2-pass driver;
  `search_mode = "windows"` keeps the old path). The Gaia archive was far too slow for strip queries (2026-10-01), so the
  corridor reads only the local catalog `gaia_dr3_g18` (built 2026-10-01: 280.3 M stars of 1811.7 M, 11.2 GB, 101 min).
  Whole run for 23 asteroids x 20 days: 75 s.
- Verified 2026-10-01 against the old path (23 targets, 2026-10-01 + 20 days, reach 200 km): all 40 old hits with
  G <= 18 found, within 1.4 ms and 0.8 m; 10 extra real hits; the other 28 old hits are G > 18 (beyond the catalog).
- Solver bug fixed 2026-10-01: `star_test` minimised over raw ET, where `minimize_scalar(bounded)` has a ~12 s
  tolerance (sqrt(eps)*|x|); it now solves for the offset from the window centre (`tests/test_solver.py`). Results
  logged before (old `hits_log.csv`, maps) are off by up to ~9 s and ~90 km (median 6 km). The OWC check above uses
  the fixed solver.
- Corridor solver bracket: the scan estimates the Earth-centre closest approach; the observer's can be margin/speed
  (10-20 min) away, so the bracket is `corridor.solver_bracket_s` (+/- 1.3 margin/speed, >= 1 step, <= 4 h).
- Not run against live services: Horizons RSS 3-sigma column names in `pyoccult_paths.py`.
- Pick tool validated 2026-10-01: blind screen of all 465k asteroids (H < 17), Oct 1 + 8 d, 20 km reach, min alt 5:
  39 events incl. all 13 OWC reference events with H < 17 (same stars, times within 5 s, drops/durations as
  pyoccult.py); 819762 (H 18.45) needs `--all`. 875 s in one process, 318 s with 4 workers, same events.
  SBDB bulk elements MUST be full precision (`full-prec=true`): rounded ones give ~40" errors.
- Report map: OpenStreetMap tiles only (`--tile-url`), so it works through a web server (OSM needs a Referer), not
  from `file://`. Map dialog reopen bug fixed 2026-10-02 (the box was cleared on every open, removing Leaflet's panes).

## Ideas not built yet
- Star angular-diameter model for the drop and duration.
- Gravitational light deflection (ABOUT.md Part 6, estimated 2026-10-04): not modelled ('CN' and Gaia directions are
  both undeflected). The Sun's differential deflection (star minus asteroid) shifts paths 0.5-6 km at elongation
  < ~120 deg; Jupiter matters within a few arcmin (7 km at 1'). Plan: shift the star direction per event; then
  compare cross-track paths with OWC at low elongation.
- Process-level parallelism by target (`ProcessPoolExecutor`; parent does kernel checks, Horizons SPKs and opens the local Gaia catalog;
  workers return records, parent writes the CSV).
- `m_before` / `m_during` columns in the log.
- Favorites, next steps (simple version built 2026-10-04, see Files): re-predict one favorite with the latest orbit
  (single-target search; keep old map/preview versions next to new ones), export (CSV, KML bundle, report page),
  share/pull with Occult Watcher Cloud (campaign events, multi-site chords; how TBD, no known public OWC interface),
  observation data per favorite (result, D/R times, chord, link to the SODIS report from DVTI+CAM / ASTRID).

