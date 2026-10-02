# PyOccult
Python Occultation Searcher by PyZahl (C) 2026.

Experimental Asteroid Occultation Search Tool build using Python, Astropy, Spiceypy.

## What is it?
Scientific background, start here; International Occultation Timing Association (IOTA):

- https://occultations.org/

- https://occultations.org/occultations/what-is-an-occultation/

### What is an Occultation?
An occultation occurs when a solar-system body passes in front of a more distant object (e.g. a star or another solar system body), partially or totally hiding the more distant object and momentarily blocking its light. Each occultation can be seen only at the right time and from a limited part of the Earth.

### Citing: Asteroid Occultations
For asteroid occultations the star is usually the brightest component of the occultation. The asteroid is usually several magnitudes fainter than the star and often too faint to be detected in a small telescope.  In an asteroid occultation, the observer must find 
the star to be occulted and monitor the star to watch for any drop in brightness that would signal an occultation.  Asteroid occultation events typically last several seconds but may observers may record much shorter or much longer events in rare cases.  In the following diagram of an asteroid occultation:  As the asteroid moves in its orbit, a shadow is created from light cast by the star about to be occulted. The shadow (equal in size to the asteroid) then moves across the Earth (diagram not to scale).  An observer will only see an event (drop in the brightness of the star) if they are located inside the path of the asteroid’s shadow.  Since asteroids are generally much smaller than the moon, choosing a location for observing an asteroid occultation is more important than location in lunar occultations.  In addition, asteroid subtend a much smaller angular size on the sky and this leads to more uncertainty in the actual location of the asteroid’s shadow.  Asteroid occultation predictions posted by IOTA provide information on the expected location of the shadow path, expected time of the occultation, the level of drop in the star’s light and the expected duration of the occultation event.  An observer can expect to see a single disappearance (or drop in starlight) and a single reappearance though it is possible to see step events.

<img width="599" height="425" alt="image" src="https://github.com/user-attachments/assets/0225ac54-fc17-460e-a2cd-28fff8c801ef" />


# Tools in this project:

| File | What it does |
|---|---|
| `pyoccult.py` | the search: finds star occultations by your targets for your site, appends to `hits_log.csv` |
| `pyoccult_config.py` | run and site configuration |
| `sites.py` | configures observer site(s), use the example_sites.py file as a template and copy to sites.py |
| `pyoccult_paths.py` | shadow ground track (centre line, limits, 3-sigma) as KML |
| `pyoccult_report.py` | turns `hits_log.csv` into an HTML (or Markdown) event list with an embedded map |
| `pyoccult_pick.py` | finds the events at your site for all asteroids (OWC-style), writes `pick_events.csv` and `targets.py` |
| `pyoccult_setup.py` | one-time setup: SPICE kernels, local Gaia catalog, bright-star index |
| `pyoccult_gaia_local.py` | builds and reads the local Gaia catalog (used by `pyoccult_setup.py` and the search) |
| `pyoccult_owc_check.py` | regression check against an OWC search result you paste into `owc_reference.txt` (private) |

See `ABOUT.md` for the computations, data sources and open points.


# Install

# Python Virtual Environment Setup Guide

To set up a Python virtual environment and install dependencies from an existing `requirements.txt` file, open your terminal or command prompt and follow these three steps:

## 1. Create the Virtual Environment
Navigate to your project folder and run the `venv` command. Replacing `.venv` with your preferred environment name is optional, though `.venv` is the standard convention.

* **Windows / macOS / Linux:**
  ```bash
  python -m venv .venv
  ```

## 2. Activate the Virtual Environment
Before installing packages, you must activate the environment. The command depends on your operating system:

* **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```
* **Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate.bat
  ```
* **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
*Once activated, your terminal prompt will show `(.venv)` at the beginning of the line.*

NOTE: all caches go to `cache_path` in pyoccult_config.py. It defaults to /dev/shm (RAM, Linux) and to the system temp folder on other platforms; set it to any folder you like.

## 3. Install from requirements.txt
With the environment active, run `pip` to download and install all the listed packages into your isolated environment:

```bash
pip install -r requirements.txt
```

## 4. One-time data setup

PyOccult works offline from local data: SPICE kernels for the planets and Earth orientation, and a local copy of the
Gaia star catalog. `pyoccult_setup.py` installs all of it.

**What you need**

