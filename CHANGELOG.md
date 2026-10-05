# Changelog

All notable changes to PyOccult. Newest first. Format: [Keep a Changelog](https://keepachangelog.com), versions:
[semantic versioning](https://semver.org) (MAJOR.MINOR.PATCH). The version and its code name live in
`pyoccult_version.py`; the code name changes at major milestones. Details of the computations: `ABOUT.md`.

## [0.11.1] "New Horizons" - 2026-10-05

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

[0.11.1]: https://github.com/pyzahl/PyOccult/commits/main
[0.11.0]: https://github.com/pyzahl/PyOccult/commit/5abc5f6
[0.10.0]: https://github.com/pyzahl/PyOccult/commit/0047057
[0.9.0]: https://github.com/pyzahl/PyOccult/commit/a2d5c21
