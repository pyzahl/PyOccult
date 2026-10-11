# Changelog

All notable changes to PyOccult. Newest first. Format: [Keep a Changelog](https://keepachangelog.com), versions:
[semantic versioning](https://semver.org) (MAJOR.MINOR.PATCH). The version and its code name live in
`src/pyoccult/version.py`; the code name changes at major milestones. Details of the computations: `ABOUT.md`.

## [Unreleased]

### Added
- GUI Site tab: coordinates pasted as text into Latitude, Longitude or Elevation are parsed (`geo.parse_coords`):
  labels in any order (lat/latitude, lon/lng/long/longitude, alt/elevation/height, also German), degrees-minutes-
  seconds, decimal minutes or decimal degrees, N/S/E/W or signs, heights in m/ft/km; without labels latitude first
  (as Google Maps copies them). All three fields are filled, the map marker moves, a missing elevation is looked up.

## [0.16.0] "New Horizons" - 2026-10-10

Picks in seconds instead of minutes: a pre-screen does the site-independent part of a pick (which asteroids can put
a star's shadow on the Earth at all) once for a window and stores it, for a region or for the whole Earth. A
whole-Earth pre-screen stores each event's shadow path (Besselian-element style), so any site, or any region cut from
it, is tested in seconds; for a 4-day window the pick with it gave exactly the full pick's events in 14 s instead of
210 s. In the GUI, "Asteroids: auto" uses a fitting pre-screen by itself, and a Pre-screens panel builds and lists
them. Picks and builds also run up to 2.4x faster with one math thread per worker.

### Added
- **Pre-screens** (`pyoccult/prescreen.py`, `pyoccult prescreen build|list|show|query|extract|index`): the asteroids
  with possible occultations in a window, using the pick's own parts (SBDB elements, orbits, bright-star index,
  candidate scan) for the whole Earth plus each candidate's ground track (161 samples, the Earth's rotation from SPICE).
  Regions: a box around the site (`--around-site KM`), one box around all sites of sites.py (`--around-sites KM`,
  the short way round across the date line), named regions (`--region usa|europe|south-america|...`) or a lat/lon
  box. A strict superset of what any fitting pick finds: every test is widened by what can change between samples,
  and the reach, a distance in the fundamental plane, is turned into the exact largest ground distance of an
  observer (`shadowtrack.ground_reach`: up to 1/sin(star altitude) longer); the orbit grid reaches 12 h beyond the
  window, so events whose track touches it are found. Checked against dense sampling and the exact site test at many
  sites (VERIFICATION.md).
- **Whole-Earth pre-screens** (`prescreen build --global`, new `pyoccult/shadowtrack.py`): per event the shadow's
  motion across the fundamental plane (star direction, quadratic in time, misfit; 80 bytes) in a time-sorted
  `.global.npy` + `.json`, at about the cost of a region build (~1 GB per month at G 16 for 465k asteroids). An
  **index** (`.idx.npy`, written after the build; `prescreen index` for older files) holds each track's lat/lon box
  and star altitude range, so a site or region query tests only the events that can reach it (14-26 %).
  `prescreen query` (asteroids for the site), `prescreen extract` (a region file, optionally shorter window and
  brighter star limit, e.g. a continent to share).
- **Picks with pre-screens**: `pick --prescreen FILE|auto`; auto takes the newest pre-screen that fits the site,
  window and limits, else screens all asteroids and says why none fits. Only the pre-screen's asteroids with an event
  in the window and a star within the pick's star limit are screened (a whole-Earth file: those passing the site
  test). `targets.py` notes which asteroids were screened. Same events as the full pick (checked).
- **Pre-screen builds fit the free memory and resume**: chunk size and workers from the available memory and a
  measured model of the NumPy arrays; chunks shrink when memory runs low; every chunk is committed to `<name>.partial`
  and the same command resumes after a crash, Ctrl-C or the GUI's Stop (`--fresh` starts over; a build of an older
  format is refused with a clear message). Verbose progress: the plan, then per chunk rate, ETA, free memory, swap
  and worker memory. Stop ends the workers at once. The candidate scan and ground tracks run in bounded blocks.
- GUI Pick tab: "Asteroids" = auto (default) / all (any place and time) / a fitting pre-screen, with a line saying
  what the pick will screen; a "Pre-screens" panel to build one (start, days, region: this site, all my sites, whole
  Earth; box km; Start over) with its progress in the log, and a table of the built ones (window, region, sites
  inside, limits, asteroids/events, age, fits this pick or why not) with delete.

### Fixed
- Pick workers use one NumPy (OpenBLAS) thread each: before, every worker started one thread per CPU (4 workers on
  8 cores: 32 busy threads, each worker at ~40 % of a CPU); a pre-screen build ran 2.4x faster with the fix.

## [0.15.0] "New Horizons" - 2026-10-10

