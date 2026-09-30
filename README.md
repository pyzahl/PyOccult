# PyOccult
Python Occultation Searcher

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

## 3. Install from requirements.txt
With the environment active, run `pip` to download and install all the listed packages into your isolated environment:

```bash
pip install -r requirements.txt
```

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
  echo 'EDIT IT, RUN IT:'
  ./pyoccult.py
  ```



## Site Configuration and Run Setup:
Currently need to adjust the pyoccult_config.py file to setup a run.

```  
ct, days, spn = "2026-10-01T00:00:00", 10, 3600
targets = ["218001", "305580", "111287", "115181", "229912", "111286", "54653", "70141", "4272"]
max_shadow_dist = 200  ## km

### CONFIG

LAT = 40.9541175
LON = -72.92614552
ELE = 40

MAG_MIN = 20
MIN_STAR_ALT = 10.0     # deg, use the same constants in both gates
MAX_SUN_ALT  = -6.0     # deg, try -12 for faint stars
ALT_MARGIN   = 3.0      # early gate is looser than the final one, so it never rejects a real event
```


ct: Start Date-Time, i.e. first search interval

days: #days to search from start

spn: search interval length in sec (1 hour default, ma yuse up to 3 hours -- this is the window the star motion is assumed to be negligible vs. asteroid's motion)

targets: List of Asteroids (use ID number), must be in JPL's Horizon catalog.

max_shadow_dist: allowable distance from observer's location (set to 0 for no travel is anticipated) (in km). May be used to add extra allowance margin as of shadow's (size, as of max rad from Horizons query) uncertainty.

LAT, LON, ELE: Observer's 3d location in deg, meters

MAG_MIN: minimum magnitude of potential star

MIN_STAR_ALT: minimum star altitude to be observable

MAX_SUN_ALT: max sun altitude to be observable, lower for fainter stars i.e -12 deg

ALT_MARGIN: may adjust, early pre screening gate only


Results are appended (if existing) to hits_log.csv