| | Kernels | Gaia catalog (G <= 18) | Bright-star index |
|---|---|---|---|
| Download | ~120 MB | 753 GB (streamed, not stored) | none (built from the catalog) |
| Disk | ~120 MB | ~11 GB | ~1.3 GB |
| Time | a minute | 1.5-2 h at ~1.4 Gbit/s, longer on slower lines | ~30 s |

Also needed: `curl` (for the kernels) and a few GB of free RAM while the index is built.

**Before you start**, check these in `pyoccult_config.py`:

* `sites.py`: before running any script, please setup your site, copy sites_example.py to sites.py and adjust your site info! See below for details.
* `gaia_local_dir`: where the catalog goes (default `gaia_dr3_g18` in the project folder). Pick a disk with ~13 GB free.
* `gaia_local_gmax`: faintest star kept (default 18). Fainter stars are never searched; 18 suits most small telescopes.
  A different value needs a new folder.
* `cache_path`: where the smaller caches go (asteroid orbits, SBDB data). Defaults to `/dev/shm` on Linux (RAM, emptied
  on reboot) and to the system temp folder elsewhere.

**Run it**

```bash
python pyoccult_setup.py              # kernels + local Gaia catalog + bright-star index
python pyoccult_setup.py --no-gaia    # kernels only (e.g. to try the old "windows" search mode)
python pyoccult_setup.py --status     # what is installed
```

The Gaia download is long. On Linux you can let it run on its own and check on it later:

```bash
nohup python pyoccult_setup.py > setup.log 2>&1 &
tail -f setup.log                     # progress every 20 files, with an ETA
```

It is safe to stop and rerun: finished files are skipped, so the same command resumes. `--status` should end with
`3386/3386 files ... (complete)` and `bright-star index ... ok`. The search (`pyoccult.py`) refuses to run on an
incomplete catalog and tells you to rerun the setup. See "Local Gaia catalog" below for what is kept and why.

## 5. Configure and run
Set your site and search window in `pyoccult_config.py` (see "Site Configuration and Run Setup" below), then:

```bash
./pyoccult.py                         # search; results appended to hits_log.csv, maps in maps/
python pyoccult_report.py hits_log.csv    # HTML event list with maps
```

A small script does a fresh run and publishes the report on a local web server (here nginx; the map tiles need a
web server, see the report section). Save it as `run.sh` (it is in `.gitignore`, adjust the paths) and make it
executable with `chmod +x run.sh`:

```bash
#!/bin/sh
rm -f hits_log.csv                    # start a fresh log (the search appends)
clear
./pyoccult.py
./pyoccult_report.py hits_log.csv
sudo cp hits_report.html /var/www/html/hits_report.html
```

To include the maps' KML links in the published page, also copy the `maps` folder (`sudo cp -r maps /var/www/html/`).

---

## Quick Tips
* **Deactivate:** When you are done working, simply type `deactivate` to exit the virtual environment.
* **Version Control:** Do not upload your `.venv` folder to GitHub. Add `.venv/` to your `.gitignore` file, but **do** commit your `requirements.txt` file.
* **Updating the list:** If you install new packages later and want to update your file, run:
  ```bash
  pip freeze > requirements.txt
  ```

* **Install + run:** Quick Start, all of above for Linux:
  ```
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  python pyoccult_setup.py            # one-time: kernels + local Gaia catalog (long download, resumable)
  echo 'EDIT SITES AND CONFIG, RUN IT:'
  ./pyoccult.py
  ```



## Site Configuration and Run Setup

All settings live in `pyoccult_config.py` (a Python file: edit it, keep the names). The search, the pick tool and the
report read it from the project folder.

**Observing sites** are kept apart from the settings, in `sites.py` (yours, not in git). Copy `sites_example.py` to
`sites.py` and enter your sites; without `sites.py` the example site (New York City Hall) is used:

```python
# sites.py
sites = {
    "home":  dict(lat=51.4769, lon=-0.0005, ele=46, name="Home",             # example: Royal Observatory Greenwich
                  aperture_cm=25, min_alt=20),
    "field": dict(lat=51.7600, lon=-1.2600, ele=60, name="Dark-sky field",
                  aperture_cm=35, min_alt=10, max_sun_alt=-12, reach_km=50, mag_adjust=0.5),
}
default_site = "home"
```

`lat`, `lon` (geodetic degrees, longitude east-positive, west is negative) and `ele` (metres) are required. Each site
can also describe its view and its equipment; keys it leaves out take the defaults from `pyoccult_config.py`:

| Key | Default | Meaning |
|---|---|---|
| `min_alt` | 10 | lowest usable star altitude, deg (trees, houses, haze) |
| `max_sun_alt` | -6 | the Sun must be below this, deg (try -12 for faint stars) |
| `reach_km` | `max_shadow_dist` | how far you can travel from this site, km |
| `aperture_cm` | 25 | telescope aperture, cm |
| `frames` | 4 | detection frames: video frames the event must cover |
| `mag_adjust` | 0 | OWC's MagAdjust: + for better conditions (dark sky, sensitive camera), - for worse |
| `extinction` | `atm_extinction` (0, off) | atmospheric extinction, mag per airmass (~0.2): low stars count as fainter |
| `min_dur_s` | 0.4 | hard limit: shortest event, s |
| `max_exp_s` | 0.64 | longest usable exposure, s; sets the faintest star searched |
| `mag_limit` | from the above | faintest star searched (Gaia G), if you want to set it directly |

Events are judged with OWC's General Observability Criterion: an event is kept if

    StarMag < 5 log10(aperture_cm) + 2.5 log10(MaxDuration / frames) + 8.5 + mag_adjust

(minus the extinction loss at the star's altitude, if enabled). The faintest star searched is the one that passes at the
longest usable exposure, `MaxDuration / frames = max_exp_s`: G 15.0 at 25 cm, G 16.5 at 50 cm.

`default_site` is used unless the environment variable `PYOCCULT_SITE` names another one, so one site can be run
without editing anything, or several in a batch:

```bash
PYOCCULT_SITE=field ./pyoccult.py
for s in home field; do PYOCCULT_SITE=$s python pyoccult_pick.py -o pick_$s.csv --targets-file ""; done
```

**Search window and targets**

| Setting | Example | Meaning |
|---|---|---|
| `ct, days, spn` | `"2026-10-01T00:00:00", 20, 3600` | search start (UTC) and number of days; `spn` (window length, s) is used only by the old `"windows"` mode |
| `targets` | `["218001", "305580"]` | asteroid numbers as strings. Taken from `targets.py` when it exists (written by `pyoccult_pick.py`), else the list in the `except ImportError:` branch |
| `max_shadow_dist` | `20` | km you can travel: an event is logged if the shadow edge passes within this of your site (0 = only from home); a site's `reach_km` overrides it |
| `search_mode` | `"corridor"` | `"corridor"` (default, fast, needs the local Gaia catalog) or `"windows"` (old per-hour archive queries) |
| `min_mag_drop` | `0.1` | events with a smaller magnitude drop are not logged; also caps the star magnitude searched per asteroid |
| `corridor_step_s` | `600` | path step of the corridor candidate scan, s |
| `gaia_local_dir`, `gaia_local_gmax` | `"gaia_dr3_g18"`, `18.0` | local Gaia catalog folder and its faintest G (see "Local Gaia catalog") |

**Observer**

| Setting | Example | Meaning |
|---|---|---|
| `LAT`, `LON`, `ELE` | from the site | the chosen site (see "Observing sites" above); `site_name` holds its name |
| `MIN_STAR_ALT`, `MAX_SUN_ALT` | from the site | the site's `min_alt` and `max_sun_alt` |
| `MAG_MIN` | from the site | faintest star (Gaia G) searched: the site's `mag_limit`, else from its aperture; at most `gaia_local_gmax` |
| `pick_aperture_cm`, `pick_frames`, `pick_mag_adjust`, `pick_extinction`, `pick_min_dur_s` | from the site | the site's equipment (used by the pick tool) |
| `ALT_MARGIN` | `3.0` | the early visibility gate is this much looser than the final test, so it never rejects a real event |
| `atm_extinction` | `0.0` | atmospheric extinction for low altitudes, mag per airmass (0 = off, ~0.2 typical, ~0.3 hazy); a star at altitude h counts as fainter by `atm_extinction * (airmass - 1)`; a site's `extinction` overrides it |

**Pick tool** (`pyoccult_pick.py`, see below)

| Setting | Example | Meaning |
|---|---|---|
| `pick_hmax` | `17.0` | asteroids with H below this (`--all` ignores it) |
| (equipment) | from the site | aperture, frames, MagAdjust, extinction and limits come from the chosen site |

**Output and caches**

| Setting | Example | Meaning |
|---|---|---|
| `hits_output_cvs_file` | `'hits_log.csv'` | results are appended here |
| `write_maps`, `map_dir` | `True`, `"maps"` | write a KML ground track for every event close enough to matter |
| `default_sigma3_km` | `10.0` | path uncertainty used when JPL Horizons has none |
| `cache_path` | `/dev/shm` or the temp folder | asteroid orbit files and SBDB downloads (RAM on Linux, emptied on reboot) |
| `sbdb_max_age_days` | `30` | asteroid size and orbit downloads are refreshed after this many days |
| `earth_pck_max_age` | `7` | the Earth orientation kernel is refreshed after this many days |
| `force_cleanup` | `False` | `True` deletes and re-downloads the SPICE kernels at start-up |

Results are appended to `hits_log.csv` (a rerun appends again; the report drops duplicates). Each hit also records
`calc_s` (its calculation time), `airmass`, `extinction_mag` and `mag_margin` (magnitudes below OWC's observability
limit, after extinction). At the end of a run `pyoccult.py` prints a summary (total time, start-up, asteroid data
loading, search, maps, time per asteroid and per exact solve, counts) and appends it, with the site, equipment and
limits, as one line to `hits_log.runs.jsonl`; the report shows the latest one in its header.


## Local Gaia catalog (required)

The corridor search (the default) needs the Gaia stars along each asteroid's path. The Gaia archive took many minutes
per asteroid for that, or hung (it warns it is unstable while DR4 is being prepared), so the stars come from a local,
magnitude-limited copy that you build once:

```
python pyoccult_setup.py                       # does all of it (kernels, catalog, bright-star index)
python pyoccult_gaia_local.py build            # the catalog alone; folder and G limit from gaia_local_dir / gaia_local_gmax
python pyoccult_gaia_local.py build --dir gaia_dr3_g18 --gmax 18 --workers 6
python pyoccult_gaia_local.py status
```

* It streams all of Gaia DR3 `gaia_source` from ESA's CDN (3386 files, **753 GB download**), keeps G <= gmax with full
  astrometry and ruwe < 1.4 (7 columns, binary), and deletes each download. G <= 18 keeps about 19 GB.
  At about 1.4 Gbit/s it takes 1.5 to 2 hours.
* It is resumable: rerun the same command after an interruption, finished files are skipped.
* `gaia_local_dir` in pyoccult_config.py must name that folder. pyoccult.py refuses a missing or incomplete catalog.
* A strip lookup takes about 1 s (2 s in the Galactic bulge), no network. Gaia is not cached elsewhere any more.
* Stars fainter than `gaia_local_gmax` are not searched, whatever `MAG_MIN` says.



## Quick start: choose targets (pick tool)

`pyoccult_pick.py` finds the actual occultation events at your site for all asteroids in a window, like an OWC/Occult
search, and writes the asteroids of the best events to `targets.py` for `pyoccult.py`.

```bash
python pyoccult_pick.py                          # window, site and camera from pyoccult_config.py, H < 17
python pyoccult_pick.py --start 2026-10-01 --days 14 --top 30
python pyoccult_pick.py --all                    # exhaustive: every numbered asteroid (~900k)
python pyoccult_pick.py --sort date              # ranking: mag (default, brightest star first), date, margin, drop
```

How it works:

* Asteroids: one bulk download from JPL's Small-Body Database (numbered, H < `pick_hmax`, full-precision orbital
  elements), cached as `PyOccult_sbdb_cache.json` in `cache_path` and refreshed after `sbdb_max_age_days`.