The favorites panel now summarises each event like OccultWatcher Cloud's event page (prediction, event, star,
object; checked against OWC), with the sky-plane uncertainty ellipses of the target, the star and both combined in one
diagram. All verification is in the new VERIFICATION.md, with the full lists of two 50-event OWC comparisons. Also:
the GUI remembers its site and catalog, a target unknown to JPL Horizons no longer stops a search, and maps no
longer show a false second path for tracks across the date line.

### Added
- GUI: the site and catalog chosen at the top right are remembered across restarts (`gui_state.json` in the
  data folder, private); a site or catalog that no longer exists falls back to the default.
- **VERIFICATION.md**: all checks in one place (OWC search results, Occult's star positions, internal and geometric
  checks, what the differences mean), moved out of ABOUT.md Part 5 (now a summary with a link), with a new OWC set
  (Oct 8-11 2026, 50 events: 44 match; two events on Gaia 2-parameter stars the local catalog leaves out, one small
  asteroid's orbit, three drops by the asteroid's brightness) and the full lists of both 50-event sets (matches,
  misses, extras, time differences over 1.5 s marked). ABOUT.md has a table of contents.
- Favorites panel: an **event summary laid out like OccultWatcher Cloud's event page** (Prediction, Event, Target
  star, Object): orbit solution (JPL# and date, from SBDB), path error in path widths and in time, the times the
  shadow is on the Earth (From/To), combined magnitude, solar and Moon elongation, Moon phase, constellation, the
  star's ICRS and apparent (true equator and equinox of date) position, the target's angular diameter, distance and
  motion. Checked on 369152 (Oct 12 2026) against OWC: From/To within 1 s, distance, elongations, star positions
  (apparent within 6 mas) and magnitude as OWC. The search logs the new values with each event (`dist_au`,
  `motion_ra_ash`, `motion_dec_ash`, `sun_elong_deg`, `m_combined`, `shadow_from_utc`, `shadow_to_utc`); older
  favorites get them once from JPL Horizons at GUI start (From/To then from the map's minute marks, marked ≈).
  Not available locally, so not shown: the star's V/R/B magnitudes, its diameter and RUWE (the local catalog keeps
  RUWE < 1.4), and the error ellipse (Horizons gives its RSS size).
- Favorites panel layout: title "<asteroid> occults <Gaia DR3 star> around <time> UT at <site> (lat, lon, height)"; the four
  groups (Prediction, Event, Star, Object) in a larger font, the Object group with H, albedo, shape and rotation and
  the known satellites, the Star group with RUWE and the close/double-star check; the uncertainty-ellipse diagram at the
  bottom left next to status and note. The separate lines for site, size, shape, double star and satellites are
  gone (now in the groups). When Gaia's errors for the star are not at hand (archive not reached, 2-parameter
  source), the diagram uses a typical Gaia DR3 star of that G (Lindegren et al. 2021), marked "!".
- Favorites panel: the **sky-plane 1-sigma uncertainty ellipses** of the event in one diagram, titled "Uncertainty
  ellipses (sky plane, 1σ)", at one scale (as OWC's
  "Error Ellipses", but overlaid): the target's (JPL Horizons SMAA/SMIA/Theta), the star's (Gaia DR3 position and
  proper-motion errors with their correlations, carried to the event date; at true scale usually a dot) and the
  combined one, with the target's motion and the **error across the track** in mas and km (only that part shifts
  the path). Checked on 369152 against OWC: target 28.00 x 22.33 mas @ 94, star 0.28 x 0.26 mas @ 90, combined
  28.00 x 22.33 mas @ 94 (OWC 22.30); with Gaia's correlations, which OWC seems to leave out (without them
  ours equals OWC's), the star's ellipse is 0.30 x 0.22 mas @ 126 (1 % of the target's). The search logs the target's ellipse (`ast_err_*`), the Gaia online check
  the star's (`star_err_*`); older favorites get them once at GUI start (Horizons, one Gaia job, in the
  background). New module `pyoccult/ellipses.py`.
  The diagram also shows the target's disk at its angular size and the star where it stands as seen from the site
  at closest approach (its ellipse again, dashed, with its track relative to the target): from the logged offsets
  of the shadow axis, so its distance from the centre is the site's distance from the centre line (in mas and km,
  "inside" or "outside" the shadow). A star more than 2 shadow widths outside is not drawn (the diagram does not
  zoom out for it); the legend gives its distance.
