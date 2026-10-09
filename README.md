# PyOccult <img src="src/pyoccult/pyoccult_logo.svg" alt="" width="96" align="right">
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23149371.svg)](https://doi.org/10.5281/zenodo.23149371)

Python Occultation Searcher by PyZahl (C) 2026, version 0.14.0 “New Horizons”. Free software under the GNU GPL v3 or later (see License below).
The version and its code name (it changes at major milestones) are kept in `pyoccult/version.py`; the GUI header and
its **About** box show both, the report and `--version` of every tool show the version. What changed in each version:
[CHANGELOG.md](CHANGELOG.md). How the predictions were verified: [VERIFICATION.md](VERIFICATION.md).

Experimental occultation search tool for asteroids, planets and their moons, built with Python, Astropy, SpiceyPy and
NiceGUI: a local web interface to plan and run all tasks for easy event exploration. New here? Start with the
[Quick start](#quick-start).

## Contents

- [What is it?](#what-is-it)
- [Occultation Data](#occultation-data)
- [Tools in this project](#tools-in-this-project)
- [Quick start](#quick-start)
- [Install](#install)
  - [Easiest: with uv (Linux, macOS, Windows)](#easiest-with-uv-linux-macos-windows)
  - [Windows, step by step (with uv)](#windows-step-by-step-with-uv)
  - [With pip and a virtual environment](#with-pip-and-a-virtual-environment)
- [Python Virtual Environment Setup Guide](#python-virtual-environment-setup-guide)
  - [1. Create the Virtual Environment](#1-create-the-virtual-environment)
  - [2. Activate the Virtual Environment](#2-activate-the-virtual-environment)
  - [3. Install PyOccult](#3-install-pyoccult)
  - [4. One-time data setup](#4-one-time-data-setup)
  - [5. Run it: the web interface](#5-run-it-the-web-interface)
    - [The core command-line tools](#the-core-command-line-tools)
  - [Quick Tips](#quick-tips)
- [Where your data and settings live](#where-your-data-and-settings-live)
- [Site Configuration and Run Setup](#site-configuration-and-run-setup)
- [Local Gaia catalog (required)](#local-gaia-catalog-required)
- [Pick tool: choose targets](#pick-tool-choose-targets)
- [Web interface (GUI)](#web-interface-gui)
- [Planets and moons](#planets-and-moons)
- [Report: event list, maps and previews](#report-event-list-maps-and-previews)
- [GUI Step by Step in Screenshots](#gui-step-by-step-in-screenshots)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)
- [References](#references)

## What is it?
Scientific background, start here; International Occultation Timing Association (IOTA):

- IOTA: https://occultations.org

- Background: https://occultations.org/occultations/what-is-an-occultation

- OWC: https://cloud.occultwatcher.net

### What is an Occultation?
An occultation occurs when a solar-system body passes in front of a more distant object (e.g. a star or another solar system body), partially or totally hiding the more distant object and momentarily blocking its light. Each occultation can be seen only at the right time and from a limited part of the Earth.

### Citing from IOTA: Asteroid Occultations
For asteroid occultations the star is usually the brightest component of the occultation. The asteroid is usually several magnitudes fainter than the star and often too faint to be detected in a small telescope.  In an asteroid occultation, the observer must find 
the star to be occulted and monitor the star to watch for any drop in brightness that would signal an occultation.  Asteroid occultation events typically last several seconds but may observers may record much shorter or much longer events in rare cases.  In the following diagram of an asteroid occultation:  As the asteroid moves in its orbit, a shadow is created from light cast by the star about to be occulted. The shadow (equal in size to the asteroid) then moves across the Earth (diagram not to scale).  An observer will only see an event (drop in the brightness of the star) if they are located inside the path of the asteroid’s shadow.  Since asteroids are generally much smaller than the moon, choosing a location for observing an asteroid occultation is more important than location in lunar occultations.  In addition, asteroid subtend a much smaller angular size on the sky and this leads to more uncertainty in the actual location of the asteroid’s shadow.  Asteroid occultation predictions posted by IOTA provide information on the expected location of the shadow path, expected time of the occultation, the level of drop in the star’s light and the expected duration of the occultation event.  An observer can expect to see a single disappearance (or drop in starlight) and a single reappearance though it is possible to see step events.

<img width="599" height="425" alt="image" src="https://github.com/user-attachments/assets/0225ac54-fc17-460e-a2cd-28fff8c801ef" />

## Occultation Data
includes all reported timings of observed asteroid occultation events:

- https://data.nasa.gov/dataset/asteroid-occultations

- https://science.unistellar.com/asteroid-occultations/results/

This is where PyOccult comes in: it predicts such events for observation planning, so that more of them get observed and every timed event adds to our knowledge of the many small bodies of the Solar System.

# Tools in this project:

The code is the Python package `pyoccult` in `src/pyoccult/` (paths below are relative to `src/`). One command starts
everything: `pyoccult` (the web interface) or `pyoccult <command>`, e.g. `pyoccult search`, `pyoccult pick`,
`pyoccult setup`, `pyoccult report hits_log.csv`, `pyoccult owc-check`, `pyoccult gaia status`, `pyoccult picks list`
(`pyoccult --help` lists them all).

| File | What it does |
|---|---|
| `pyoccult/search.py` | the search: finds star occultations by your targets (asteroids, planets, moons) for your site; stores them in the results database `pyoccult.db` and writes the current list as `hits_log.csv` |
| `pyoccult/bodies.py` | planets and moons as targets (`P:Jupiter`, `M:Io`, ...): the satellite table, ephemeris kernels from Horizons or NAIF, sizes and brightness |
| `pyoccult/db.py` | the results database (`pyoccult.db`, SQLite): runs, events, contact times, favorites |
| `pyoccult/exports.py` | the CSV downloads of the GUI tables, with the columns of `csv_exports.py` |
| `pyoccult_config.py` | your run configuration (window, targets, limits, output), in the PyOccult folder; created from `pyoccult/templates/pyoccult_config.py` |
| `sites.py` | your observing site(s) with their view and equipment; private, created by `pyoccult setup` from `pyoccult/templates/sites_example.py` |
| `pyoccult/paths.py` | shadow ground track (centre line, limits, 3-sigma) as KML |
| `pyoccult/report.py` | turns `hits_log.csv` into an HTML (or Markdown) event list with an embedded map |
| `pyoccult/pick.py` | finds the events at your site for all asteroids (OWC-style), writes `pick_events.csv` and `targets.py`, and saves both per site and window in `picks/` |
| `pyoccult/picks.py` | the saved picks: which one a search uses, `list`, `import` |
| `pyoccult/urls.py` | every download and web address PyOccult uses (NAIF, ESA Gaia, Zenodo, JPL, MPC, Open-Meteo, maps), each with its own name: change them there only |
| `pyoccult/kstars.py` | points a running KStars at an event (Linux, D-Bus); used by the report's KStars button in the GUI |
| `pyoccult/stellarium.py` | points a running Stellarium at an event (Remote Control plugin, HTTP); the report's Stellarium button |
| `pyoccult/favorites.py` | the favorites list (`favorites/`, private): events starred in the report, with copies of map and preview; `list` |
| `pyoccult/setup.py` | one-time setup: SPICE kernels, local Gaia catalog, bright-star index |
| `pyoccult/gaia_local.py` | builds and reads the local Gaia catalog (used by `pyoccult/setup.py` and the search) |
| `pyoccult/gui.py` | local web interface: sites on a map, run search and pick, live log, results (NiceGUI) |
| `pyoccult/owc_check.py` | regression check against an OWC search result you paste into `owc_reference.txt` (private) |
| supporting modules | `pyoccult/corridor.py` (star corridor), `pyoccult/screen.py` + `pyoccult/orbits.py` (pick tool engine), `pyoccult/preview.py` (event preview image), `pyoccult/globe.py` (whole-Earth plot), `pyoccult/doubles.py` (close and double stars), `pyoccult/binaries.py` (asteroid satellites), `pyoccult/occultations.py` (earlier occultations), `pyoccult/sbdb.py` (asteroid size cache), `pyoccult/cameras.py` (sensor list), `pyoccult/kernels.py` (kernel download), `pyoccult/geo.py` (place and IP lookup), `pyoccult/runner.py` (runs with per-run settings) |

See [ABOUT.md](ABOUT.md) for the computations, data sources and open points, and
[VERIFICATION.md](VERIFICATION.md) for how the predictions were checked against OccultWatcher Cloud and Occult
(same stars, times within a few seconds) and the differences found.

# Quick start

A few commands, one download (about 2 GB), then everything happens in your browser:

1. **Get it:** install [uv](https://docs.astral.sh/uv/getting-started/installation/), then
   `git clone https://github.com/pyzahl/PyOccult` (or download the ZIP from GitHub and unpack it). Windows users: see
   [Windows, step by step](#windows-step-by-step-with-uv). Without uv on Linux/macOS: `sh linux_install.sh` does
   steps 2 and 3 with pip.
2. **Set up once**, in the PyOccult folder: `uv run pyoccult setup`. It downloads the SPICE kernels and the local
   Gaia catalog (G <= 16 from Zenodo; resumes if interrupted) and asks for your first observing site.
3. **Start the web interface:** `uv run pyoccult` (opens http://127.0.0.1:8080). Work through the tabs from left
   to right:
   * **Site**: your position (map, place name or MPC observatory code) and your telescope and camera.
   * **Pick**: choose a window and **Run pick**: all asteroids are screened for events at your site (a few
     minutes; saved and reused for that window).
   * **Planets & Moons** (optional): tick planets and moons and run; no pick needed.
   * **Search**: **Run search**: exact predictions for the picked asteroids, with maps and previews.
   * **Results**: the event list with Map, Preview, Globe and KML, KStars and Stellarium pointing, and ☆ to keep an
     event.
   * **Favorites**: your starred events, with status and notes.
4. **Next time:** `uv run pyoccult` again; run a new pick when your window ends. `git pull` updates PyOccult (uv
   installs new dependencies by itself).

The rest of this README goes into detail: installing with pip, the data folder, sites, the catalog, the pick, the
GUI, planets and moons, and the report.

# Install

> **How to type the commands in this README.** They are written as `pyoccult …`. Depending on how you installed:
>
> | installed with | type | where |
> |---|---|---|
> | uv | `uv run pyoccult …` | in the PyOccult folder |
> | pip, environment activated (`source .venv/bin/activate`; Windows: `.venv\Scripts\activate`) | `pyoccult …` | anywhere, in that terminal |
> | pip, not activated | `.venv/bin/pyoccult …` (Windows: `.venv\Scripts\pyoccult …`) | in the PyOccult folder |
>
> Activation lasts for one terminal only. To type just `pyoccult` in every terminal, add an alias once, e.g. in
> `~/.bashrc`: `alias pyoccult=~/PyOccult/.venv/bin/pyoccult` (with your folder), or with uv
> `alias pyoccult='uv run --project ~/PyOccult pyoccult'`, which also works from any folder.

## Easiest: with uv (Linux, macOS, Windows)

[uv](https://docs.astral.sh/uv/) installs the right Python and all packages by itself, like for PyMovie and PyOTE;
nothing else is needed (no Python installation, no virtual environment by hand, no admin rights).

1. Install uv once:
   * Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   * Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

   (then open a new terminal, so the `uv` command is found)
2. Get PyOccult: `git clone https://github.com/pyzahl/PyOccult.git`, or download the ZIP from GitHub (green "Code"
   button, "Download ZIP") and unpack it.
3. In the PyOccult folder:

   ```bash
   cd PyOccult
   uv run pyoccult setup     # one-time: your site, SPICE kernels, Gaia catalog (asks; resumable)
   uv run pyoccult           # the web interface, in your browser
   ```

The first `uv run` downloads Python 3.12 (`.python-version`) and the packages in the exact versions of `uv.lock`
into `.venv` in the PyOccult folder (about a minute); later starts are instant. Every tool works the same way:
`uv run pyoccult pick ...`, `uv run pyoccult search`, `uv run pyoccult --help`. To update: `git pull` (or a new ZIP),
then `uv run pyoccult` as before; uv brings the packages up to date by itself. Your data (sites, settings, kernels,
catalogs, results) stays in the PyOccult folder, see "Your data folder" below.

## Windows, step by step (with uv)

Not tested on Windows yet: please report what works and what does not (GitHub issue or e-mail).

1. **Install uv.** Open PowerShell (Start menu, type "PowerShell", Enter) and paste:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Close PowerShell and open a new one, so the `uv` command is found (`uv --version` shows it).
2. **Get PyOccult.** On https://github.com/pyzahl/PyOccult click the green "Code" button, then "Download ZIP".
   Unpack it (right-click, "Extract All...") and give the folder a simple place and name, e.g. `C:\PyOccult`
   (the ZIP's folder is called `PyOccult-main`; rename it if you like). With Git for Windows installed you can
   instead run `git clone https://github.com/pyzahl/PyOccult.git C:\PyOccult`, which makes updates easier.

   Choose a folder that is **not** synced to OneDrive (Documents and Desktop often are): PyOccult keeps everything
   in this folder, including the Gaia catalog (3 GB, or 11 GB for G 18), which you do not want uploaded to the cloud.
   You need about 5 GB free on that drive for the default catalog.
3. **One-time setup.** In PowerShell:

   ```powershell
   cd C:\PyOccult
   uv run pyoccult setup
   ```

   The first run downloads Python and the packages (about a minute), then setup asks for your site (it can guess
   it from your internet address or look up a place name) and the catalog: Enter takes G 16 from Zenodo (2.1 GB
   download). Setup can be stopped and rerun; it resumes.
4. **Start PyOccult.**

   ```powershell
   cd C:\PyOccult
   uv run pyoccult
   ```

   Your browser opens the PyOccult page (http://127.0.0.1:8080). Keep the PowerShell window open while you use it;
   close it, or press Ctrl+C in it, to stop PyOccult. If Windows asks whether Python may use the network, allowing
   private networks is enough (the page is only reachable from your own computer).

**A start icon (optional).** In `C:\PyOccult` create a text file `PyOccult.bat` (Notepad, "Save as type: All
files") with these two lines, then double-click it (or right-click, "Send to", "Desktop (create shortcut)"):

```bat
cd /d "%~dp0"
uv run pyoccult
```

**Updating.** With git: `cd C:\PyOccult`, `git pull`. With the ZIP: download it again and copy its contents over
your folder (your own files, `sites.py`, `pyoccult_config.py`, the catalog, picks, favorites and results, are not
in the ZIP, so they stay). Then start as usual; uv updates the packages by itself.

**Good to know on Windows:** caches go to the Windows temp folder (`cache_path` in `pyoccult_config.py` sets
another one); the SPICE kernels are downloaded with `curl`, which is part of Windows 10 and 11; the KStars buttons
are Linux-only and hidden. To remove PyOccult, delete its folder (and `%APPDATA%\PyOccult` if it exists); uv itself
can stay (it is small), or see uv's documentation, "Uninstallation" (https://docs.astral.sh/uv/getting-started/installation/).

## With pip and a virtual environment

General steps: clone this repository, change into its folder PyOccult, set up a Python virtual environment, install
PyOccult into it (`pip install -e .`, which also installs the packages it needs and the `pyoccult` command) and run
the setup. PyOccult is a standard Python package (`pyproject.toml`, code in `src/pyoccult/`); your data (sites,
settings, kernels, catalogs, results) stays in the PyOccult folder.

For Linux (and macOS): the script `linux_install.sh` does steps 1-5 below in one go after cloning: it creates the
virtual environment `.venv`, installs the packages into it, runs the one-time setup (it asks for your site and the
catalog) and then starts the GUI:

  ```bash
  git clone https://github.com/pyzahl/PyOccult.git
  cd PyOccult
  sh linux_install.sh
  ```

It can be rerun (it reuses `.venv`, and the setup resumes). It needs Python 3 with its venv module (Debian/Ubuntu:
`sudo apt install python3 python3-venv`). Later, start the GUI with `.venv/bin/pyoccult`.

# Python Virtual Environment Setup Guide

To set up a Python virtual environment and install PyOccult with its dependencies (listed in `pyproject.toml`), open
your terminal or command prompt in the PyOccult folder and follow these three steps:

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

## 3. Install PyOccult
With the environment active, install PyOccult and all the packages it needs into your isolated environment:

```bash
pip install -e .
```

`-e` (editable) runs the code from `src/pyoccult/` directly, so a later `git pull` takes effect without installing
again (only when `pyproject.toml` gains a new package, run it once more). It also installs the command `pyoccult`:
`pyoccult` alone starts the web interface, `pyoccult <command>` runs a tool (`pyoccult --help` lists them; options
as before). Without activating the environment, use `.venv/bin/pyoccult` (Windows: `.venv\Scripts\pyoccult`).

**Your data folder** (sites, settings, kernels, catalogs, results): see "Where your data and settings live" below.

## 4. One-time data setup

PyOccult works offline from local data: SPICE kernels for the planets and Earth orientation, and a local copy of the
Gaia star catalog. `pyoccult/setup.py` installs all of it.

The Gaia catalog can be installed two ways, with the same result:

* **zenodo** (recommended): download the ready-made catalog from Zenodo,
  [doi:10.5281/zenodo.23113337](https://doi.org/10.5281/zenodo.23113337) (CC BY-NC 4.0, the terms of the Gaia data it contains). Setup checks its SHA-256 and
  unpacks it. Available for G <= 16 (`gaia_dr3_g16.tar.xz`, 2.1 GB, the default) and G <= 18 (`gaia_dr3_g18.tar.xz`,
  8.2 GB).
* **esa**: build it yourself from ESA's Gaia DR3 bulk files. Takes much longer, but works for any magnitude limit.

**What you need**

| | Kernels | Gaia catalog G <= 16 (default), zenodo | Gaia catalog G <= 18, zenodo | Gaia catalog, esa | Bright-star index |
|---|---|---|---|---|---|
| Download | ~120 MB | 2.1 GB | 8.2 GB | 753 GB (streamed, not stored) | none (built from the catalog) |
| Disk | ~120 MB | ~3 GB (~5 GB while unpacking) | ~11 GB (~20 GB while unpacking) | ~3 GB (G 16), ~11 GB (G 18) | ~1.3 GB |
| Time | a minute | download time + ~2 min | download time + ~5 min to check and unpack | 1.5-2 h at ~1.4 Gbit/s, longer on slower lines | ~30 s |

G 16 suits most amateur telescopes (a 25-30 cm telescope with a video camera reaches about G 15-16); take G 18 for
large apertures or long exposures. Also needed: `curl` (for the kernels)
and a few GB of free RAM while the index is built.

**Before you start**: your observing site goes into `sites.py` (see "Observing sites" below). If it does not exist
yet, `pyoccult/setup.py` helps you create it: it guesses your position from your IP address (ipinfo.io; city level,
off by 10-100 km, wrong behind a VPN; `--no-geoip` skips it), and you can accept that, look up a city or place name
(Open-Meteo, with elevation), or type latitude, longitude and elevation. A guessed or looked-up position is marked
APPROXIMATE in `sites.py`, and `--status` keeps warning until you replace it with your exact position (GPS or a map;
a shadow can be only a few km wide). Without a terminal, setup copies `src/pyoccult/templates/sites_example.py` instead. Also check these in
`pyoccult_config.py`:

* `gaia_local_dir`: where the catalog goes (default `gaia_dr3_g16` in the data folder). Pick a disk with ~5 GB free
  for G 16, ~22 GB for G 18 (while the Zenodo archive is unpacked; it is saved next to the folder and deleted
  afterwards).
* `gaia_local_gmax`: faintest star kept (default 16). Fainter stars are never searched; it also caps the site's star
  limit, so set it to the catalog you have (18 with `gaia_dr3_g18`).
  A different value needs a new folder (`--gmax`, see below).
* `cache_path`: where the smaller caches go (asteroid orbits, SBDB data). Defaults to `/dev/shm` on Linux (RAM, emptied
  on reboot) and to the system temp folder elsewhere.

**Run it**

```bash
pyoccult setup              # kernels + local Gaia catalog + bright-star index (asks: zenodo or esa)
pyoccult setup --source zenodo   # catalog from Zenodo without asking (G <= 16 or 18 only)
pyoccult setup --source esa      # build the catalog from ESA's files without asking
pyoccult setup --no-gaia    # kernels only (e.g. to try the old "windows" search mode)
pyoccult setup --status     # what is installed
pyoccult setup --gmax 18    # the larger catalog to G 18 (own folder gaia_dr3_g18, ~11 GB); --dir to choose the folder
```

The catalog limit defaults to `gaia_local_gmax` (16). Another limit with `--gmax` is built in its own folder
(`gaia_dr3_g<limit>`, or `--dir`); setup then prints the two lines to set in `pyoccult_config.py` (`gaia_local_dir`,
`gaia_local_gmax`) so the search uses it. Stars fainter than the catalog limit are never searched.

In a terminal, setup first asks for the catalog's limit (Enter = 16; `--gmax` skips the question), and names the
folder after it (`gaia_dr3_g<limit>`). Where the catalog comes from (`--source`, default `auto`): in a terminal, setup
then asks, and Enter takes Zenodo. Without
a terminal it takes Zenodo. It builds from ESA's files when the limit is not 16 or 18, or when an interrupted ESA
build is already in the folder (it resumes that one). `--keep-archive` keeps the downloaded `.tar.xz`. If you already
have the archive (downloaded by hand from the DOI page), put it next to the catalog folder, e.g.
`gaia_dr3_g18.tar.xz` beside `gaia_dr3_g18/`. Setup then checks it and unpacks it without downloading.

The download takes a while, the ESA build much longer. To let it run on its own and check on it later (Linux,
macOS), answer setup's questions first and then start only the catalog in the background, with your answers given as
options. In the background setup cannot ask: it would take the example site (New York) and the catalog limit from
`pyoccult_config.py`.

```bash
pyoccult setup --no-gaia                                           # in the terminal: your site and the kernels
nohup pyoccult setup --gmax 18 --source zenodo > setup.log 2>&1 &  # then the catalog in the background
tail -f setup.log                     # progress with speed and ETA: a new line every 30 s
```

`--gmax 16` for the smaller catalog; `--source esa` to build it from ESA's files instead.

It is safe to stop and rerun: a Zenodo download continues where it stopped, and an ESA build skips finished files, so
the same command resumes. `--status` should end with
`3386/3386 files ... (complete)` and `bright-star index ... ok`. The search (`pyoccult/search.py`) refuses to run on an
incomplete catalog and tells you to rerun the setup. See "Local Gaia catalog" below for what is kept and why.

**Downloads fail (offline, server down, proxy or firewall).** Setup stops with a message naming the address instead
of a traceback; what is already downloaded is kept, so rerun it later. Behind a proxy, tell curl and Python about it
first: `export https_proxy=http://<proxy>:<port> HTTPS_PROXY=http://<proxy>:<port>`. If a proxy blocks one source,
try the other (`--source zenodo` or `--source esa`), or copy the kernel files (`*.tls *.bsp *.tpc *.bpc`) and a
finished catalog folder (`gaia_dr3_g16`, `gaia_dr3_g18`) from another computer. All addresses are listed in
`pyoccult/urls.py`. An ESA build skips a file that still fails after its retries (a rerun fetches it) and stops early
if the first files all fail.

## 5. Run it: the web interface

Start the GUI and work through its tabs from left to right:

```bash
pyoccult                 # opens http://127.0.0.1:8080 in your browser (local only)
```

1. **Site**: set your observing site on the map (or by place name / IP address, or from the Minor Planet Center's list of
   ~2700 observatories with their official MPC codes: type a code or name in **MPC observatory**; the **MPC code**
   field holds your site's code, if it has one) and enter its equipment (**Sensor (cameras)**: pick your camera's sensor, e.g.
   type "174" or your camera's name, to fill the sensor width and height; MM / MC, M / C are a camera's mono and
   color versions). **Add as new site** (next to the list) adds
   what the map and form show as a new site to the site selector, named as in **New site name**, and saves it;
   **Save sites.py** instead stores the form into the site selected at the top right; **Remove site** deletes the
   selected site from `sites.py` (after asking): aperture,
   focal length, sensor size, detection frames, reach (how far you can travel), minimum star altitude, Sun limit.
   The site and the Gaia catalog used by all runs are chosen at the top right.
2. **Pick**: choose a window (start date, today by default, and days), the asteroids (**H below**: an asteroid with a
   larger H is never found by the pick, but the search finds it if you enter its number) and the **Star G limit**
   (from the site's telescope, capped at the catalog; change it for one run), and run the pick: it screens all asteroids (H below 17 by default)
   for actual events at your site and saves the best targets for this site and window. This is the slow step
   (several minutes); a saved pick is reused by every later search of the same site and window. **CSV** downloads the
   selected pick's events as a table (the Results tab has the same button for the search results, named
   `hits_<site>__<start>_<days>d.csv`).
3. **Planets & Moons** (optional): occultations by the planets Mars to Neptune, Pluto and their moons, with
   disappearance and reappearance times; tick the bodies, choose the window and run. Results in the tab (see
   "Planets and moons" below).
4. **Search**: the exact prediction for the picked targets (JPL Horizons orbits, local Gaia catalog): event times,
   drops, durations, shadow paths (KML maps) and star-field previews. **Star G limit** (default from your telescope)
   and the minimum drop apply to this run.
5. **Results**: the event list with a **Map** (shadow path with shadow, 1-sigma and 3-sigma limits and your site),
   a **Preview** (star field and camera frame), a **Globe** (the whole Earth seen from the star with the path and
   minute marks, and the event parameters as on Occult's plot) and the **KML** for Google Earth for each event; a
   **Stellarium** button that points Stellarium at the event (any system, Remote Control plugin), on Linux with
   KStars running also a **KStars** button, and a **☆** button that adds the event to your favorites.
6. **Favorites**: the events you starred, from any search and any site, each with its own copy of map and preview
   (later searches do not change them). The table is the Results table (same columns, sorting and tools: KStars,
   Map, Preview, KML) plus a select box, the site, status, note and when it was added. Check rows to set their
   status (planned / observed / cancelled / clouded) or remove them; **Remove past events** drops every favorite
   whose event is before today (UTC); **times** switches the event times between UT, your computer's time zone (Local)
   and the time zone of each event's site (Site). Click a row to see its star-field preview and shadow path map side by side
   below the table, with its size (the diameter and range the search used, its source, H and albedo), its shape and
   rotation where SBDB knows them (axes, rotation period, pole, taxonomic type; fetched once per favorite from the
   SBDB API, as the pick tool's bulk data holds only the size), and to edit its note. **CSV** downloads the favorites
   table (`favorites_<date>.csv`; columns: see "CSV downloads" below); `favorites/favorites.csv`, with all fields,
   is rewritten with every change, for use in other tools or sharing. Drag the bottom-right corner of the table to resize it (remembered
   in your browser; the Results report and the Pick table have the same corner).

Settings changed in the GUI apply to that run only; `pyoccult_config.py` is not changed. Details: "Web interface
(GUI)" below; screenshots of every tab: "GUI Step by Step in Screenshots" at the end.

### The core command-line tools

Everything the GUI does is also available on the command line (scripts, automation, a remote machine). Type them as
`uv run pyoccult …` with uv, or `.venv/bin/pyoccult …` without an activated environment (see "How to type the
commands" at the top of Install). The site is
`default_site` in `sites.py`, or `PYOCCULT_SITE=<name>` for one run; settings come from `pyoccult_config.py`.

| Step | Command | What it does |
|---|---|---|
| once | `pyoccult setup` | SPICE kernels, local Gaia catalog (Zenodo download or ESA build), bright-star index, `sites.py` |
| choose | `pyoccult pick --start 2026-10-01 --days 20` | screen all asteroids for events at the site; writes `pick_events.csv`, `targets.py` and the saved pick in `picks/` |
| predict | `pyoccult search` | exact search for the targets (the saved pick of the site covering the window, else `targets.py`); adds the events to the current results list in `pyoccult.db`, writes it as `hits_log.csv`, and `maps/` |
| present | `pyoccult report hits_log.csv` | HTML event list with maps and previews (`hits_report.html`) |
| planets | `pyoccult run search '{"targets": ["P:Jupiter", "M:Io"], "results_list": "bodies", "hits_output_cvs_file": "bodies_log.csv"}'` then `pyoccult report bodies_log.csv -o bodies_report.html --layout bodies` | planets and moons as the Planets & Moons tab runs them |
| point | `pyoccult stellarium <ra> <dec> <utc> [fov]`, `pyoccult kstars ...` | point Stellarium or KStars at a position and time |
| check | `pyoccult owc-check --ref owc_reference.txt` | rerun an OWC search result you saved as text and compare event by event (`--sea-level`: compute at elevation 0, as OWC online does) |

`pyoccult run <command> '<JSON>'` runs a command with settings changed for that run only (`pyoccult_config.py`
stays as it is), e.g. `pyoccult run search '{"ct": "2026-10-01T00:00:00", "days": 8, "MAG_MIN": 15}'`; the GUI starts
every run this way.

Useful options: `pyoccult pick --hmax 18 --reach 30 --frames 4 --top 40 --workers 4` (see "Pick tool: choose
targets" below), `pyoccult picks list` (saved picks), `PYOCCULT_CATALOG=gaia_dr3_g16 pyoccult search`
(another catalog for one run), `pyoccult setup --status` (what is installed).

A small script does a fresh run and publishes the report on a local web server (here nginx; the map tiles need a
web server, see the report section). Save it as `run.sh` (it is in `.gitignore`, adjust the paths) and make it
executable with `chmod +x run.sh`:

```bash
#!/bin/sh
clear
pyoccult run search '{"results_new_series": true}'   # a fresh results list (older ones stay in pyoccult.db)
pyoccult report hits_log.csv
sudo cp hits_report.html /var/www/html/hits_report.html
```

To include the maps' KML links in the published page, also copy the `maps` folder (`sudo cp -r maps /var/www/html/`).

---

## Quick Tips
* **Deactivate:** When you are done working, simply type `deactivate` to exit the virtual environment.
* **Version Control:** Do not upload your `.venv` folder to GitHub (`.gitignore` keeps it out).
* **Updating the list:** if the code needs a new package, add its name to `dependencies` in `pyproject.toml`
  (unpinned, no version numbers, like the others), run `uv lock` to update `uv.lock` (commit both), and
  `pip install -e .` again in a pip-made environment.

* **Install + run:** Quick Start, all of above for Linux:
  ```
  python -m venv .venv
  source .venv/bin/activate
  pip install -e .
  pyoccult setup        # one-time: kernels + local Gaia catalog (Zenodo download, resumable)
  pyoccult              # then: Site -> Pick -> Search -> Results in the browser
  ```



## Where your data and settings live

**One data folder holds all your files**, none of them in git:

| what | files |
|---|---|
| your sites and settings | `sites.py`, `pyoccult_config.py` (created from `src/pyoccult/templates/pyoccult_config.py` on first use), `csv_exports.py` (the columns of the CSV buttons; created at the first CSV download) |
| downloaded data | SPICE kernels (`*.bsp`, `*.bpc`, `*.tls`, `*.tpc`, ~120 MB), Gaia catalogs (`gaia_dr3_g16/` ~4 GB, `gaia_dr3_g18/` ~13 GB), `data/ObsCodes.html` (MPC observatory list) |
| your results | `pyoccult.db` (the results database: every search run and its events, kept per "results list", and the favorites), `hits_log.csv` (+ `.runs.jsonl`: the current results list, exported from the database after each search), `hits_report.html`, `maps/` (KML, previews, globe plots), `favorites/` (map and preview copies of the favorites), `picks/` (saved picks), `targets.py`, `pick_events.csv` |

**Which folder is the data folder** (first match wins; `pyoccult setup --status`, the GUI's About box and its
start-up line show the one in use and why):

1. `PYOCCULT_HOME=<folder>`: for a single run (testing, a second setup side by side).
2. The saved setting, written by `pyoccult setup --home <folder>` or by the first setup of an installed copy.
3. A clone or unpacked ZIP (the folder with `pyproject.toml`): **the PyOccult folder itself**. This is the usual case
   with `git clone` / ZIP plus uv or pip.
4. Otherwise (an installed copy without a setting): `PyOccult` in your home folder.

`pyoccult setup --home <folder>` moves the data folder from now on (also for a clone). Files are not moved: setup
tells you if the old folder holds data of yours; move or link it yourself (big catalog folders can be linked).

**Per system:**

| | Linux | macOS | Windows |
|---|---|---|---|
| default data folder (installed copy) | `~/PyOccult` | `~/PyOccult` (`/Users/<you>/PyOccult`) | `%USERPROFILE%\PyOccult` (`C:\Users\<you>\PyOccult`) |
| saved setting (path of the data folder) | `~/.config/pyoccult/home` (or `$XDG_CONFIG_HOME/pyoccult/home`) | `~/Library/Application Support/PyOccult/home` | `%APPDATA%\PyOccult\home` |
| cache (`cache_path` in `pyoccult_config.py`): asteroid orbit files, SBDB data | `/dev/shm` (RAM, emptied on reboot) | the system temp folder (`$TMPDIR`, under `/var/folders/...`) | the temp folder (`%TEMP%`) |
| Python environment | `.venv/` in the PyOccult folder (uv and pip) | same | same |
| uv's own downloads (shared by all uv projects; `uv cache dir`, `uv python dir`) | `~/.cache/uv`, `~/.local/share/uv/python` | same as Linux | `%LOCALAPPDATA%\uv\cache`, `%APPDATA%\uv\python` |

On Windows, choose a data folder that is **not synced to OneDrive** (Documents and Desktop often are): the Gaia
catalog would be uploaded to the cloud. The cache can be set to any folder with `cache_path`; it is refilled when
needed.

**Settings kept in your browser** (per browser, not in the data folder): the GUI's list heights, the favorites'
time display (UT / Local / Site) and similar view choices.

**To remove PyOccult:** delete the PyOccult folder (code, `.venv` and, for a clone, your data), the data folder if it
is elsewhere, and the saved setting file above if it exists. The cache empties itself (RAM or temp folder); uv's
downloads can be cleared with `uv cache clean`.

## Site Configuration and Run Setup

All settings live in `pyoccult_config.py` (a Python file: edit it, keep the names). The search, the pick tool and the
report read it from the project folder.

**Observing sites** are kept apart from the settings, in `sites.py` (yours, not in git). `pyoccult/setup.py` creates it
on the first run (see step 4), or copy `src/pyoccult/templates/sites_example.py` to `sites.py` yourself; without `sites.py` the example site
(New York City Hall) is used:

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
| `focal_mm` | 100 x `aperture_cm` (f/10) | focal length, mm: with `sensor_mm` gives the camera field of the event preview |
| `sensor_mm` | (5.6, 3.2) | camera sensor width and height, mm |

Events are judged with OWC's General Observability Criterion: an event is kept if

    StarMag < 5 log10(aperture_cm) + 2.5 log10(MaxDuration / frames) + 8.5 + mag_adjust

(minus the extinction loss at the star's altitude, if enabled). The faintest star searched is the one that passes at the
longest usable exposure, `MaxDuration / frames = max_exp_s`: G 15.0 at 25 cm, G 16.5 at 50 cm.

`default_site` is used unless the environment variable `PYOCCULT_SITE` names another one, so one site can be run
without editing anything, or several in a batch:

```bash
PYOCCULT_SITE=field pyoccult search
for s in home field; do PYOCCULT_SITE=$s pyoccult pick -o pick_$s.csv --targets-file ""; done
```

**Search window and targets**

| Setting | Example | Meaning |
|---|---|---|
| `ct, days, spn` | `"2026-10-01T00:00:00", 20, 3600` | search start (UTC) and number of days; `spn` (window length, s) is used only by the old `"windows"` mode |
| `targets` | `["218001", "305580"]` | asteroid numbers as strings. Taken from `targets.py` when it exists (written by `pyoccult/pick.py`), else the list in the `except ImportError:` branch |
| `targets_source`, `picks_dir` | `"auto"`, `"picks"` | `"auto"`: use the saved pick of the site covering the search window if there is one, else `targets`; `"list"`: always `targets` |
| `max_shadow_dist` | `20` | km you can travel: an event is logged if the shadow edge passes within this of your site (0 = only from home); a site's `reach_km` overrides it |
| `search_mode` | `"corridor"` | `"corridor"` (default, fast, needs the local Gaia catalog) or `"windows"` (old per-hour archive queries) |
| `write_globes`, `globe_style` | `True`, `"color"` | Occult-style whole-Earth plot per event (`maps/<event>_globe.svg`, needs `write_maps`): `"color"` (sea, land, night side, like OWC's globe) or `"lines"` (black on white, like Occult's plot) |
| `companion_radius_arcsec`, `gaia_online_check` | `4.0`, `True` | close and double stars: neighbours within this radius blend into the star image, so the drop is recomputed with their light (marked with a warning sign in the report); the online check asks the Gaia archive once per run for Gaia's double-star hints and neighbours the local catalog leaves out (GUI Search tab switch; skipped when offline). ABOUT.md Part 6 |
| `star_parallax`, `light_deflection` | `True`, `True` | astrometric corrections of the star: seen from the Earth (Gaia parallax), and the light bending by Sun, Jupiter and Saturn (ABOUT.md Part 6). Off reproduces the results before 0.10.0 |
| `min_mag_drop` | `0.1` | events with a smaller magnitude drop are not logged; also caps the star magnitude searched per asteroid |
| `corridor_step_s` | `600` | path step of the corridor candidate scan, s |
| `gaia_local_dir`, `gaia_local_gmax` | `"gaia_dr3_g16"`, `16.0` | local Gaia catalog folder and its faintest G (see "Local Gaia catalog"); the environment variable `PYOCCULT_CATALOG=<folder>` chooses another catalog for one run |

**Observer**

| Setting | Example | Meaning |
|---|---|---|
| `LAT`, `LON`, `ELE` | from the site | the chosen site (see "Observing sites" above); `site_name` holds its name |
| `MIN_STAR_ALT`, `MAX_SUN_ALT` | from the site | the site's `min_alt` and `max_sun_alt` |
| `MAG_MIN` | from the site | faintest star (Gaia G) searched: the site's `mag_limit`, else from its aperture; at most `gaia_local_gmax` |
| `pick_aperture_cm`, `pick_frames`, `pick_mag_adjust`, `pick_extinction`, `pick_min_dur_s` | from the site | the site's equipment (used by the pick tool) |
| `ALT_MARGIN` | `3.0` | the early visibility gate is this much looser than the final test, so it never rejects a real event |
| `atm_extinction` | `0.0` | atmospheric extinction for low altitudes, mag per airmass (0 = off, ~0.2 typical, ~0.3 hazy); a star at altitude h counts as fainter by `atm_extinction * (airmass - 1)`; a site's `extinction` overrides it |

**Pick tool** (`pyoccult/pick.py`, see below)

| Setting | Example | Meaning |
|---|---|---|
| `pick_hmax` | `17.0` | asteroids with H below this (`--all` ignores it) |
| (equipment) | from the site | aperture, frames, MagAdjust, extinction and limits come from the chosen site |

**Output and caches**

| Setting | Example | Meaning |
|---|---|---|
| `hits_output_cvs_file` | `'hits_log.csv'` | results are appended here |
| `write_maps`, `map_dir` | `True`, `"maps"` | write a KML ground track for every logged event |
| `write_previews` | `True` | write an event preview (SVG) for every hit next to its KML |
| `preview_mag_limit`, `preview_field_factor` | `16.0`, `3.0` | faintest star drawn; preview field = this x the camera field (at least 10′) |
| `default_sigma3_km` | `10.0` | path uncertainty used when JPL Horizons has none |
| `cache_path` | `/dev/shm` or the temp folder | asteroid orbit files and SBDB downloads (RAM on Linux, emptied on reboot) |
| `sbdb_max_age_days` | `30` | asteroid size and orbit downloads are refreshed after this many days |
| `earth_pck_max_age` | `7` | the Earth orientation kernel (`earth_latest_high_prec.bpc`) is refreshed after this many days |
| `force_cleanup` | `False` | `True` deletes and re-downloads the SPICE kernels at start-up |

**Earth orientation coverage.** `earth_latest_high_prec.bpc` holds measured Earth orientation up to its "last datum"
(about the day NAIF made the file) and a prediction for about three months after that. At start-up `pyoccult/search.py`
checks the file's age (refreshed after `earth_pck_max_age` days) and prints both dates, e.g.
`Earth PCK of 2026-09-29T17:07:04: measured to 2026-09-29, predicted to 2026-12-26`. The report header repeats them
and says whether the search window uses measured or predicted values. The prediction is accurate to a few
milliseconds of Earth rotation, about a metre on the ground. A search window that ends after the file's coverage
stops at start-up: shorten it, or delete the file and rerun to fetch a newer one.

Results are appended to `hits_log.csv` (a rerun appends again; the report drops duplicates). Each hit also records
`calc_s` (its calculation time), `airmass`, `extinction_mag` and `mag_margin` (magnitudes below OWC's observability
limit, after extinction). At the end of a run `pyoccult/search.py` prints a summary (total time, start-up, asteroid data
loading, search, maps, time per asteroid and per exact solve, counts) and appends it, with the site, equipment and
limits, as one line to `hits_log.runs.jsonl`; the report shows the latest one in its header.


## Local Gaia catalog (required)

The corridor search (the default) needs the Gaia stars along each asteroid's path. The Gaia archive took many minutes
per asteroid for that, or hung (it warns it is unstable while DR4 is being prepared), so the stars come from a local,
magnitude-limited copy that you build once, or download ready-made from Zenodo
([doi:10.5281/zenodo.23113337](https://doi.org/10.5281/zenodo.23113337), G <= 16 and G <= 18, same files as a build):

```
pyoccult setup                       # does all of it (kernels, catalog, bright-star index)
pyoccult gaia build            # the catalog alone; folder and G limit from gaia_local_dir / gaia_local_gmax
pyoccult gaia build --dir gaia_dr3_g18 --gmax 18 --workers 6
pyoccult gaia status
pyoccult gaia zenodo --dir gaia_dr3_g18 --gmax 18   # or the ready-made copy from Zenodo
```

`pyoccult/setup.py --gmax N` passes another limit through to this build (see step 4).

* It streams all of Gaia DR3 `gaia_source` from ESA's CDN (3386 files, **753 GB download**), keeps G <= gmax with full
  astrometry and ruwe < 1.4 (7 columns, binary), and deletes each download. G <= 18 keeps about 11 GB
  (280 M of 1.81 G stars), G <= 16 about 3 GB.
  At about 1.4 Gbit/s it takes 1.5 to 2 hours.
* It is resumable: rerun the same command after an interruption, finished files are skipped.
* `gaia_local_dir` in pyoccult_config.py must name that folder. pyoccult/search.py refuses a missing or incomplete catalog.
* Several catalogs can sit side by side (e.g. `gaia_dr3_g16` and `gaia_dr3_g18`). Choose one per run with
  `PYOCCULT_CATALOG=gaia_dr3_g16 pyoccult search` (the pick tool follows it too), or in the GUI header;
  `pyoccult setup --status` lists the catalogs it finds.
* A strip lookup takes about 1 s (2 s in the Galactic bulge), no network. Gaia is not cached elsewhere any more.
* Stars fainter than `gaia_local_gmax` are not searched, whatever `MAG_MIN` says.

**Adding a catalog later.** Run setup again with the limit you want, e.g. `pyoccult setup --gmax 16`.
It asks Zenodo or ESA as on the first run and installs into its own folder `gaia_dr3_g<limit>`, next to the ones you
have. The GUI's **Catalog** selector (top right) lists every catalog folder it finds after a restart; a half-built one
is shown as "incomplete n/3386" and runs refuse it until setup has finished it (rerun the same command, it resumes).
If a folder already holds a catalog with another limit (e.g. an interrupted build), setup asks before deleting it.

**Other catalog sources.** The search does not care where a catalog comes from: any folder with a `catalog.json`
(`gmax`, `files`) and, per listed file, the three `.npy` files described at the top of `pyoccult/gaia_local.py`
(stars with the 7 Gaia columns, sky cells, fast movers) is found and can be selected. A converter for another source
only has to write that layout.



## Pick tool: choose targets

`pyoccult pick` (the GUI's Pick tab) finds the actual occultation events at your site for all asteroids in a window,
like an OWC/Occult search, and saves the asteroids of the best events as the targets of `pyoccult search` for that
site and window.

```bash
pyoccult pick                          # window from pyoccult_config.py, site and equipment from sites.py, H < 17
pyoccult pick --start 2026-10-01 --days 14 --top 30
pyoccult pick --all                    # exhaustive: every numbered asteroid (~900k)
pyoccult pick --sort date              # ranking: mag (default, brightest star first), date, margin, drop
```

How it works:

* Asteroids: one bulk download from JPL's Small-Body Database (numbered, H < `pick_hmax`, full-precision orbital
  elements), cached as `PyOccult_sbdb_cache.json` in `cache_path` and refreshed after `sbdb_max_age_days`.
* Orbits are integrated with the planets' gravity for the whole window (agrees with JPL Horizons to about 0.01").
* The stars are the actual Gaia stars along each path, from the bright-star index of the local catalog
  (`pyoccult setup` builds it). Only times when the asteroid is up and the Sun is down are searched.
* Each event is solved for your site and kept if the shadow passes within the asteroid radius + your reach
  (the site's `reach_km`, else `max_shadow_dist`).
* Detection follows OWC's General Observability Criterion with the site's equipment (see "Observing sites"):
  `StarMag < 5 log10(aperture_cm) + 2.5 log10(MaxDuration / frames) + 8.5 + mag_adjust`, optionally less the extinction
  at the star's altitude, plus the hard limits `min_dur_s` and `min_mag_drop`. Bright stars therefore allow short
  events (a G 5.6 star with a 0.25 s event counts), faint stars need long ones. For asteroids whose size is only
  estimated from H, the duration uses the upper size bound, so they are not dismissed too early.

Speed: 465k asteroids (H < 17) over 8 days in about 5 minutes with 4 worker processes (`--workers`).

Memory: per worker about 0.5 GB plus ~55-60 MB per day of the window, so workers x (0.5 GB + 55 MB x days) should
stay well below your free memory (4 workers x 20 days: ~8 GB). The H limit costs time, not memory; the star limit
mainly adds shared, memory-mapped index pages (1.3 GB for G <= 15, ~3.7 GB for G <= 16). For long windows use fewer
workers or split the window. If `top` shows single workers far above 100 % CPU, NumPy runs extra threads in each:
start with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1` for one per worker (usually faster). Details:
ABOUT.md, section 3.5.

Output:

* a ranked table of the events, and `pick_events.csv` with all of them (time, star, magnitude, drop, duration,
  `mag_margin` = magnitudes below the observability limit, distance from the centre line, altitudes, size)
* `targets.py`: the asteroids of the best `--top` events, best first, importable; each line shows its event
* their size data goes to the shared size cache, so the following `pyoccult/search.py` run needs no SBDB lookups for them
* a saved copy per site and window in `picks/` (`<site>__<start>_<days>d.py` + `.csv`; `--picks-dir`, config
  `picks_dir`; private, in `.gitignore`). A new pick of the same site and window replaces it.

**Saved picks are reused.** Picking is the slow part, so you only need it once per site and window: `pyoccult/search.py`
(with `targets_source = "auto"`, the default) takes the newest saved pick of its site whose window covers the search
window, e.g. a pick for Oct 1 + 30 d serves any search from Oct 1 to Oct 31 at that site. It prints which one it
uses, and the report header names it. Without one it falls back to `targets.py` or the list in `pyoccult_config.py`
(`targets_source = "list"` always uses that list). `pyoccult picks list` shows the saved picks;
`pyoccult picks import` saves an existing `targets.py` + `pick_events.csv` (from before saved picks) under
the site and window in its header.

`pyoccult/search.py` then computes these events exactly (JPL Horizons orbit, exact solver, maps). Run it over the same window
(`ct`, `days` in `pyoccult_config.py`; the pick tool uses them as its defaults).

Tune it like OWC: with the same aperture, frames and MagAdjust as in OWC you get OWC's selection. Raise `mag_adjust`
for a dark site or a sensitive camera, lower it for light pollution or a less sensitive one.

**How wide is the corridor?** An event is kept when the shadow's centre line passes the site within
**r_max + reach**: r_max is the upper bound of the asteroid's radius, reach is how far you can travel (the site's
**Reach** in the GUI, `reach_km` in `sites.py`, `--reach` on the command line; default `max_shadow_dist`). It is the
same rule `pyoccult/search.py` uses for logging, and Reach is the only setting for it. Example: reach 25 km and a 10 km
asteroid (r_max about 5 km) keep events whose centre line passes within 30 km of the site, on either side.

* Sigmas: only the size has one. r_max comes from the SBDB diameter + 3 sigma (sigma 15 % of the diameter when SBDB
  gives none); with only H it is the diameter for albedo 0.05 instead of the nominal 0.14 (about 1.7x larger). The
  orbit uncertainty is not added: an event whose path is uncertain by more than your reach can be missed or kept
  wrongly. Raise Reach for such poorly known orbits, and check the 3-sigma lines on the map of the final prediction.
* Positions in the pick are good to about 2 km (orbits integrated from SBDB elements); `pyoccult/search.py` then computes
  the kept events exactly with the JPL Horizons orbit.
* The stars are first gathered from a wider strip (Earth radius + r_max + reach on each side, plus a margin for proper
  motion). That strip is only a coarse pre-filter before the exact solve for the site and does not change the result;
  the search's previews show it as dotted lines along the track ("search corridor").
* Grazes and near misses are kept: anything within r_max + reach. The **Shadow dist** column says "inside" or how
  many km outside the shadow edge your site is.

Without a saved pick, the search reads `targets.py` (written by the last pick) through `pyoccult_config.py`, which
imports it when present; or set `targets = ["218001", ...]` there yourself (with `targets_source = "list"`).


## Web interface (GUI)

`pyoccult/gui.py` is a local web interface (NiceGUI) for everyday use:

```bash
pyoccult                 # opens http://127.0.0.1:8080 in your browser
pyoccult --port 8090 --no-browser
```

* **Site for all runs** and **Catalog** (top right, on every tab): the site and the local Gaia catalog the search
  and the pick tool use (every complete catalog in the project folder is offered). The Search and Pick tabs repeat
  the site.
* **Site**: edit the selected site or add one: set its position by clicking the map (the elevation is looked up), by
  searching a place or from your IP address, and edit its view and equipment (the **Sensor (cameras)** list fills the sensor size); the derived star limit and camera field
  are shown, and "unsaved changes" while the form differs from `sites.py`. Runs read `sites.py`, so unsaved changes
  to the selected site are saved automatically when you start a run. **Save sites.py** rewrites `sites.py` (comments
  in it are not kept); "Default for command-line runs" sets `default_site`, used when the scripts run without the GUI.
* **Pick**: window, H limit or all asteroids, number of targets, workers and ranking, then **Run pick**; the pick is
  saved for the selected site and window. **Saved picks of this site** lists them (newest window first); the
  selected one's events appear in a sortable table, with the target asteroids marked. **Use for search** sets the
  search window to that pick's window. **Reload** rereads the list (e.g. after a pick on the command line).
* **Planets & Moons**: see "Planets and moons" below.
* **Search**: window, targets (the saved pick of the selected site that covers the window, or typed in), **Star G
  limit** (default from the site's telescope, capped at the catalog), minimum drop, maps and previews, the astrometric corrections (stellar parallax, light deflection; both on by default),
  then **Run search**. A line says which saved pick the search will use, or that none
  covers the window.
  The report is rebuilt and shown under **Results** when the run finishes.
* **Results**: the HTML report with its maps and previews. On Linux with KStars running, each event also gets a
  **KStars** button: it points KStars at the target star at the event time, seen from the site, with a field like
  the preview's. "KStars: set its location to the event site" (on by default) moves KStars' location to the site;
  a message says from where, so you can switch back in KStars. Off, KStars keeps its location, and the message warns
  if that is more than 50 km from the site (horizon and altitudes are then for that place). KStars picks the time
  zone of a location it is moved to itself, so its local-time label can be off by an hour or two; the sky is
  computed for the right UT. It uses KStars' D-Bus interface (`gdbus` or `dbus-send`,
  both standard on Linux desktops). Elsewhere (macOS, Windows, KStars not running, the report opened as a file) the
  button does not appear.
  A **Stellarium** button (any system) does the same in Stellarium: the event time with the clock stopped, the
  view on the star and the field; with the checkbox "KStars/Stellarium: set its location to the event site" also
  the site. The button is always shown when the GUI serves the report; a click tries and says if Stellarium did
  not answer. Also `pyoccult stellarium <ra> <dec> <utc> [fov]`.
  **Stellarium setup (once):** the pointing uses Stellarium's **Remote Control** plugin.
  1. Configuration (F2) > Plugins > **Remote Control**: tick **Load at startup**, then restart Stellarium.
  2. Same place, **configure**: tick **Server enabled** and **Enable automatically on startup**. Port **8090** is
     the default (PyOccult uses it); leave "Access requires authentication" off. **Save settings**.
* **Favorites**: the starred events of all searches and sites (see "Run it" above).
* **Log**: the live output of the running job, with **Stop**.

**CSV downloads** (Pick, Results, Planets & Moons, Favorites): by default the columns and values exactly as the
table shows them (without the tools column). Results, Planets & Moons and Favorites come from the results database
(`pyoccult.db`), the pick from its saved file. Which columns, in which order and with which headings is set in
`csv_exports.py` in the data folder (created from `src/pyoccult/templates/csv_exports.py` at the first download):
one list per table of `(heading, source)`, where the source is a value as the table shows it (`"altitude"`,
`"chance"`, ...), a raw field of the event record (`"raw:star"` for the Gaia DR3 id, `"raw:star_ra"`,
`"raw:best_utc"`, ...), `"*"` for all raw fields not listed yet, or a Python function `f(shown, raw)`. A table your
file leaves out keeps the default. The files are UTF-8 with a byte order mark (spreadsheets show ° and the Moon
symbols right). The complete favorites table stays in `favorites/favorites.csv`, the complete search log in
`hits_log.csv` / `bodies_log.csv`.

Settings chosen in the GUI apply to that run only (via `pyoccult/runner.py`); `pyoccult_config.py` is not changed.
Each run is its own process. The GUI listens on this computer only (127.0.0.1), because it can start programs.


## Planets and moons

The GUI tab **Planets & Moons** (after Pick) searches occultations by the planets Mars to Neptune, the dwarf
planet Pluto and their moons: per system the planet and its larger moons (radius 150 km or more) to tick, and one
box for its smaller moons; choose the window and run. No pick is needed (only a few bodies). The results are their own
list (`bodies_log.csv`, `bodies_report.html`), apart from the asteroid search, and the report lists for each event
the **disappearance (D)**, the closest approach and the **reappearance (R)** at your site, the duration, the star,
its altitude, the Moon, the shadow distance and the chance, with map, preview (the planet as a disk with its
moons), globe and KML. On the command line, give the bodies in the target list with a prefix that keeps them apart
from asteroid numbers: `P:Jupiter`, `M:Io`, `M:Titan`, `M:Himalia`, `P:Pluto`, `M:S2003_J2`, ... (`python -m
pyoccult.bodies` lists them).

* The satellite table (`src/pyoccult/data/satellites.json`, 458 moons) comes from JPL Horizons: radius from the
  angular diameter, brightness (H, phase removed with an H-G law, G 0.5; within ~0.2 mag of published values for
  the major moons, Phobos ~1 mag). Where Horizons gives only one of them, the other is estimated like for
  asteroids (marked \* in the tables). 91 moons can be searched; the rest (mostly tiny, recently found moons of
  magnitude 22-25) have neither. The small moons behave like asteroids (faint, narrow paths), but their orbits are
  less certain (rough 3-sigma 50-200 km for the sigma lines and the chance).

* Positions: from JPL Horizons with each search (a small kernel per window, cached), the same ephemeris as NAIF's
  satellite kernels. For offline use, `pyoccult setup --planet-kernels` downloads NAIF's kernel once (Jupiter:
  `jup365.bsp`, 1.1 GB; setup also asks on a first-time setup); PyOccult then uses it.
* Brightness: a star covered by a planet disappears, so planets have no drop limit, only the run's star limit
  (**Star G limit** in the tab; how faint you can see a star next to the planet's glare is up to you); moons
  (Jupiter's are about mag 5) need bright stars for a measurable drop (`min_mag_drop`).
* Planets Mars to Neptune use the planet rule; Pluto (point-like, mag ~14.5) follows the asteroid rules (drop
  limit). Saturn's rings and the planets' atmospheres are not modelled (the shadow is the planet's disk).
* Offline kernels (`--planet-kernels`): Jupiter `jup365.bsp`, Saturn `sat441.bsp`, Neptune `nep097.bsp`, Pluto
  `plu060.bsp`, Mars `mar099.bsp`; Uranus only via Horizons (NAIF splits it per moon, up to 2 GB each).
* Coming: Earth's Moon; later solar eclipses (contacts C1-C4).

## Report: event list, maps and previews

The GUI builds and shows the report after every search; this section is about the page itself and the command.
The events are kept in the results database `pyoccult.db`; after each search the current results list is also
written as `hits_log.csv` (planets and moons: `bodies_log.csv`), a plain-text copy to review or use elsewhere.
`pyoccult report` turns it into a one-page event list with the columns OWC users expect (asteroid, event time UT, star mag, mag drop, max duration, altitude with compass direction, Moon distance, shadow distance from the centre line) plus **Chance** (the probability that the shadow covers your site, from the shadow distance, the shadow radius and the 1-sigma path uncertainty of JPL Horizons; it falls as the shadow distance grows and is a rough guide for far-future events, whose uncertainty is large) and a **Map** button for each event. Standard library only, no install needed.
The page header shows the site, its equipment, the magnitude and observing limits, the statistics of the run with the
saved pick its targets came from, and the Earth orientation data it used (from `hits_log.runs.jsonl`); each event's
calculation time is in `hits_log.csv` (`calc_s`). The **Preview** button shows the event preview: the star field
around the target star at the event date (local Gaia catalog), the camera frame (`focal_mm`, `sensor_mm` of the
site), the target star, the asteroid's position and track with the search corridor (dotted), north up and east
left; for planets and moons the bodies of the system as disks at their size, each moon marked with a cyan +.

```bash
pyoccult report hits_log.csv                           # writes hits_report.html next to the CSV
pyoccult report hits_log.csv -o hits_report.md         # Markdown instead
pyoccult report hits_log.csv --kml-dir maps --max-miss 200 --min-drop 0.3 --title "My events"
pyoccult report hits_log.csv --sort date               # by event time (default --sort mag: brightest star first)
pyoccult report bodies_log.csv -o bodies_report.html --layout bodies   # planets and moons: D, closest, R
```

* The site (header, compass directions, map pin) comes from the run summary in `hits_log.runs.jsonl`, else from
  `pyoccult_config.py` (`sites.py`); `--lat`, `--lon` override it. `map_dir` (default `maps`) or `--kml-dir` locate the KML files.
* `--max-miss KM` and `--min-drop MAG` filter the list; `--no-embed` leaves out the embedded map viewer.
* Each event row links to its KML file (`maps/<asteroid>_<YYYYMMDDTHHMM>*.kml`, written by the shadow-path module). The map button opens an embedded Leaflet map with the centre line (green), the shadow limits (red), the 1-sigma limits (purple, dotted: the real shadow edge stays inside them about 2 times in 3), the 3-sigma limits (orange, dashed) and your site, zoomed to the nearest point of the path. A link there opens that point in Google Maps.

**What the lines mean** (map, KML, globe plot):

| Line | Distance from the centre line | Based on |
|---|---|---|
| shadow limits (red) | radius r | the asteroid's **size** (best estimate) |
| 1-sigma limits (purple, dotted) | r + 1 sigma | the **orbit** uncertainty: where the shadow edge may lie |
| 3-sigma limits (orange, dashed) | r + 3 sigma | the **orbit** uncertainty |
| satellite zone (cyan, dotted; only for asteroids with a known moon) | r + the moon's distance + its radius | where a **satellite's** shadow can pass: its position at the event is not predicted, so it can be anywhere in this band; observers outside the main path may see a short extra event |

* The sigma lines are **not** a size uncertainty. Sigma is the uncertainty of the asteroid's **position** (its
  orbit) at the event time: JPL Horizons' 3-sigma value (RSS), converted to km at the asteroid's distance and divided
  by 3; without a Horizons value it is `default_sigma3_km` (10 km, so sigma 3.3 km). The 1-sigma lines enclose the
  real shadow edge about 2 times in 3, the 3-sigma lines almost always.
* The **size** uncertainty (diameter range, e.g. SBDB diameter +/- 3 sigma, or from H with an assumed albedo) is not
  drawn. It sets the search range (largest likely radius + your reach), and the favorites show it in their size line.
  An **\*** after the asteroid name (Results, Favorites, Pick tab) marks a size estimated from H with an assumed
  albedo (no measured diameter, typical for H above ~15): diameter, duration and shadow width are uncertain by a
  factor of about 1.7, so watch from a wider band or expect a shorter or longer event.
* Not included in sigma: the star's position error (small for bright stars, a few km for faint ones), and the
  direction of the error ellipse (the RSS value is its whole size, so the band is right when its long axis lies
  across the track and too wide when it lies along it). See ABOUT.md, section 2.10.
* View it through a web server for reliable maps: copy the report, the `maps` folder (for the KML links) and, e.g.,
  ```bash
  cp hits_report.html /var/www/html/pyoccult/ && cp -r maps /var/www/html/pyoccult/
  ```
  and open `http://localhost/pyoccult/hits_report.html`. Opened straight from disk (`file://`), the OpenStreetMap
  tiles are blocked because the request carries no Referer. `--tile-url` sets another tile server (an `{z}/{x}/{y}`
  URL template). The map needs internet (Leaflet and tiles load from CDNs); the event table does not.
* To refresh the report after every run, add the report command at the end of your batch job.



### MAPS

To import a KML file into Google Maps, you must use the Google My Maps platform on a web browser. Standard Google Maps allows you to view these custom maps, but the actual file upload has to take place through the My Maps editor.

- Open the Tool: Navigate directly to Google My Maps in your web browser and ensure you are signed into your Google Account. Or go here: https://www.google.com/maps/d
- Create a Map: Click the Create a New Map button in the top left corner.
- Locate the Import Panel: In the left-hand legend window, find the box labeled Untitled layer and click the Import link directly underneath it.
- Upload Your File: Drag and drop your KML files (maps folder) into the box.


### GUI Step by Step in Screenshots
#### Site
Setup sit(s)e and equipment.
<img width="2212" height="1265" alt="image" src="https://github.com/user-attachments/assets/536207cf-5a08-4249-88ba-6089983ceaea" />

#### Pick
Run Auto Pick Targets for site, this narrows the number of potential target asteroids down to close encounters and creates a list of targets the precision search runs on:
<img width="2207" height="1623" alt="image" src="https://github.com/user-attachments/assets/53e12100-2d71-4121-94d9-727e011f2837" />
The pre-screening and picking process is teh most compute intense as all 464740 potential targets from Horizons are screened against stars in their from the site apparent motion corridor.
A computing progress info is updated in the Log window:
<img width="2207" height="481" alt="image" src="https://github.com/user-attachments/assets/a75000a0-65bb-478c-8f7c-2c3f73c9992a" />
<img width="2206" height="1687" alt="image" src="https://github.com/user-attachments/assets/47f8f16a-eaf1-4f72-b90c-778696534b31" />


#### Planets & Moons
Additionally to Asteroid star occultations, larger solar system bodies are also supported since version 0.13.0:
<img width="2207" height="1785" alt="image" src="https://github.com/user-attachments/assets/e4fb9750-eab1-4fd2-b299-790dd53a7d6e" />
Build in Preview and KStars+Stellarium auto pointing on event.
<img width="2210" height="1862" alt="image" src="https://github.com/user-attachments/assets/6f084f97-6b80-40bd-b46e-02b93767e38e" />

#### Search
Run the final precision search for observable events caused by targets as picked or optionally manually entered. Once completed it runs a Gaia online check of 40 event star(s) (close and double stars), that may take some time or even times out if busy, then this extra info is not be available.
<img width="2203" height="1470" alt="image" src="https://github.com/user-attachments/assets/8cca7943-67ed-42d1-b1b3-3a661c3b0af8" />
<img width="2206" height="1687" alt="image" src="https://github.com/user-attachments/assets/4d0ade70-1c09-4508-9846-3b0500718432" />


#### Results
View results table. Detail quick path view map button and star field preview (stars only), use for example Stellarium or KStars (their buttons point them at the event) to further investigate and check for other potentially interesting or interfering objects like planets, etc.. Use the Favorites "Star" Button to move a Event to your Favorites List.
<img width="2206" height="1687" alt="image" src="https://github.com/user-attachments/assets/15f5c986-193f-49de-88ad-eb491e99775e" />
<img width="2200" height="1566" alt="image" src="https://github.com/user-attachments/assets/47317ab9-e597-4fd0-a1e1-244645ee412b" />
Map view, fully interactive:
<img width="2200" height="1566" alt="image" src="https://github.com/user-attachments/assets/9f9454c3-1895-4223-8435-c2f7bdb2ace4" />
<img width="2200" height="1566" alt="image" src="https://github.com/user-attachments/assets/e2d6917e-8bf0-4395-b87b-8b27aca84a7a" />
Globe view:
<img width="2200" height="1566" alt="image" src="https://github.com/user-attachments/assets/1d510f1d-c7e6-44b6-8e4b-6abb3f5477f7" />
Preview:
<img width="2200" height="1566" alt="image" src="https://github.com/user-attachments/assets/030ccb68-8a84-482a-93f9-3b540cec49c4" />
And also KStars + Stellarious auto point options.
Results and labelled with OWC stations (experimental feature):
<img width="2256" height="1933" alt="image" src="https://github.com/user-attachments/assets/150ed7b9-416e-4918-a22c-feec0aeef68b" />


#### Favorites
And finally your "Starred" events in Favorites Manager, a experimental OWC feed/station info can be loaded (disabled by default as experimental):
<img width="2318" height="2146" alt="image" src="https://github.com/user-attachments/assets/a83acd77-8718-45c9-9bff-11c2487878d1" />


## Contributing

Additions and fixes are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) for forking, branches, the tests, working
with Claude Code (`CLAUDE.md` holds the project notes it reads) and pull requests.

## License

PyOccult is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any
later version (`GPL-3.0-or-later`). It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE)
for the full text.

The licence covers the code. The data PyOccult downloads or uses keep their own terms, in particular Gaia DR3
(CC BY-NC 3.0 IGO, see References), and so does the ready-made catalog on Zenodo.

To cite PyOccult, use [CITATION.cff](CITATION.cff) (GitHub: "Cite this repository") or its Zenodo DOI
[10.5281/zenodo.23149371](https://doi.org/10.5281/zenodo.23149371) (all versions; each release also has its own DOI).

## Acknowledgements

Parts of the code and documentation were developed with the help of Claude (Anthropic), an AI model, using
Claude Code. All results were reviewed and validated by the author, among others against Occult Watcher Cloud
(see [VERIFICATION.md](VERIFICATION.md)). Commits made with this help carry a
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line.

Thanks to the IOTA community and the authors of Occult and Occult Watcher Cloud, on whose work and reference
predictions this project builds.

## References
- [Spiceypy] Annex et al., (2020). SpiceyPy: a Pythonic Wrapper for the SPICE Toolkit. Journal of Open Source Software, 5(46), 2050, https://doi.org/10.21105/joss.02050

- [NAIF] https://naif.jpl.nasa.gov/naif

- Acton, C.H.; "Ancillary Data Services of NASA's Navigation and Ancillary Information Facility;" Planetary and Space Science, Vol. 44, No. 1, pp. 65-70, 1996.
DOI 10.1016/0032-0633(95)00107-7
   https://doi.org/10.1016/0032-0633(95)00107-7

- Charles Acton, Nathaniel Bachman, Boris Semenov, Edward Wright; A look toward the future in the handling of space science mission geometry; Planetary and Space Science (2017);
DOI 10.1016/j.pss.2017.02.013
   https://doi.org/10.1016/j.pss.2017.02.013



- [NiceGUI] https://nicegui.io/

### Data

- [Gaia DR3] Gaia Collaboration, Vallenari, A., et al. (2023). Gaia Data Release 3. Summary of the content and survey properties. Astronomy & Astrophysics, 674, A1.
   https://doi.org/10.1051/0004-6361/202243940

- [Gaia] Gaia Collaboration, Prusti, T., et al. (2016). The Gaia mission. Astronomy & Astrophysics, 595, A1.
   https://doi.org/10.1051/0004-6361/201629272

- Gaia acknowledgement, as requested by ESA: "This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national institutions, in particular the institutions participating in the Gaia Multilateral Agreement."
  Gaia data are distributed under the CC BY-NC 3.0 IGO licence (https://www.cosmos.esa.int/web/gaia-users/license).

- [PyOccult Gaia catalog] Local G-limited Gaia DR3 catalog in PyOccult's format (G <= 16, G <= 18), Zenodo.
   https://doi.org/10.5281/zenodo.23113337

- [DE440] Park, R. S., Folkner, W. M., Williams, J. G., Boggs, D. H. (2021). The JPL Planetary and Lunar Ephemerides DE440 and DE441. The Astronomical Journal, 161, 105.
   https://doi.org/10.3847/1538-3881/abd414

- [Horizons] Giorgini, J. D., et al. (1996). JPL's On-Line Solar System Data Service. Bulletin of the American Astronomical Society, 28, 1158. Service: https://ssd.jpl.nasa.gov/horizons/

- [SBDB] JPL Small-Body Database and its APIs (orbital elements, H, G, diameters, albedos): https://ssd.jpl.nasa.gov/tools/sbdb_query.html

- [NEOWISE] Masiero, J. R., et al. (2014). Main-belt asteroids with WISE/NEOWISE: near-infrared albedos. The Astrophysical Journal, 791, 121 (diameters via SBDB; see also the PDS NEOWISE diameters and albedos dataset, Mainzer et al.).
   https://doi.org/10.1088/0004-637X/791/2/121

- [Occultations] Herald, D., Dunham, D. W., et al. Small Bodies Occultations, NASA Planetary Data System, Small
  Bodies Node (V4.0, 2024). https://doi.org/10.26033/ehqs-jp27 , https://sbn.psi.edu/pds/resource/occ.html
  (earlier occultations of an asteroid, shown in the favorites panel).

- [Occultation diameters] Herald, D., et al. (2020). Precise astrometry and diameters of asteroids from occultations
  - a data set of observations and their interpretation. Monthly Notices of the Royal Astronomical Society.
  https://arxiv.org/abs/2010.06086

- [Binary asteroids] Johnston, W. R. (2019). Binary Minor Planets Compilation V3.0, NASA Planetary Data System.
  https://doi.org/10.26033/bb68-pw96 ; kept current at Johnston's Archive, "Asteroids with satellites":
  https://www.johnstonsarchive.net/astro/asteroidmoons.html (known moons: "+moon" in the tables, satellite zone on
  the maps).

- [OpenStreetMap] Map data © OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright

### Methods

- [Occult] Herald, D., Occult (occultation prediction software, the engine behind Occult Watcher Cloud): http://www.lunar-occultations.com/iota/occult4.htm

- [OWC] Pavlov, H., Occult Watcher Cloud (used for validation): https://cloud.occultwatcher.net

- [MPC observatory codes] Minor Planet Center, list of observatory codes (code, longitude, parallax constants, name),
  downloaded once by the GUI into `data/` (not redistributed): https://minorplanetcenter.net/iau/lists/ObsCodes.html

- [H, G] Bowell, E., et al. (1989). Application of photometric models to asteroids. In: Binzel, R. P., Gehrels, T., Matthews, M. S. (eds.), Asteroids II, University of Arizona Press, pp. 524-556.

- [Diameter from H and albedo] Pravec, P., Harris, A. W. (2007). Binary asteroid population. 1. Angular momentum content. Icarus, 190, 250-259 (D = 1329 km / sqrt(albedo) x 10^(-H/5)).
   https://doi.org/10.1016/j.icarus.2007.02.023

### Software

- [Astropy] Astropy Collaboration, Price-Whelan, A. M., et al. (2022). The Astropy Project: Sustaining and Growing a Community-oriented Open-source Project and the Latest Major Release (v5.0) of the Core Package. The Astrophysical Journal, 935, 167.
   https://doi.org/10.3847/1538-4357/ac7c74

- [astroquery] Ginsburg, A., et al. (2019). astroquery: An Astronomical Web-querying Package in Python. The Astronomical Journal, 157, 98.
   https://doi.org/10.3847/1538-3881/aafc33

- [NumPy] Harris, C. R., et al. (2020). Array programming with NumPy. Nature, 585, 357-362.
   https://doi.org/10.1038/s41586-020-2649-2

- [SciPy] Virtanen, P., et al. (2020). SciPy 1.0: fundamental algorithms for scientific computing in Python. Nature Methods, 17, 261-272.
   https://doi.org/10.1038/s41592-019-0686-2

- [pandas] The pandas development team, pandas-dev/pandas: Pandas (Zenodo): https://doi.org/10.5281/zenodo.3509134

- [Leaflet] Leaflet, an open-source JavaScript library for interactive maps (report and GUI maps): https://leafletjs.com


