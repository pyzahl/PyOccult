# Changelog

All notable changes to PyOccult. Newest first. Format: [Keep a Changelog](https://keepachangelog.com), versions:
[semantic versioning](https://semver.org) (MAJOR.MINOR.PATCH). The version and its code name live in
`pyoccult_version.py`; the code name changes at major milestones. Details of the computations: `ABOUT.md`.

## [Unreleased]

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
- All download and web addresses moved into one file, `pyoccult_urls.py`, each with its own name (`URL_NAIF_DE440`,
  `URL_JPL_HORIZONS_API`, `URL_MPC_OBSCODES`, ...), so they are maintained in one place. A separate file rather than
  `pyoccult_config.py`, which reads `sites.py` when imported: setup and the report need addresses without it.
- GUI Site tab: the site list is now the Minor Planet Center's list of observatory codes (ObsCodes.html, ~2700
  observatories, downloaded once into `data/`, not in git; `pyoccult_geo.mpc_observatories`), searchable by code or
  name. It replaces Occult's site list of 0.12.0, which turned out to hold mainly reference cities. Positions and
  heights come from the MPC parallax constants (WGS84); for old entries with fewer than 5 decimals the height is
  looked up instead.

### Added
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
  type) where SBDB has them. Favorites get SBDB's full per-object record once (`pyoccult_sbdb.get_full`; the pick
  tool's bulk rows hold only size fields); older favorites when the GUI starts.
- Site key `mpc_code` (the official MPC observatory code), a **MPC code** field in the GUI Site tab (filled in when
  an MPC observatory is picked), shown in the report header and kept in the run summary.

### Fixed
- README: the logo at the top pointed to its old place in the project root (moved into `src/pyoccult/`).
- GUI Favorites tab: the **CSV** download was saved as "true.csv" (the link's `download` attribute); it is now a
  button like in the Pick and Results tabs and saves `favorites_<date>.csv`.
- Pick tool with a star limit above G 15 (now easy to reach with the GUI's **Faintest star** field): the deeper
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

[0.12.0]: https://github.com/pyzahl/PyOccult/commits/main
[0.11.1]: https://github.com/pyzahl/PyOccult/releases/tag/V0.11.1-NewHorizons
[0.11.0]: https://github.com/pyzahl/PyOccult/commit/5abc5f6
[0.10.0]: https://github.com/pyzahl/PyOccult/commit/0047057
[0.9.0]: https://github.com/pyzahl/PyOccult/commit/a2d5c21