* Orbits are integrated with the planets' gravity for the whole window (agrees with JPL Horizons to about 0.01").
* The stars are the actual Gaia stars along each path, from the bright-star index of the local catalog
  (`python pyoccult_setup.py` builds it). Only times when the asteroid is up and the Sun is down are searched.
* Each event is solved for your site and kept if the shadow passes within the asteroid radius + `max_shadow_dist`.
* Detection follows OWC's General Observability Criterion with the site's equipment (see "Observing sites"):
  `StarMag < 5 log10(aperture_cm) + 2.5 log10(MaxDuration / frames) + 8.5 + mag_adjust`, optionally less the extinction
  at the star's altitude, plus the hard limits `min_dur_s` and `min_mag_drop`. Bright stars therefore allow short
  events (a G 5.6 star with a 0.25 s event counts), faint stars need long ones. For asteroids whose size is only
  estimated from H, the duration uses the upper size bound, so they are not dismissed too early.

Speed: 465k asteroids (H < 17) over 8 days in about 5 minutes with 4 worker processes (`--workers`).

Output:

* a ranked table of the events, and `pick_events.csv` with all of them (time, star, magnitude, drop, duration,
  `mag_margin` = magnitudes below the observability limit, distance from the centre line, altitudes, size)
* `targets.py`: the asteroids of the best `--top` events, best first, importable; each line shows its event
* their size data goes to the shared size cache, so the following `pyoccult.py` run needs no SBDB lookups for them