- `pyoccult owc-check --markdown FILE`: the full comparison as a Markdown table, by star magnitude (every OWC event
  and PyOccult's extra events, marked); `--hits FILE` compares a saved hit list (with `--compare-only`).

### Fixed
- Maps (report, favorites): a shadow path across the date line showed a false second path, a straight band
  along one latitude across the whole map (the step from -179.8 to +178.8 deg drawn the long way round). Longitudes
  are now continuous along each line, placed next to the observer. The KML files themselves were right.
- Gaia online check (close and double stars, now also the star's errors): synchronous queries in chunks instead of
  one asynchronous job, whose status polling hung for minutes (October 2026) while the synchronous query answered
  in seconds.
- Search: a target JPL Horizons does not know (e.g. a mistyped asteroid number) stopped the whole run with a
  traceback. It is now skipped with a one-line reason, the others are searched, and the run summary lists it
  (`skipped_targets`).
- `owc-check`: OWC tag words in capitals (e.g. "IBEROC") are no longer taken as part of the asteroid's name.

## [0.14.0] "New Horizons" - 2026-10-08

**Planets and moons** join the asteroids as occulting bodies: Mars to Neptune, Pluto and 91 of their moons, in
their own GUI tab with disappearance and reappearance times. All results now live in one **results database**
(`pyoccult.db`). Also new: Stellarium pointing, a column file for the CSV downloads, the star limit per run in the
Search tab, and the search corridor in the previews. Nothing to do after updating: an existing `hits_log.csv` and
`favorites/favorites.json` are imported into the database once.

### Added
- **Planets and moons as targets** (`pyoccult/bodies.py`): `P:Mars`, `P:Jupiter`, ... `P:Neptune`, `P:Pluto` and
  moons such as `M:Io`, `M:Titan`, `M:Himalia`, `M:Triton`, `M:Charon` in the target list (the prefix keeps them
  apart from asteroid numbers; `python -m pyoccult.bodies` lists them). Positions from JPL Horizons as a small SPICE
  kernel per search window (cached; the same ephemeris as NAIF's satellite kernels, reproduced to ~1 m), radii from
  the planet constants. Events get **disappearance and reappearance times** at the site (`d_utc`, `r_utc`, also as
  contacts in the database); verified: D and R put the star exactly one Jupiter radius from its centre in
  independent geometry. A star covered by a planet disappears, so planets have no drop limit; moons and Pluto
  follow the asteroid rules (drop limit). The light deflection leaves out the target's own planet.
- Satellite table `src/pyoccult/data/satellites.json`: all 458 moons of Mars to Pluto known to JPL Horizons, with
  radius and brightness (H with the phase removed, H-G law with G 0.5; within ~0.2 mag of published values for the
  major moons, Phobos ~1 mag). 91 can be searched; a missing size or brightness is estimated as for asteroids
  (marked \*); the rest (mostly tiny, recently found moons of magnitude 22-25) have neither. Rebuilt with
  `python -m pyoccult.bodies build`. Rough 3-sigma path uncertainty by size (15-200 km) for the sigma lines and
  the chance.
- GUI tab **Planets & Moons** (after Pick): per system the planet and its larger moons (radius 150 km or more) to
  tick, one box for its smaller moons; window, star G limit, the moons' minimum drop, Run. Results right in the
  tab as their own list (`bodies_log.csv`, list "bodies" in the database, apart from the asteroid search) with a
  report layout for major bodies: D, closest approach and R at the site, duration, star, sky, shadow distance,
  chance, tools. Previews show the planet and its moons as disks at their size, zoomed to the system, each moon
  marked with a small cyan **+** whatever its size. File and favorite names use `P-Jupiter` (no ':' for Windows).
- Optional offline ephemeris: `pyoccult setup --planet-kernels` (also asked on a first-time setup) downloads NAIF's
  satellite kernels (Jupiter `jup365.bsp` 1.1 GB, Saturn `sat441.bsp`, Neptune `nep097.bsp`, Pluto `plu060.bsp`,
  Mars `mar099.bsp`), used instead of Horizons when they cover the search window.
- **Stellarium** button next to KStars in the Results and Favorites tables (`pyoccult/stellarium.py`, any
  system): through Stellarium's Remote Control plugin (port 8090) it sets the event time with the clock stopped,
  the view on the star and the field, and with "KStars/Stellarium: set its location to the event site" the site.
  Shown whenever the GUI serves the report; a click tries and reports. Also `pyoccult stellarium`.
- **CSV columns file** `csv_exports.py` in the data folder (`pyoccult/exports.py`, template
  `templates/csv_exports.py`, created at the first download): which columns the CSV buttons of the Pick, Results,
  Planets & Moons and Favorites tabs export, in which order and with which headings. Default: exactly the table's
  columns and values as shown; any raw field of the event record (`"raw:star"`, ...), all of them (`"*"`) or a
  function can be added. UTF-8 with byte order mark for spreadsheets.
- GUI Search and Planets & Moons tabs: **Star G limit** for one run (as in the Pick tab; default from the site's
  telescope, capped at the selected catalog's limit). A search notes when `gaia_local_gmax` in your
  `pyoccult_config.py` caps the limit below the catalog's (older configs have 13).
- Event preview: the **search corridor** (the strip searched for stars: Earth radius + body radius + reach, at the
  event distance) as dotted lines on both sides of the track, with its half-width in the legend.

### Changed
- **Results database** (`pyoccult/db.py`): searches and favorites are stored in `pyoccult.db` in the data folder
  (SQLite, part of Python): every run with its summary, every event, and the favorites. "Start a fresh hits_log.csv"
  became **Start a fresh results list**: a new list (series) begins, the older ones stay in the database instead of
  being deleted. `hits_log.csv` / `bodies_log.csv` and their `.runs.jsonl` are still written after each search, as
  plain-text copies of the current list with consistent columns (the reports and other tools read them). An
  existing `hits_log.csv` and `favorites/favorites.json` are imported once (the latter kept as
  `favorites.json.migrated`).
- The CSV buttons export the table as shown (see the columns file above) instead of the raw log with all columns;
  Results, Planets & Moons and Favorites are exported from the database. The full files stay: `hits_log.csv`,
  `bodies_log.csv`, `favorites/favorites.csv`.
- The KStars location checkbox of the Results tab is now "KStars/Stellarium: set its location to the event site".

### Fixed
- A minimum drop of 0 stopped the search with "math domain error" (now: no drop limit).
- A star limit set for a planet run was capped by `MAG_MIN` (G 13 with older configs), so faint stars were never
  searched; the separate planet star limit is gone, the run's Star G limit applies.
- The asteroid size lookup (SBDB) is no longer tried for planet and moon targets.

## [0.13.0] "New Horizons" - 2026-10-07

A standard Python package now (`pyproject.toml`, code in `src/pyoccult/`, one `pyoccult` command; install with
`pip install -e .` or run with `uv run pyoccult`): **after updating, run `pip install -e .` once** in your virtual
environment, or use uv. New reference information with each event: close and double stars, known asteroid
satellites, earlier occultations; plus the camera list, the data folder setting and several fixes.

### Changed
- Default Gaia catalog G <= 16 (`gaia_dr3_g16`, 2.1 GB download, ~3 GB on disk; enough for most amateur
  telescopes): template `gaia_local_dir`/`gaia_local_gmax`, setup's limit question (Enter = 16) and the pick's
  default catalog. Before, the template capped the star limit at G 13 (`gaia_local_gmax = 13.0`). G 18 stays
  available (`pyoccult setup --gmax 18`). Your own `pyoccult_config.py` keeps its values.
- **Standard Python package** (PEP 517/518/621, src layout as PyMovie and PyOTE use): `pyproject.toml` replaces
  `requirements.txt`; the code moved from the project root into `src/pyoccult/` with short module names
  (`pyoccult_pick.py` -> `pyoccult/pick.py`, `pyoccult.py` -> `pyoccult/search.py`, ...); imports are
  `from pyoccult import ...`. One command, `pyoccult`, starts everything: `pyoccult` (web interface),
  `pyoccult setup`, `pyoccult pick ...`, `pyoccult search`, `pyoccult report hits_log.csv`, `pyoccult owc-check`,
  `pyoccult gaia ...`, `pyoccult picks ...` (`pyoccult --help`; options unchanged); also `python -m pyoccult`.
  Your data stays where it is: the project folder is the data folder (`PYOCCULT_HOME` chooses another one).
  `pyoccult_config.py` is now your own file there (not in git): it is created from
  `src/pyoccult/templates/pyoccult_config.py` when missing, and settings it lacks keep the template's default.
  `sites_example.py`, the logo and the globe's map data moved into the package. Checked: tests on Python 3.10 and
  3.14, a clean install with uv (Python 3.10), and pick (spawn workers), search, report, setup and the GUI run
  through the new command from another folder.
  **Upgrading an existing install:** `git pull`, then once `pip install -e .` in your virtual environment (or
  `.venv/bin/python -m pip install -e .`); start the GUI with `pyoccult` (`.venv/bin/pyoccult`) instead of
  `python pyoccult_gui.py`. If you changed `pyoccult_config.py`, keep a copy before pulling (git removes the tracked
  file; PyOccult then recreates it from the template, so copy your changes back in).
- All download and web addresses moved into one file, `pyoccult/urls.py`, each with its own name (`URL_NAIF_DE440`,
  `URL_JPL_HORIZONS_API`, `URL_MPC_OBSCODES`, ...), so they are maintained in one place. A separate file rather than
  `pyoccult_config.py`, which reads `sites.py` when imported: setup and the report need addresses without it.
- GUI Site tab: the site list is now the Minor Planet Center's list of observatory codes (ObsCodes.html, ~2700
  observatories, downloaded once into `data/`, not in git; `pyoccult.geo.mpc_observatories`), searchable by code or
  name. It replaces Occult's site list of 0.12.0, which turned out to hold mainly reference cities. Positions and
  heights come from the MPC parallax constants (WGS84); for old entries with fewer than 5 decimals the height is
  looked up instead.

- Documentation: README table of contents, how to type the commands (uv, pip, alias), where data and settings
  live (data folder, setting, cache, per system); ABOUT.md 3.5 memory and CPU use of the pick (per worker ~0.5 GB +
  ~55 MB per day of window; NumPy threads per worker), 4.1 what Horizons/SBDB hold vs the occultation archive,
  4.2 asteroid satellites; open items for close and double stars (Part 6).

### Added
- Experimental, off by default: **Check OWC** buttons in the GUI's Results and Favorites tabs (`owc_lookup = True` in
  `pyoccult_config.py`; no GUI switch). They look the events up in OccultWatcher Cloud through the interface of its
  public event pages (`pyoccult/owc.py`; one request per second, PyOccult named as the client, only on click) and
  show the prediction feeds and signed-up stations under the asteroid, e.g. "OWC IBEROC · 2 stations", linked
  to the OWC event page (stations with distance and commitment on hover). Matched by the star's Gaia DR3 id, else
  by time; results cached in `owc_cache.json` in the data folder.
- Results and Favorites tables: a **Chance** column, the probability that the shadow covers your site, from the
  offset, the shadow radius and the 1-sigma path uncertainty (JPL Horizons' 3-sigma position uncertainty / 3, else
  `default_sigma3_km`), like Occult's "Rank" but for your site; sortable, details on hover. New hit-log columns
  `path_sigma1_km`, `sigma_source`, `p_site` (events logged before show "—").
- **Asteroid satellites** (`pyoccult/binaries.py`, `data/binaries.json`: 325 systems from W. R. Johnston's Binary
  Minor Planets Compilation V3.0, NASA PDS 2019, doi:10.26033/bb68-pw96, plus satellites seen in occultations):
  "+moon" / "+2 moons" ("+moon?": only reported in an occultation) after the asteroid in the Results and Favorites
  tables with sizes, distances and periods on hover, a "Satellites" line in the favorites panel, and a dotted
  **satellite zone** on the event maps (KML, report map, globe plot): the primary's shadow plus the largest known
  moon distance and radius, where a moon's shadow can pass (its position is not predicted). ABOUT.md 4.2.
- Favorites: the close/double-star check also for favorites added before it (filled in once at GUI start from the
  local catalog), shown in the favorites table (⚠ after the drop) and as a "close or double star" line in the
  detail panel.
- **Close and double stars** (`pyoccult/doubles.py`): each event checks the local catalog for neighbours within
  4" (`companion_radius_arcsec`) whose light stays in the camera image, and recomputes the drop with it
  (`mag_drop_blended`; the report shows e.g. "3.61 ⚠ 3.31" with details on hover when the drop is 0.1 mag or
  more smaller). Optional online check after a search (`gaia_online_check`, default on, GUI Search tab): one query to
  the Gaia DR3 archive for all events adds Gaia's double-star hints for the event star (`non_single_star`,
  `ipd_frac_multi_peak`, `duplicated_source`, `ruwe`) and neighbours the local catalog leaves out; skipped when
  offline. New hit-log columns at the end (`blend_*`, `mag_drop_blended`, `double_hint`, `double_check`, `gaia_*`).
  Still open (ABOUT.md Part 6): known-double catalogs, events on stars the catalog drops (RUWE >= 1.4), step events.
- **Earlier occultations** of an asteroid in the favorites panel, e.g. "Occultations (NASA PDS archive, to 2023-12):
  8 events 1991-2021 (1 reliable size, ...); shape-model diameter 107.8 +- 5.6 km (6 events); best profile
  2008-06-06: 119.1 x 101.7 km". From NASA PDS Small Bodies Node "Small Bodies Occultations" V4.0 (Herald, Dunham et
  al., doi:10.26033/ehqs-jp27): a compact extract ships with PyOccult (`pyoccult/occultations.py`,
  `data/occultations_pds.json`, 2903 asteroids, 387 kB). Reference only; the prediction's size source is unchanged.
  ABOUT.md 4.1 explains what Horizons/SBDB holds (no chords) and what the archive adds.
