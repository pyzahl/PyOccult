# PyOccult: project notes for Claude Code

Portable Python replacement for the old Windows occultation predictor (Occult / occult.exe, behind OWC). Finds asteroid
occultations of Gaia stars for one observer site. Read `ABOUT.md` for the computations and sources, `README.md` for usage.

## Files
- Layout (since 2026-10-06): PEP 621 package, src layout like PyMovie/PyOTE. `pyproject.toml` (setuptools, version
  from `pyoccult.version`, dependencies, entry point `pyoccult = pyoccult.__main__:main`); code in `src/pyoccult/`
  (paths below are relative to `src/`); install `pip install -e .` (later: uv). Imports are `from pyoccult import x`,
  never file paths. `pyoccult/home.py`: `HOME` = data folder, first match: env `PYOCCULT_HOME`; the saved setting
  `home.POINTER` (Linux `~/.config/pyoccult/home`, macOS `~/Library/Application Support/PyOccult/home`, Windows
  `%APPDATA%\PyOccult\home`; written by `pyoccult setup --home <dir>` or setup's first-run question); the checkout
  root (pyproject.toml); else `~/PyOccult` (`home.SOURCE` says which; stdlib only, no platformdirs). The dispatcher
  creates HOME except for `setup`, which chooses it first (`choose_home`, module level, before config). `PKG` (package dir: logo, `data/ne_110m_earth.json`, `templates/`). Every command
  chdirs to HOME, so data paths in the config stay relative (kernels, catalogs, sites.py, maps/, picks/, ...).
  `pyoccult/__main__.py`: dispatcher `pyoccult [command] ...` (no command = GUI; `COMMANDS` maps names to modules).
  It imports the module and calls `main()`, so functions sent to spawn workers (pick, gaia build) pickle as
  `pyoccult.<module>.<fn>`; never run those modules via runpy as `__main__`. Exception: `search` (not import-safe)
  runs via `runpy.run_module(..., run_name="__main__")`. The GUI starts runs as `[sys.executable, "-u", "-m",
  "pyoccult", <command>, ...]` with `PYOCCULT_HOME` and `PYTHONPATH` set. Tests put `src/` on sys.path.
- uv (2026-10-06): `uv run pyoccult` in a clone (or unpacked ZIP) creates `.venv` with `.python-version` (3.12) and the
  pinned set of `uv.lock` (universal: Linux/macOS/Windows; 94 packages). After any change to `dependencies` run
  `uv lock` and commit `uv.lock`; `uv run --locked ...` fails if the lock is stale. Tested on Linux only so far.
- `pyoccult/config.py`: loader. Runs `templates/pyoccult_config.py` (defaults), then the user's `HOME/pyoccult_config.py`
  (gitignored; copied from the template if missing) into this module's globals, so older user files get new keys.
  Puts HOME on sys.path (sites.py, targets.py) and templates/ (sites_example for old config copies).
- `pyoccult/version.py`: the one place for `__version__` and `__codename__` ("New Horizons"; changes at major
  milestones), `__author__`, `__copyright__`, `__license__`, `__url__` (GUI About box). Releases: GitHub tag `vX.Y.Z` (matching
  `__version__`) -> Zenodo DOI automatically; concept DOI 10.5281/zenodo.23149371 (README badge, CITATION.cff `doi`).
  Every version increase gets a
  `CHANGELOG.md` entry (Keep a Changelog style, newest first) (semver; keep CITATION.cff `version` and the README line in step);
  every module imports it, tools have `--version`, GUI header, run summary/report, picks and favorites record it.
- `pyoccult/search.py`: main search script. Kernel setup runs at import time (not import-safe). Driver is the `__main__` block.
- `sites.py` (private, not in git, in HOME; layout `pyoccult/templates/sites_example.py`): named observing sites with view (min_alt, max_sun_alt,
  reach_km) and equipment (aperture_cm, frames, mag_adjust, extinction, ...); `pyoccult_config.py` derives `LAT`, `LON`,
  `ELE`, `MIN_STAR_ALT`, `MAX_SUN_ALT`, `MAG_MIN`, `pick_*` from `default_site` or env `PYOCCULT_SITE`. Never put real coordinates in tracked files.
  Env `PYOCCULT_CATALOG=<folder>` overrides `gaia_local_dir` for one run (GUI header selector sets it).
- `pyoccult_config.py` (user file in HOME, not in git; template `pyoccult/templates/pyoccult_config.py`): run config (targets, window, site, thresholds). Optional: `map_dir`, `min_mag_drop`, `search_mode` (`corridor`/`windows`), `corridor_step_s`,
  `gaia_local_dir` (required by corridor mode), `gaia_local_gmax`.
- `pyoccult/paths.py`: shadow ground track (centre, limits, 3-sigma) as KML.
- `pyoccult/report.py`: `hits_log.csv` (+ last run of `hits_log.runs.jsonl` for the header) to HTML/Markdown with an embedded Leaflet map. Standard library only.
- `pyoccult/pick.py`: event finder over all asteroids (OWC-style) for a window; writes `pick_events.csv` and
  `targets.py`, and saves both per site + window in `picks/` (`pyoccult/picks.py`; pyoccult/search.py with
  `targets_source = "auto"` uses the newest saved pick of its site covering the search window; an explicit
  `targets` override sets `"list"`). Engine `pyoccult/screen.py` (site solve, OWC observability formula), orbits `pyoccult/orbits.py` (SBDB full-precision
  elements + planets, RK4, ~0.01" vs Horizons), stars `BrightIndex` (G <= index_gmax(cam_limit) = max(15, ceil(limit)), cells sorted by G; a missing one is
  built by `run_screen` in the parent before the workers start, low-memory via a memmap). Worker processes.
- `pyoccult/prescreen.py` (0.16.0; FORMAT 3 since 2026-10-10: time grid +-PAD_S 12 h, candidates kept if
  tc +- half touches the window, `numbers` +- HALF_MAX_S; region test via shadowtrack.ground_track; FORMAT 1 builds
  missed ~21 % of a 500 km region's asteroids through 41-sample gaps and axis-only sky tests): pre-screens = per region/window the asteroids with possible events (build:
  pick.fetch_sbdb/build_rows, orbits.propagate, BrightIndex.near_path with Earth radius + r_max + reach, corridor
  find_candidates, then a vectorized ground track per candidate: shadow axis in the fundamental plane -> surface
  point (sphere), J2000->ITRF from pxform on the 10-min grid + spin OMEGA*dt, region box (+ r_max + reach margin,
  lon wrap), Sun and star altitude there). SQLite `prescreen/<name>.db`: events + meta (build limits). pick
  `--prescreen`: PS.check (window, region, limits as loose) else exit 2; rows filtered by PS.numbers(et0, et1).
  GUI Pick "Asteroids" select (prescreen_options: files covering window and site). A superset by design: same
  events as the full pick when it fits. Build memory (2026-10-10): `plan_chunks` from `mem_status()` (/proc/meminfo MemAvailable; else
  half of physical) x mem_frac or --max-mem, model `chunk_bytes` = n x steps x BYTES_PER_STEP (12x3x8, measured ~10)
  + CHUNK_FIXED; workers reduced if MIN_CHUNK does not fit; w+1 chunks in flight, halved when free < 2 chunks.
  find_candidates gets block_cells=SCAN_CELLS (4e6; the corridor default 2.5e7 made a ~730 MB transient for 30-day
  paths), ground tracks in CAND_BLOCK blocks (`_ground_track`; identical events). Checkpoint `<out>.partial` (events
  + `done` numbers + meta 'settings'; resumed only with equal settings, `--fresh` discards), finished -> meta,
  DROP done, VACUUM, os.replace. Worker RSS peak includes the memory-mapped bright index pages (reclaimable); the
  progress line also shows RssAnon after the chunk. SIGTERM (GUI Stop) is handled like Ctrl-C. Use: pick `--prescreen auto`
  -> PS.numbers(et0, et1, gmax=cam_limit) (pick never uses stars fainter than cam_limit: G 13.2 -> ~1/40 of the
  asteroids vs ~1/6 at G 16) -> `best_fit` (newest by meta 'built' among check()==[]; else full screen + reasons); `box_around_all` (CLI
  `--around-sites`, all sites.py sites, widest longitude gap outside; lon width at the poleward edge, so >= km
  everywhere; `box_around` (single site) uses cos(site lat): ~7 % narrower at the north edge for 500 km at 41 N,
  documented, change only between builds: resume compares the stored region); targets.py line "# asteroids screened:".
  GUI Pick tab: p_pre "auto"/"all"/path (PRE_FIXED), `pre_info` line, expansion "Pre-screens" (ps_start, ps_days,
  ps_where site/sites/global, ps_km, `run_prescreen`, ps_table with fit reasons, `delete_prescreens`);
  prescreen_options() mirrors PS.check without SPICE (`_day_et`: both windows start 00:00 UTC).
- `pyoccult/shadowtrack.py` (2026-10-10): shadow elements per event (DTYPE 80 B: number, star, et=tc, g, m_ast,
  geo_miss, star dir sx/sy/sz f4, x0/y0/vx/vy/ax/ay f4 quadratic in dt=t-tc over +-half, half, r_km, err = misfit at 9
  points; measured <= 0.3 km), `fit`, `positions`, `ground_track` (shared by build and region test: N_TRACK 161
  samples, all tests widened by `_half_steps` and the sky by (r + reach)/R: strict superset vs 1281 samples),
  `region_mask`, `site_mask` (Site.at on a 1-min grid, segment distances between N_SAMPLES 81 samples, TOL_KM 10,
  TOL_DEG 1), `frames`, `in_box`. Global files: prescreen `<name>.global.npy` sorted by et + `.global.json` meta
  (kind global, n_events, n_asteroids); `PS.select` (searchsorted window +- half, g), `site_numbers`, `extract` ->
  region .db, `remove`, `is_global`; pick uses `site_numbers` for a global file; CLI `query`, `extract`, `index`.
  Reach is a PLANE distance: `ground_reach(sin_h, rho, sin_min)` = exact largest ground distance of an observer
  within rho (plane) of the axis point (|proj| = R cos h; chord^2 = rho^2 + R^2 dsin^2): 210 km -> 280 km at 50 deg,
  730 at 20, 1640 at 0; used for in_box margins and the sky tolerance in `_track` (FORMAT 3). Index
  `<name>.global.idx.npy` (IDX_DTYPE: lat_lo/hi, lon_w, lon_width, sin_lo/hi; `track_bounds` pads only gs + r;
  `near_site`/`hits_box` add `_reach_pad` = max ground_reach over the track's altitude range (not monotonic in h:
  33 points + 3 %) for the query's reach/min_alt, TOL margins; validated 2026-10-10: 0 dropped at all tested
  sites/limits, passes 14-26 % of events). Named regions `REGIONS` / `parse_region`.