`pyoccult.py` then computes these events exactly (JPL Horizons orbit, exact solver, maps). Run it over the same window
(`ct`, `days` in `pyoccult_config.py`; the pick tool uses them as its defaults).

Tune it like OWC: with the same aperture, frames and MagAdjust as in OWC you get OWC's selection. Raise `mag_adjust`
for a dark site or a sensitive camera, lower it for light pollution or a less sensitive one.

Use the result in `pyoccult_config.py`:

```python
try:
    from targets import targets, target_names
except ImportError:
    targets = ["218001", "305580", "111287", "115181", "229912", "111286", "54653", "70141", "4272"]
    target_names = {}
```

(`from targets import targets` already gives the list, so do not add `targets = targets.targets`.)



## Quick start: hits_log.csv to HTML report

`pyoccult_report.py` turns the log into a one-page event list with the columns OWC users expect (asteroid, event time UT, star mag, mag drop, max duration, altitude with compass direction, Moon distance, offset from the centre line) and a **Map** button for each event. Standard library only, no install needed.
The page header shows the site, its equipment, the magnitude and observing limits, and the statistics of the run
(from `hits_log.runs.jsonl`); each event's calculation time is in the `Calc (s)` column.

```bash
python pyoccult_report.py hits_log.csv                           # writes hits_report.html next to the CSV
python pyoccult_report.py hits_log.csv -o hits_report.md         # Markdown instead
python pyoccult_report.py hits_log.csv --kml-dir maps --max-miss 200 --min-drop 0.3 --title "Long Island"
python pyoccult_report.py hits_log.csv --sort date               # by event time (default --sort mag: brightest star first)
```

* Observer `LAT`/`LON` (for the compass direction) and `map_dir` (optional, default `maps`) come from `pyoccult_config.py`; override with `--lat`, `--lon`, `--kml-dir`.
* `--max-miss KM` and `--min-drop MAG` filter the list; `--no-embed` leaves out the embedded map viewer.
* Each event row links to its KML file (`maps/<asteroid>_<YYYYMMDDTHHMM>*.kml`, written by the shadow-path module). The map button opens an embedded Leaflet map with the centre line (green), the shadow limits (red), the 3-sigma limits (orange, dashed) and your site, zoomed to the nearest point of the path. A link there opens that point in Google Maps.
* View it through a web server for reliable maps: copy the report, the `maps` folder (for the KML links) and, e.g.,
  ```bash
  cp hits_report.html /var/www/html/pyoccult/ && cp -r maps /var/www/html/pyoccult/
  ```
  and open `http://localhost/pyoccult/hits_report.html`. Opened straight from disk (`file://`), the OpenStreetMap tiles are blocked because the request carries no Referer; the default light and satellite basemaps are meant to work from disk, and the map has a basemap switcher and a notice if tiles fail. The map needs internet (Leaflet and tiles load from CDNs); the event table does not.
* To refresh the report after every run, add the report command at the end of your batch job.



### MAPS

To import a KML file into Google Maps, you must use the Google My Maps platform on a web browser. Standard Google Maps allows you to view these custom maps, but the actual file upload has to take place through the My Maps editor.

- Open the Tool: Navigate directly to Google My Maps in your web browser and ensure you are signed into your Google Account. Or go here: https://www.google.com/maps/d
- Create a Map: Click the Create a New Map button in the top left corner.
- Locate the Import Panel: In the left-hand legend window, find the box labeled Untitled layer and click the Import link directly underneath it.
- Upload Your File: Drag and drop your KML files (maps folder) into the box.


<img width="1087" height="643" alt="image" src="https://github.com/user-attachments/assets/64a4ea87-9296-4fff-bbf7-e45a472a4231" />