- GUI Site tab: **Sensor (cameras)** list next to the MPC observatory list: 21 sensors common in occultation work, one
  entry each as "Sony IMX174: 11.34 x 7.13 mm, 1936 x 1216 px of 5.86 um (ZWO ASI174MM / MC, QHY174M-GPS, ...,
  DVTI+CAM 174)", with the ZWO, QHY, ASTRID, DVTI+CAM, Seestar and Unistellar cameras built with them, plus analog
  video formats. Searchable by sensor or camera name (e.g. "174", "QHY600", "ASTRID"); picking one fills sensor width
  and height (computed from pixels x pixel size; `pyoccult/cameras.py`). The Site
  form now has MagAdjust next to the focal length, and sensor width, height and detection frames in one row.
- **uv support** (as PyMovie and PyOTE): `uv run pyoccult` in the PyOccult folder installs Python 3.12
  (`.python-version`) and the exact package versions of `uv.lock` (Linux, macOS, Windows) into `.venv` by itself;
  then `uv run pyoccult setup` and `uv run pyoccult`. README: install steps for uv on each system (also from the
  GitHub ZIP, without git). The pip way still works.
- README: **Windows, step by step (with uv)**: installing uv, the ZIP (or git), a folder outside OneDrive, setup,
  start, an optional `PyOccult.bat` start icon, updating and removing. Not yet tested on Windows.