- `pyoccult/corridor.py`: per-asteroid path, magnitude cap and vectorized candidate scan; `corridor_candidates(plan, local)`
  takes the stars from `LocalGaia`. No archive access (removed 2026-10-01: archive too slow).
- `linux_install.sh` (user's quick install, Linux/macOS): creates `.venv` with python3, installs the project via
  `.venv/bin/python -m pip install -e .` (never `activate`: sh runs it in a subshell; system pip is refused by PEP 668),
  runs `.venv/bin/pyoccult setup` then `exec`s `.venv/bin/pyoccult`; `set -e`, rerunnable. Keep it in step with setup/GUI changes.
- `pyoccult/setup.py`: one-time bootstrap (kernels via `pyoccult/kernels.py`, local Gaia catalog, bright-star index);
  rerunnable, resumes. `pyoccult/kernels.py`: the kernel download, also called by pyoccult/search.py at start-up.
- `pyoccult/gaia_local.py`: builds/reads a local G-limited Gaia DR3 copy from ESA's CDN bulk files (`build`, `status`);
  one `.npy` per source file plus `.cells.npy` (1x1 deg cell index) and `.hpm.npy` (pm > 1500 mas/yr). No healpy.
  Ready-made copies (G <= 16, 18; no bright index) on Zenodo, concept DOI 10.5281/zenodo.23113337 (first version
  ...338, packed by `release/pack.sh`, untracked): `fetch_zenodo` (resumable, SHA-256, unpacks into any folder name);
  setup `--source auto|zenodo|esa` (auto: ask, Enter = zenodo; resumes a partial ESA build; esa for other limits).
- `pyoccult/sbdb.py`: shared per-asteroid SBDB cache (raw diameter/extent/H/G/albedo/name, not derived sizes). Filled by
  `pyoccult.search.sbdb_phys()` (per-object API) and by `pyoccult/pick.py` for its top targets (bulk rows: size fields only); `get_full()` fetches the per-object
  record (rotation, pole, extent, type) for favorites; standard library only.
- `pyoccult/gui.py`: NiceGUI web interface (127.0.0.1 only); runs scripts as subprocesses via `pyoccult/runner.py`
  (JSON config overrides per run). `pyoccult/geo.py`: IP/place/elevation lookups (setup + GUI). `pyoccult/preview.py`:
  event preview SVG per hit (`maps/<target>_<stamp>.svg`), shown by the report's Preview button.
- `pyoccult/bodies.py` (2026-10-08): planets/moons as targets, prefix + name (`P:Jupiter`, `M:Io`; `L:Moon` later),
  REGISTRY (NAIF id, centre = system barycentre, kind, V(1,0), phase coeff, rough sigma3), GROUPS ("jupiter").
  `ensure_kernel`: Horizons VECTORS (CENTER 500@<bary>, 20 min, ICRF) -> SPK type 13 via `spkw13` in cache_path
  (~1 m vs Horizons; Horizons = jup365 ephemeris, so no 1 GB NAIF download), furnsh + `boddef(alias)` so all SPICE
  calls take "M:IO". search.py: corridor loop branch (no SBDB/Horizons SPK; size from PCK radii; planets H=None ->
  no drop cap, star limit = MAG_MIN like asteroids (GUI "Star G limit" override; no separate planet limit); moons H from satellites.json, G=MOON_G), deflection without own system
  (`bodies.deflectors`), sigma from REGISTRY, `contact_times` D/R (brentq on |offset|=r; logged d_utc/r_utc,
  duration_s; db contacts), record `kind`. Windows mode skips bodies. Verified 2026-10-08: Jupiter events, D/R at
  exactly the radius by independent topocentric geometry (0.1 km). Report: name + kind badge (no SBDB link).
  Stage 3: results lists in db (`results_list` "main"/"bodies", series per list via meta 'series:<list>', numbers
  unique); GUI tab "Planets & Moons" runs search with results_list=bodies, hits_output_cvs_file=bodies_log.csv,
  report `--layout bodies` (`html_row_body`: D/closest/R); favorites ★ finds events in the db (any list,
  `db.find_event_run`). File/folder names: `report.file_id` (P:Jupiter -> P-Jupiter). Preview: `disks=` (system
  bodies at angular size) and `field_arcmin` zoom. Optional NAIF kernel (`NAIF_KERNELS`, `naif_kernel`,
  `download_naif`; setup `--planet-kernels`): used if it covers the window (spkcov), else Horizons.
  All systems (2026-10-08): REGISTRY = PLANETS (Mars..Neptune kind planet, Pluto kind dwarf = H rule) + moons from
  `data/satellites.json` (`python -m pyoccult.bodies build`: Horizons 'MB' list + one OBSERVER query per moon,
  APmag/Ang-diam/r/delta; `phase_correct` with H-G G=MOON_G=0.5 via SPICE phase angle; `fill_estimates`
  radius<->H with albedo, flagged -> D_est/'*'). 458 moons, 91 usable. GROUPS per system (planet + usable moons by
  size), `featured()` = planet + radius >= 150 km vs smaller. `LOADED` = targets with kernels (previews).
  Brightness vs literature: ~0.2 mag (Phobos ~1 mag). Saturn rings not modelled.
- `pyoccult/db.py` (2026-10-08): results database `<data folder>/pyoccult.db` (config `results_db`; sqlite3, WAL,
  30 s busy timeout: GUI and run processes share it). Tables runs (summary JSON), events (kind, target, best_utc,
  record JSON; `series`), contacts (D/R, C1-C4 later), favorites (entry JSON), meta (schema, current series). A
  series = what hits_log.csv was: GUI "Start a fresh results list" / config `results_new_series` starts a new one.
  search.py: `db.start_run` at start (after a one-time `import_log` of an old hits_log.csv + runs.jsonl),
  `db.add_event` per hit, `db.finish_run` + `db.export` in run_summary: hits_log.csv and hits_log.runs.jsonl are
  EXPORTS of the current series (report, CSV button, OWC check and favorites read them). favorites.py load/_save use
  the db next to the favorites folder (favorites.json imported once -> .migrated). owc_check uses owc_check.db.
- `pyoccult/doubles.py`: close/double stars per event. Local: `companions()` from `LOCAL.cone` (radius
  `companion_radius_arcsec`, <= 5 mag fainter, proper motion to the event date), `blended_drop`, `fields()` (blend_*,
  mag_drop_blended, double_hint only if the drop changes >= 0.1 mag or Gaia flags). Online (`gaia_online_check`):
  `search.online_double_check` after pass 2: one async ADQL job (OR of circles, daemon thread, 120 s timeout) ->
  `online_fields` -> `db.update_events` (this run's events in the results database).
  New record fields go at the END of the hit record (the log is appended; mixed headers otherwise).
- `pyoccult/owc.py` (experimental, hidden: config `owc_lookup = False`, only by editing the config; the user is
  introducing it to IOTA people step by step, so keep it low-key): OccultWatcher Cloud lookup through the public
  event pages' interface `URL_OWC_API` (`events/?astNo=&dt=&bf=` then `event/<id>`; no login; `my-events` needs
  login: not used). Match by Gaia id (`gaia.id`) else time (10 min); 1 s pause, User-Agent PyOccult; on click only
  (GUI "Check OWC" in Results/Favorites, `run.io_bound`); cache `<data folder>/owc_cache.json`; report `owc_line()`
  under the asteroid (tags, station count, hover: observer, signed distance km, commitment).
- `pyoccult/binaries.py`: known asteroid satellites, `data/binaries.json` from Johnston's PDS compilation V3.0
  (fixed-width `binarytable.tab`, layout read from its PDS4 label) + SAT_* columns of the occultations archive's
  `Asteroid_*.psv` (separation in mas). `short()` "+moon"/"+moon?" (report label, Markdown), `text()` (favorites
  panel, hover), `zone_km()` = max(a + d2/2) -> `shadow_path(sat_km=)` adds 'satellite_plus/minus' -> KML
  "Satellite zone A/B", report LINE_STYLES, globe LINES. Reference only; moon positions not predicted.
- `pyoccult/cameras.py`: `SENSORS` (sensor, px w, px h, pixel um, camera names) for the Site tab's "Sensor (cameras)"
  list; sizes = pixels x pixel size (`sensor_mm`); one entry per sensor, cameras searchable in the label.
- `pyoccult/occultations.py`: earlier occultations from NASA PDS "Small Bodies Occultations" V4.0 (doi
  10.26033/ehqs-jp27): compact extract `data/occultations_pds.json` (per numbered asteroid: events, years, quality
  counts, best profile of codes >= 2 with measured size, shape-model diameter; no chords/observers), rebuilt with
  `python -m pyoccult.occultations build <zip>`. Reference line in the favorites panel only; not a size source yet.
- `pyoccult/globe.py` (0.11.0): Occult-style whole-Earth plot `maps/<stem>_globe.svg` (written by
  `pyoccult.write_globe` after the KML; `write_globes`, `globe_style` "color"/"lines"); `globe_data(spice, ...)` +
  pure `render_svg(d)`. Data `data/ne_110m_earth.json` (Natural Earth 110m coast/borders/land, public domain).
  Report "Globe" button (prevbtn with data-wide); favorites copy it as files["globe"] (+ `backfill_globes` from maps/
  at GUI start). Preview lookups exclude `*_globe.svg`.
- MPC observatories: `pyoccult.geo.mpc_observatories()` downloads https://minorplanetcenter.net/iau/lists/ObsCodes.html
  once to `data/ObsCodes.html` (gitignored) and parses the fixed columns (code [0:3], east lon [4:13], rho cos phi'
  [13:21], rho sin phi' [21:30], name [30:]); `mpc_geodetic` turns the parallax constants into WGS84 lat/lon/height
  (ele_ok False below 5 decimals: look the height up). GUI Site tab select (code + name only, so a code search does
  not match coordinates) and the `mpc_code` site key (report header, run summary). Replaced Occult's InstallSites.zip
  (0.12.0: mainly cities) and astropy's EarthLocation registry (no MPC codes).
- `pyoccult/kstars.py`: KStars D-Bus control (Linux only, `gdbus` with `--` before args, else `dbus-send`; never raises).
  setGPSLocation(site) -> setLocalTime (KStars local time: re-read `tz` from location(), it follows DST of the shown
  date) -> setRaDecJ2000 (RA in hours) -> setTracking -> setApproxFOV. `set_location` (GUI Results checkbox,
  `KSTARS_OPT`): move KStars to the site (message names the old place) or keep it (warn if > 50 km). KStars ignores
  the tz passed to setGPSLocation and picks its own (Long Island got -6): label only, UT is right. GUI routes `/api/kstars/status|show`; the report's
  hidden `.ksbtn` buttons appear only if the status call succeeds (not from file://). Verified with KStars 3.6.2.
- `pyoccult/exports.py` (2026-10-08): GUI CSV downloads. Columns from `csv_exports.py` in HOME (template
  `templates/csv_exports.py`, copied at first use; user EXPORTS dict per table over the template's): lists of
  (heading, source), source = shown name | "raw:<field>" | "*" | f(shown, raw). Shown values = the tables' text
  (`event_shown` from report.build_event + report fmt helpers; `pick_shown` is also what the GUI Pick table uses,
  so they cannot drift). results_rows reads db.events(lst) of the current series (raw values via db._cell, as the
  CSV export) with report dedupe + mag sort; favorite_rows from favorites.load(). Written to
  cache_path/pyoccult_exports, utf-8-sig. Keep event_shown in step with report.html_row / html_row_body.
- `pyoccult/stellarium.py` (2026-10-08): Stellarium Remote Control plugin (`URL_STELLARIUM_API`, port 8090, HTTP POST
  form fields via `net.urlopen`): location/setlocationfields (if KSTARS_OPT set_location) -> main/time (time = JD
  UT, timerate=0) -> main/view (j2000=[x,y,z]) -> main/fov. Never raises. GUI route `/api/stellarium/show`; report
  `.stbtn` shown whenever served over http (no status check: blind try, toast). Verified with a running Stellarium.
- `pyoccult/favorites.py`: favorites in `favorites/` (private, gitignored): `favorites.json` (entry = hits_log record,
  site and run context from the run summary, status, note) and `favorites/<target>_<YYYYMMDDTHHMM>/` with copies of
  KML and preview SVG. Report: hidden `.favbtn` stars, shown only via the GUI (`/api/favorites/keys|add`; add looks
  the event up in hits_log.csv by target + minute, site from the last run summary). GUI tab Favorites: iframe of
  `favorites/favorites.html` (`write_page`: report `to_html` with `meta["favorites"]`, rows get `e["fav"]`/`e["site"]`;
  select boxes, Site/Status/Note/Added, per-row KStars site) rebuilt after every change; mass actions call
  `/api/favorites/update|remove|cleanup`; row click -> `parent.emitEvent('fav_select', key)` -> detail panel (preview,
  map from the KML copy, size line, status, note). Entry key `phys`: the pyoccult.sbdb cache data (H, G, diameter,
  diameter_sigma, extent, albedo as (value, ref)) copied at add time (/dev/shm cache is volatile); GUI start
  backfills it for older entries. `favorites.csv` is rewritten by every `_save` (flat: key/status/note/added/site,
  all record columns, sbdb_*, file paths).
  Event summary (0.14.x): `favorites.event_info(entry)` -> [(group, [(label, value)])] like OWC's event page
  (Prediction/Event/Star/Object; astropy TETE for the apparent place, get_constellation), shown as a 4-column
  grid in the GUI panel. Record fields from `search.event_context` (end of the record); `backfill_event` (GUI start)
  fills older favorites from one Horizons OBSERVER query (quantities 3,20,23) + KML minute marks ("~" = approximate).
  sbdb `entry_from_api` keeps the orbit solution as phys "orbit" (PHYS_KEYS); get_full refetches entries without it.
  Error ellipses: `pyoccult/ellipses.py` (x east, y north, mas; PA north->east; cov/ellipse/add/star_ellipse/
  across_track/svg). Target: `paths.path_error` (Horizons q37: PA = 90 - Theta, verified = OWC) -> record ast_err_*;
  star: Gaia online check (doubles ERROR_COLS) -> star_err_*; favorites `backfill_errors` (GUI start, daemon
  thread: Gaia may hang; `err_checked` once both answered), `error_svg` -> data URI img in the panel.
- OWC twilight events carry the Sun altitude after the time ("☼ -5°"); `read_owc` parses it (`sun_alt_deg`) and then
  sets MAX_SUN_ALT to the brightest + 1 (fixed 2026-10-04: before, such lines were silently skipped).
- OWC online computes at sea level (ignores the site elevation); `pyoccult/owc_check.py --sea-level` sets ELE = 0 for
  a like-for-like check. Effect up to h x cos(star alt) across the track (958 m: up to 0.9 km).
- `pyoccult/owc_check.py` + `owc_reference.txt` (private, not in git: names the site): an OWC search result pasted as
  text; the script parses events and filter settings, reruns pyoccult/search.py at the sites.py site and compares.
- `owc_refs/` (private, not in git): stored OWC search results (`<site>_<date>_<filter>.txt`, `--ref` for
  pyoccult/owc_check.py) with the matching pick runs (`.pick.csv/.log`) and a README of settings and findings. Keep
  adding sets there; never delete them.
- `VERIFICATION.md` (2026-10-08): all validation (OWC sets, Occult star positions, internal/geometric checks, what the
  differences mean); ABOUT Part 5 is a summary with a link. New OWC reference sets: add the numbers there (sites
  unnamed: "the observer's site", "a second site") and the details to `owc_refs/README.md` Full lists:
  `pyoccult owc-check --markdown <set>.list.md` (`--compare-only --hits <saved csv>` for a stored run); markers ✅ 🟠
  (|dt| > WARN_T 1.5 s) 🔴 🔵.
- `CONTRIBUTING.md`: fork/branch workflow, setup, tests, working with Claude Code, private files, pull requests,
  GPL-3.0-or-later for contributions. `LICENSE` (GPL-3.0 text), `CITATION.cff` (validated with cffconvert).
- `tests/`: stand-in based tests, run each with `python tests/<name>.py` (no SPICE, astropy or network needed).

## Conventions that matter
- Asteroid position: `spkpos(id, et, 'J2000', 'CN', '399')`. Earth centre is 399, not 3. `CN` is astrometric (matches Gaia).
- Star direction (0.10.0): `pyoccult.astrometry.corrected_star_dir` in `handle_star`, once per candidate at et_guess:
  Gaia (propagated) + stellar parallax + light deflection by Sun/Jupiter/Saturn as star MINUS asteroid (asteroid stays
  SPICE 'CN'). Switches `star_parallax`, `light_deflection` (off = old results exactly). Log `star_ra/star_dec` are the
  corrected direction; `corr_parallax_mas`, `corr_deflection_mas`. Not in the pick screen yet.
- Fundamental plane: z toward the star, x east = (0,0,1) x z, y north. Miss distance = hypot(dx, dy) in km.
- Observer longitude is east-positive, geodetic, radians inside the solver.
- Target ids are strings of the asteroid number ('218001'); the SPK is aliased with `boddef` in `fetch_target_orbit`.
- `observable()` returns a tuple `(ok, star_alt, sun_alt)`; always index it. `if not observable(...)` is always False.
- `mag_drop` is the change in combined brightness (`m_ast - m_before`), never smaller than `m_ast - m_star`.
- Drop of at least `d` needs the star no fainter than `m_ast + 2.5*log10(1/(10^(0.4 d) - 1))` (2.54 mag for 0.1).
- SPICE is not thread-safe: use processes, load kernels per process, never call spice from threads. Start worker
  processes with `spawn` (`mp_context=multiprocessing.get_context("spawn")`), never `fork`: forked workers inherit the
  parent's open kernel files and share their read position, so parallel reads of de440.bsp collide
  (SPICE(RECORDNOTFOUND) "corrupted DAF", SPICE(INVALIDRADIUS)). Linux defaulted to fork up to Python 3.13 (3.14:
  forkserver), macOS uses spawn; found on a 14-worker server with Python 3.13 (2026-10-05). Network-only code
  (Gaia/Horizons fetches) may use a few threads.
- Gaia bulk files: `https://cdn.gea.esac.esa.int/Gaia/gdr3/gaia_source/` (note `esac`); the listing is an S3 bucket at
  `https://gaia.eu-1.cdn77-storage.com/?prefix=Gaia/gdr3/gaia_source/&delimiter=/`. Files are `csv.gz` with `#` comment
  lines and `null` for missing values.
- Gaia archive: synchronous `Gaia.launch_job` silently truncates at 2000 rows (`Gaia.ROW_LIMIT = -1` does not lift
  it). Windows mode (cone searches): `launch_job_async`. Online double check and star errors (doubles.py): synchronous
  in chunks (50 events / 1000 source_ids, far below the cap; a chunk reaching 2000 rows is reported), because the
  async job's status polling hung for minutes in 2026-10 while sync answered in ~5 s.
- Standard-library web requests go through `pyoccult.net.urlopen` (SSL context with certifi's CA list): some Pythons
  (macOS) have no CAs for urllib -> CERTIFICATE_VERIFY_FAILED, while requests (own certifi) works. Never call
  `urllib.request.urlopen` directly; test stand-ins must accept `context=`.
- Every download/web address lives in `pyoccult/urls.py` (`URL_*` names; no side effects, so setup/geo/kernels/report
  can import it before a sites.py exists). Never hard-code an http(s) address elsewhere; exceptions: XML namespaces
  (SVG, KML) and `pyoccult.version.__url__`. Tests that exec code excerpts must put `U` (pyoccult.urls) in their ns.
- Write cache files atomically (temp file + `os.replace`). Every cache (asteroid SPKs, SBDB bulk list, per-asteroid SBDB size data
  `PyOccult_sbdb_phys.json`; both SBDB caches refetched after `sbdb_max_age_days`) goes to `config.cache_path`
  (`/dev/shm` if present, else the system temp folder); never hard-code a path. Gaia is not cached: corridor mode
  reads the local catalog, the old windows mode queries the archive uncached.
- Earth PCK coverage: `pck_comment_dates` reads "Creation date" and "UTC Epoch of last datum" (end of measured EOP)
  from the file's comment block; `pckcov` gives the end of the prediction. Run summary key `earth_pck`; a search window
  past the end exits at start-up.
- Worker pools call `pick.single_thread_workers()` before starting (OPENBLAS/OMP/MKL_NUM_THREADS=1 via setdefault,
  inherited by spawn): OpenBLAS otherwise starts a thread per CPU in every worker (4 workers on 8 cores: load 24,
  each worker ~40 % CPU; found 2026-10-10 in a pre-screen build).
- SpiceyPy `surfpt` returns only the point and raises `NotFoundError` on a miss.
- Tests use stand-ins for spiceypy/astropy/astroquery that follow the real call contracts; keep them honest when changing
  signatures.

## Status
- Validated 2026-10-02 (`pyoccult owc-check`, 16 OWC events at the user's site, Oct 2-9): all 16 found, same
  stars (our G equals OWC's "V" column to 0.01, so OWC shows Gaia G), times within 5.4 s (13 within 3 s). Drops match within
  0.25 mag below 5 mag. Durations match within 10 % wherever both use the same diameter; 4 events differ only by
  diameter (H+albedo estimates, or OWC using another source than NEOWISE). Open: 218001 (OWC drop 1.56 mag, ours 12.97;
  OWC diameter 3.56 km, ours 1.77 km from H). Hypothesis, unverified: the 5.6 mag star's angular diameter makes it
  partial; not modelled yet (idea: Gaia `radius_gspphot`, `distance_gspphot`).
- Corridor search is merged into `pyoccult/search.py` (`handle_star` shared by both modes, `target_test_corridor`, 2-pass driver;
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
- Not run against live services: Horizons RSS 3-sigma column names in `pyoccult/paths.py`.
- Pick tool validated 2026-10-01: blind screen of all 465k asteroids (H < 17), Oct 1 + 8 d, 20 km reach, min alt 5:
  39 events incl. all 13 OWC reference events with H < 17 (same stars, times within 5 s, drops/durations as
  pyoccult/search.py); 819762 (H 18.45) needs `--all`. 875 s in one process, 318 s with 4 workers, same events.
  SBDB bulk elements MUST be full precision (`full-prec=true`): rounded ones give ~40" errors.
- Report map: OpenStreetMap tiles only (`--tile-url`), so it works through a web server (OSM needs a Referer), not
  from `file://`. Map dialog reopen bug fixed 2026-10-02 (the box was cleared on every open, removing Leaflet's panes).

## Ideas not built yet
- Star angular-diameter model for the drop and duration.
- Astrometric corrections in the pick screen (built for the search in 0.10.0; pick screen still without).
- Process-level parallelism by target (`ProcessPoolExecutor`; parent does kernel checks, Horizons SPKs and opens the local Gaia catalog;
  workers return records, parent writes the CSV).
- `m_before` / `m_during` columns in the log.
- Favorites, next steps (simple version built 2026-10-04, see Files): re-predict one favorite with the latest orbit
  (single-target search; keep old map/preview versions next to new ones), export (CSV, KML bundle, report page),
  share/pull with Occult Watcher Cloud (campaign events, multi-site chords; how TBD, no known public OWC interface;
  findings 2026-10-06: OWC Cloud is a JS app over a private REST API `https://www.occultwatcher.net/api2/v1/...`
  (login), its profile can issue a per-user API key / OAuth client (undocumented), deep link
  `api2/ext/locate?ast=&tag=&date=` (or `&occelmntId=`: Occult element id); no public export/iCal. Plan: ask H. Pavlov
  for API docs and permission, never scrape with the user's login. Without it: prediction feeds (IBEROC etc., Occult
  elements read by OW desktop) may be public files to mark campaign events; the user plans this with the community),
  observation data per favorite (result, D/R times, chord, link to the SODIS report from DVTI+CAM / ASTRID).