- **Data folder setting** for installed copies (pip/uv without a clone): the first `pyoccult setup` asks where to keep
  the data (Enter = `~/PyOccult`) and saves the choice in the system's settings folder (Linux
  `~/.config/pyoccult/home`, macOS `~/Library/Application Support/PyOccult/home`, Windows `%APPDATA%\PyOccult\home`);
  `pyoccult setup --home <folder>` changes it (for a clone too; files are not moved, setup says if the old folder
  holds your data). A clone keeps using its own folder; `PYOCCULT_HOME` still sets it for one run. The folder in use
  and why: `pyoccult setup --status`, the GUI's About box and start-up line.
- Pick: the asteroid's H in `pick_events.csv`, the saved picks and the Pick tab table (the "H below" limit is the
  most common reason an asteroid is missing from a pick).
- GUI Pick and Results tabs: a **CSV** button downloads the selected saved pick's events, or the search results
  (`hits_log.csv`, downloaded as `hits_<site>__<start>_<days>d.csv` from the last run, like the saved picks).
- GUI Pick tab: **Star G limit** (left of "H below"), the pick's star limit, computed from the site's telescope (as "Stars searched
  to G" in the Site tab) and capped at the selected catalog; it can be changed for one run (`--cam-limit`). Before,
  the GUI pick used the config's `MAG_MIN`, which `gaia_local_gmax` can cap lower than the site allows.
- GUI Site tab: **Add as new site** next to the MPC list: adds what the map and form show as a new site to the site
  selector and saves it at once (it is then selected for all runs).
- GUI Site tab: **Remove site** deletes the site selected at the top right from `sites.py` (asks first, saves at
  once; the last site cannot be removed; if it was the default for command-line runs, another site becomes it).
- Results, Favorites and Pick tables: an **\*** after the asteroid name marks a size estimated from H with an
  assumed albedo (no measured diameter; uncertain by a factor of about 1.7); hover text and a note below the table.
- Favorites detail panel: a **shape and rotation** line (axes from SBDB `extent`, rotation period, pole, taxonomic
  type) where SBDB has them. Favorites get SBDB's full per-object record once (`pyoccult.sbdb.get_full`; the pick
  tool's bulk rows hold only size fields); older favorites when the GUI starts.
- Site key `mpc_code` (the official MPC observatory code), a **MPC code** field in the GUI Site tab (filled in when
  an MPC observatory is picked), shown in the report header and kept in the run summary.

### Fixed
- A minimum drop of 0 (no drop limit) stopped the search with a math error in the star limit; it now means "no cap".
- Web lookups with Python's standard library (OWC check, place/elevation/IP lookups and the MPC list, the full SBDB
  record for favorites, the pick's SBDB download) failed on Python installations without certificate authorities
  (often macOS: "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate"), while the browser worked. They
  now use certifi's list (installed with requests) via `pyoccult/net.py`. OWC check failures name the request and
  the error in the GUI log.
- Results and Favorites tables were wider than the page (the right side looked cut off; its scroll bar was only at
  the table's end): tool buttons and column headings may wrap, the asteroid name and offset too, tighter cell
  padding, the calculation-time column dropped (it stays in `hits_log.csv`), and on windows narrower than about
  1180 px the favorites' Note and Added columns are hidden (both are in the detail panel). Both tables fit a
  1280 px window.
- GUI: the Favorites table's height (drag the corner) was sometimes restored as a sliver after a restart: it was saved
  on every size change, including the box's minimum height while the tab was laid out. Now it is saved only after
  you drag, as a share of the window height, and restored only between 25 and 92 % of the window (else the
  default, 60 %). The Results report (default 75 %) and the Pick table (55 %; all rows in one scrollable box instead
  of pages of 15) got the same resizable box, each remembered separately in the browser.
- Favorites tab: the check boxes' mass actions (**Remove**, **Set status**, the "selected" count) did nothing since
  0.12.0: the times selector's script variable `sel` replaced the selection helper `sel()` of the same script
  (seen as "cannot remove a favorite"). Renamed; the favorites test now guards against it.
- README: the logo at the top pointed to its old place in the project root (moved into `src/pyoccult/`).
- GUI Favorites tab: the **CSV** download was saved as "true.csv" (the link's `download` attribute); it is now a
  button like in the Pick and Results tabs and saves `favorites_<date>.csv`.
- Pick tool with a star limit above G 15 (now easy to reach with the GUI's **Star G limit** field): the deeper
  bright-star index it needs (`bright_G16.0.v2.npy`, ...) was built by every worker at once, each reading the whole
  catalog into memory, so the system ran into swap and the browser stalled. The pick now builds a missing index once,
  before starting workers, and the build is low-memory (three passes through a memory-mapped file; peak about one
  catalog file or block instead of the whole index). Same index as before (checked on G <= 15: identical).
- GUI: when the browser page was lost during a run (stalled, closed, reloaded), the GUI stopped reading the run's
  output, so the process blocked and every later run was refused as "already in progress". Output is now read to the
  end without the page (results still go to their files, e.g. `picks/`); the page reconnect timeout is 60 s.
- Setup with an unreachable or blocked address (offline, server down, proxy or firewall): instead of a traceback it
  stops with a message (the address, the proxy setting `https_proxy`, rerun to resume, the other catalog source,
  copying files from another computer). Kernel downloads use `curl -f` into a `.part` file (before, a proxy's error
  page or a broken download was saved as the kernel); a failed refresh of the Earth orientation file keeps the older
  copy. The ESA build detects a proxy page instead of the file listing, skips a file that fails after its retries
  (the rerun fetches it) and stops early when the first files all fail.
- Pick tool: events near sunrise or sunset (or near the altitude limit) could be lost. A candidate was kept only if
  the asteroid was visible at the sample of its Earth-centre time estimate, but the event at the site can be 10-40 min
  from it (e.g. 539175 on 2026-10-09: estimate 06:00 UT with the Sun at +4 deg at Seewis, real event 05:26 UT with
  the Sun at -1.6 deg). A candidate is now kept if the asteroid is visible anywhere in its solver window, as in the
  search; the exact star and Sun altitude at the solved time are checked as before.
- GUI Site tab: after picking a second MPC observatory, the proposed site name kept the first one, so **Add site**
  stored e.g. Trieste's position under "000 Greenwich"; the name now follows each pick (a name you typed is kept).
  Adding a site no longer overwrote its description with the site name.
- `linux_install.sh`: ran `.venv/bin/activate` as a command (no effect), so `pip install` went to the system Python
  (refused as "externally-managed-environment" on Debian/Ubuntu) and setup and GUI ran without their packages. It now
  calls `.venv/bin/python` directly, finds `python3`, stops at the first error, hints at `python3-venv`, and can be
  rerun.

## [0.12.0] "New Horizons" - 2026-10-05

### Fixed
- Pick tool with several workers on Linux with Python 3.13 or older: workers were started with "fork" and inherited
  the parent's open SPICE kernel files, so parallel reads of `de440.bsp` collided (SPICE(RECORDNOTFOUND) "corrupted
  DAF", SPICE(INVALIDRADIUS)); seen with 14 workers on a 28-thread server. Workers now always start with "spawn" and
  open their own kernels (Python 3.14 and macOS were not affected). Reproduced with `--mp-start fork` and 12 workers,
  fixed with the default spawn. `--mp-start` (spawn, forkserver, fork) is kept for diagnosis.
- Results and Favorites tables: sorting by Asteroid is numeric by its number (20 before 100), not alphabetic.

### Added
- GUI Site tab: **Occult/OWC site list**, a searchable list of Occult's ~800 reference places and observatories
  (InstallSites.zip from occultations.org, downloaded once into `data/`, not in git; `pyoccult_geo.occult_sites`).
  Picking one sets position, elevation and description and proposes it as a new site name (**Add site**).
- Favorites table: a **times** selector shows the event times in UT (default), in this computer's time zone
  (Local) or in each event site's time zone (Site, e.g. "2026-Oct-12 00:47:46 GMT+2 (Zurich)"), with daylight saving
  time; remembered in the browser, sorting unchanged. Site time zones are looked up once per site (Open-Meteo,
  `pyoccult_geo.timezone`) when a favorite is added, and for older favorites when the GUI starts.

### Changed
- GUI: the start date of the Pick and Search windows defaults to today (UTC) instead of `ct` from
  `pyoccult_config.py` (which stays the default for command-line runs).

## [0.11.1] "New Horizons" - 2026-10-05

First GitHub release with a Zenodo DOI: 10.5281/zenodo.23149372 (this release; all versions:
10.5281/zenodo.23149371). Tags `V0.11.1-NewHorizons` and `V0.1.11-NewHorizons` (same commit).

### Fixed
- Globe plot, color style: land masses mostly on the far side of the Earth could flood the visible disk with land
  colour (e.g. Africa/Eurasia when the view is centred on the Americas or the Pacific). Land is now drawn with an
  extended orthographic projection (the far side continues beyond the disk edge) clipped to the disk; a land mass
  containing the far-side point is detected by its orientation and filled as the outside of its outline. Checked on
  nine views around the globe and on the reported event (84851, 2026-10-18).

## [0.11.0] "New Horizons" - 2026-10-04

The code name: PyOccult's orbits come from JPL Horizons, and the New Horizons mission measured its flyby target
Arrokoth beforehand with stellar occultations observed around the globe.

### Added
- Globe plot (`pyoccult_globe.py`): an Occult-style event plot per event, `maps/<event>_globe.svg`. The whole Earth
  as seen from the star at the event time with the shadow path (centre line, shadow limits, 1- and 3-sigma limits,
  minute marks), the shadow axis off the Earth, the site, and a header with Occult's parameter set (star position as
  used and of date, durations, time per km and per mas, drop, Sun and Moon, 1-sigma error, asteroid size, parallax,
  hourly motion) plus a 2 deg star chart. Style `"color"` (sea, land, night side, like OWC's globe) or `"lines"`
  (black on white, like Occult). Config `write_globes`, `globe_style`. Checked against Occult's plot of 30819.
- `data/ne_110m_earth.json`: coastlines, borders and land from Natural Earth 1:110m (public domain).
- **Globe** button in the Results and Favorites tables, a Globe link in the favorites detail panel; favorites keep
  their own copy (and pick it up from `maps/` for older favorites).
- Links in the tables: the asteroid name to the JPL Small-Body Database, the star magnitude to its Gaia DR3 record
  in VizieR.
- GUI **About** box (header): logo, version and code name, author, purpose, credits, licence, GitHub link. Project
  facts (`__codename__`, `__author__`, `__copyright__`, `__license__`, `__url__`) in `pyoccult_version.py`.
- `CHANGELOG.md` (this file).

### Changed
- Report and favorites keep the preview (`<event>.svg`) and the globe plot (`<event>_globe.svg`) strictly apart.

## [0.10.0] - 2026-10-04

### Added
- Astrometric corrections of the star direction (`pyoccult_astrometry.py`), applied once per candidate in the
  search: stellar parallax (Gaia parallax) and the gravitational light deflection by the Sun, Jupiter and Saturn
  (as star minus asteroid). Switches `star_parallax`, `light_deflection` (config and GUI Search tab, both on by
  default; off reproduces the 0.9.0 results exactly). Log columns `corr_parallax_mas`, `corr_deflection_mas`; the
  report header shows which corrections were on. Against Occult's printed star positions the difference dropped
  from 4.52 to 0.90 mas (16556) and is 0.29 mas near opposition (30819). Paths move by up to ~10 km.
- `pyoccult_owc_check.py --sea-level`: our side at elevation 0, as OWC online computes (it ignores the site
  height; up to ~0.9 km across the track at a 1000 m site).

### Fixed
- `pyoccult_owc_check.py` silently skipped OWC events marked with the Sun's altitude (twilight events,
  "sun symbol -5 deg"); it now reads them and sets the Sun limit to match.

## [0.9.0] - 2026-10-04

First numbered version (`pyoccult_version.py`; GUI header, run summary, report, picks, favorites and `--version`
show it). It collects the work since the first commit:

- 2026-09-28: the search script (`pyoccult.py`): SPICE-based exact closest-approach solver in the fundamental
  plane, Gaia stars, hit log, asteroid name lookups.
- 2026-09-30: configuration file and observing window, Moon information, automatic refresh of the Earth orientation
  kernel, KML shadow paths, the HTML/Markdown report with an embedded map, the all-asteroid pick tool.
- 2026-10-01: the local Gaia DR3 catalog and the corridor search (fast, offline), observing sites in `sites.py`.
- 2026-10-02: run statistics, extinction, automatic site setup, `--gmax`, the NiceGUI web interface, the logo.
- 2026-10-03: the ready-made catalogs on Zenodo (doi:10.5281/zenodo.23113337) with setup asking for the limit and
  the source, saved picks per site and window, KStars pointing (Linux), the favorites list (status, notes, CSV,
  mass actions, map and preview copies), 1-sigma path lines, star-field previews with density dimming, Earth
  orientation coverage in the report header, progress output for long downloads, OWC reference comparisons.
- 2026-10-04: GPL-3.0-or-later licence, `CITATION.cff`, `CONTRIBUTING.md`, references and acknowledgements.

[0.15.0]: https://github.com/pyzahl/PyOccult/commits/main
[0.14.0]: https://github.com/pyzahl/PyOccult/commits/main
[0.13.0]: https://github.com/pyzahl/PyOccult/commits/main
[0.12.0]: https://github.com/pyzahl/PyOccult/commits/main
[0.11.1]: https://github.com/pyzahl/PyOccult/releases/tag/V0.11.1-NewHorizons
[0.11.0]: https://github.com/pyzahl/PyOccult/commit/5abc5f6
[0.10.0]: https://github.com/pyzahl/PyOccult/commit/0047057
[0.9.0]: https://github.com/pyzahl/PyOccult/commit/a2d5c21
