# PyOccult: verification

How PyOccult's predictions were checked: against OccultWatcher Cloud (OWC) search results and Occult's (occult.exe)
event plots, against its own older code paths, and with independent geometry. What is computed and how: `ABOUT.md`;
open items: `ABOUT.md`, Part 6. Updated 2026-10-08 (PyOccult 0.14.0).

Contents:
1. [Against OWC search results](#1-against-owc-search-results)
2. [Against Occult's event plots: star positions](#2-against-occults-event-plots-star-positions)
3. [Internal and geometric checks](#3-internal-and-geometric-checks)
4. [What the differences mean](#4-what-the-differences-mean)

---

## 1. Against OWC search results

### 1.1 How the comparison works

An OWC search result (OWC's web page, copied as text) is saved as a reference file. `pyoccult owc-check --ref <file>`
reads its events and its filter line (reach from the shadow, star magnitude limit, minimum duration, aperture,
detection frames, minimum altitude), runs PyOccult's full search with the same settings at the same site for the
asteroids and window of the list, and compares event by event: time, star, drop, duration, diameter. It runs in its
own results database (`owc_check.db`), apart from your results. The reference sets are private (they name the site)
and are kept with their check output, so every check can be rerun with a later version.

- **Star magnitudes:** PyOccult's Gaia G equals OWC's "Star Mag (V)" column to 0.01 in every set: OWC shows Gaia G.
- **Twilight events:** OWC lists them with the Sun's altitude after the time ("☼ -7°"); the check reads it and sets
  the Sun limit to the brightest listed altitude + 1 deg (OWC shows no Sun limit).
- **Site elevation:** OWC online computes for the site at sea level; it ignores the given elevation. PyOccult uses
  the real height. A site h metres up is moved across the track by up to h x cos(star altitude): 958 m gives 0.90 km
  at altitude 20 deg, 0.68 km at 45 deg, 0.33 km at 70 deg; 29 m stays below 30 m. Times change only by fractions of
  a second. So for high sites OWC's path differs from ours by that much, and ours is the right one.
  `pyoccult owc-check --sea-level` computes our side at elevation 0 for a like-for-like comparison. The sets below
  are at near-sea-level sites unless noted.
- **Match:** same asteroid, time within 10 s; drops compared below 5 mag (above that both are total and differ only
  by the asteroid's estimated brightness), within 0.25 mag; durations within 10 % where both use the same diameter.

### 1.2 The observer's site, Oct 2-9 2026 (16 events)

20 km reach, G <= 15, 25 cm, 4 frames. All 16 found with the same stars; times within 5.4 s (13 within 3 s). Drops
agree within 0.25 mag below 5 mag. Durations agree within 10 % wherever both use the same diameter; 4 events differ
only by diameter (sizes from H, or OWC using another source than NEOWISE). 218001 is the open case (section 4).

### 1.3 A second site, sets A and B (OWC data of 2026-10-02, events Oct 3-6 2026; checked 2026-10-03)

Two OWC filters: A = 25 km from shadow, G <= 15, 15 cm, 8 frames, min altitude 10 (6 events); B = 20 km, G <= 15,
15 cm, 4 frames, min altitude 5 (10 events). Search: `owc-check` with the OWC filter and the Sun below -6. Pick:
`pyoccult pick` blind over all asteroids with the same filter, Oct 1 + 7 d.

| Asteroid | Set | Time diff (s) | Star G = OWC V | Drop ours / OWC | Duration ours / OWC (s) | Diameter ours / OWC-implied (km) | Pick |
|---|---|---|---|---|---|---|---|
| (218001) 2001 XQ72 | A | +0.5 | 5.61 | 12.97 / 1.56 | 0.25 / 0.51 | 1.77 (H) / 3.56 | found (H < 17) |
| (17834) 1998 HL43 | A, B | +0.4 | 7.39 | 9.65 / 9.83 | 0.66 / 0.73 | 8.64 / 9.49 | found |
| (21641) Tiffanyko | A, B | -0.1 | 8.10 | 10.85 / 10.89 | 0.79 / 0.95 | 3.04 / 3.66 | found |
| (19714) 1999 UD | A, B | +1.0 | 10.29 | 6.70 / 6.69 | 0.57 / 0.61 | 3.26 / 3.50 | found |
| (111287) 2001 XT47 | A, B | +0.8 | 10.42 | 9.25 / 9.30 | 0.80 / 0.86 | 5.57 / 6.00 | found |
| (56450) 2000 GU80 | A | +0.3 | 11.39 | 8.83 / 8.90 | 0.73 / 0.72 | 6.42 / 6.30 | found (Sun -11.5: needs a Sun limit above -12) |
| (121701) 1999 XR78 | B | +0.4 | 11.93 | 8.56 / 8.48 | 0.66 / 0.67 | 6.78 / 6.91 | found |
| (305580) 2008 YO22 | B | +4.7 | 12.08 | 9.73 / 9.74 | 1.10 / 1.10 | 1.94 (H) / 1.94 | found |
| (819762) 2014 MK56 | B | +1.3 | 12.11 | 11.22 / 11.85 | 0.31 / 0.54 | 0.73 (H) / 1.26 | found |
| (167022) 2003 QL33 | B | -3.0 | 13.13 | 7.31 / 7.46 | 1.58 / 1.83 | 2.67 / 3.08 | found |
| (54653) 2000 SB350 | B | -0.3 | 13.37 | 6.78 / 6.84 | 2.13 / 2.07 | 19.82 / 19.24 | found |
| (70141) 1999 NE18 | B | +0.5 | 14.06 | 6.37 / 6.47 | 4.46 / 4.33 | 4.45 / 4.33 | found |

Search: all 16 OWC events found (A 6/6, B 10/10), the same stars, times within 4.7 s (14 of 16 entries within
1.3 s). Drops agree within 0.18 mag except 218001 (the open case) and 819762 (0.63 mag: both are near-total drops of
a 12 mag star; they differ by the estimated asteroid brightness of an H-only body). Durations differ only where the
diameters differ (OWC-implied diameter = OWC duration x our shadow speed; (H) = ours from H and an assumed albedo).

Pick: all 16 found as well (A with H < 17, B with H < 19 for 819762, H 18.45), times within 5 s of OWC, the same
stars. The B pick lists 30 events in Oct 1-7 against OWC's 10; the extras were not checked one by one (the pick
keeps an event if it CAN be observable: upper size bound, OWC applies the nominal size; e.g. 56450 passes 24 km from
the site, inside our r_max + 20 km, outside OWC's 20 km from the nominal edge).

### 1.4 The second site, 50 events Oct 4-7 2026 (OWC data of 2026-10-04)

20 km from shadow, G <= 16, min duration 0.2 s, 50 cm, 4 frames, min altitude 0; 9 twilight events.

- PyOccult 0.9: 46 of 50 match (8 of the 9 twilight events; they need the Sun-altitude parser, fixed 2026-10-04:
  before, such lines were skipped). Not found: 17871 (Sun -1, altitude 85), 484605, 54567; 281158 17.8 s off.
- PyOccult 0.10.0 (stellar parallax and light deflection, section 2): 48 of 50 (two borderline events now found).
  Times change by at most 0.69 s (median 0.06 s); paths move by up to 10.6 km (772902: parallax 3.37 mas, asteroid
  at 5.3 AU). For the 31 events with an expected shift over 0.5 km, the path moved by exactly the star's angular
  shift times the asteroid's distance (ratio 1.00; one event 0.74, from the simplified along-track speed in that
  check).

### 1.5 The second site, 50 events Oct 8-11 2026 (checked 2026-10-08, PyOccult 0.14.0)

Same filter as 1.4 (20 km from shadow, G <= 16, min duration 0.2 s, 50 cm, 4 frames, min altitude 0); 9 twilight
events. **44 of 50 match**:

- Same stars (G = OWC "V" to 0.01); times within 1.8 s except 86427 (4.5 s).
- Drops within 0.25 mag; durations within 10 % except 10 events with another diameter (mostly H+albedo estimates;
  largest 12439: OWC-implied 17.0 km, ours 9.5 km from H).
- Two extra hits of ours, outside OWC's listing (20370 on Oct 10, 4451 on Oct 12).

The 6 others, by cause:

| Asteroid | OWC | PyOccult | Cause |
|---|---|---|---|
| (69085) 2003 BE2 | Oct 8 08:22:20, G 11.62 | not found | star not in the local catalog: Gaia DR3 19293959462010496 is a **2-parameter source** (position only: no parallax, proper motion or RUWE) |
| (325516) 2009 RF60 | Oct 8 01:44:11, G 11.98 | not found | the same: Gaia DR3 91626190888697088, 2-parameter source |
| (549201) 2011 EO72 | Oct 8 05:25:53, G 13.85 | same star, 7 s later, path 46.7 km from the site | orbit: H 18.0 (~0.7 km), poorly known; our path is outside the 20 km reach, OWC's inside |
| (66923) 1999 VL186 | drop 5.23 | drop 4.95 | asteroid brightness (H-only body) |
| (20370) 1998 KR29 | drop 5.14 | drop 4.48 | asteroid brightness; the star is also a close pair (Gaia: two peaks in 64 % of scans; companion G 18.9 at 2.8") |
| (28336) 1999 DZ4 | drop 3.37 | drop 3.11 | asteroid brightness |

---

## 2. Against Occult's event plots: star positions

Occult's event plot prints the star's "astrometric" position. Compared with PyOccult's star direction it shows which
corrections Occult applies.

**16556 (Oct 4 2026, elongation 65 deg, morning twilight; Occult's 1-sigma (0.9 x 0.2) mas).** Occult's star position
differed from PyOccult's (Gaia DR3 with proper motion only, version 0.9) by 4.5 mas at PA 280, nearly the direction
away from the Sun (PA 286). Expected if Occult applies the light deflection (6.34 mas away from the Sun) and the
stellar parallax (Gaia parallax 1.198 mas x sin 65.4 deg = 1.09 mas towards the Sun): 5.25 mas at PA 286; the
residual 0.75 mas is within Occult's 1-sigma. So Occult includes both. What moves the path is the star relative to
the asteroid (whose light is bent too, 3.71 mas): 2.63 mas differential deflection minus 1.09 mas parallax =
1.54 mas, about 2.7 km across the track at 2.42 AU, about 1.7 of Occult's 1-sigma. Both corrections were then built
into PyOccult 0.10.0 (`ABOUT.md`, Part 6, "Gravitational light deflection and stellar parallax"). Afterwards the star
moved by 1.55 mas (predicted 1.54), and Occult's printed position minus ours (Gaia + parallax + full star deflection,
Occult's "astrometric" place) went from 4.52 mas to 0.90 mas, within Occult's 1-sigma; the rest may be Occult's star
catalog or its propagation (to ask the IOTA experts).

**30819 (Oct 11 2026 at the observer's site, elongation 164 deg, control case near opposition).** Occult
4.2025.6.12, JPL#55 orbit: 1-sigma (4.0 x 0.5) mas in PA 76, diameter 5.8 +/- 0.6 km; star TYC 0041-00123-1 = Gaia DR3
2514569868519950720 (G 9.67, parallax 3.339 mas). PyOccult 0.10.0 (parallax 0.944 mas, deflection 0.008 mas
applied): offset 2.08 km (2.69 km before), the same time within 0.04 s.

Occult's star position minus ours, four hypotheses (mas):

| Hypothesis | 16556 (65 deg) | 30819 (164 deg) |
|---|---|---|
| Gaia only | 4.52 | 0.09 |
| Gaia + parallax | 5.60 | 0.87 |
| Gaia + deflection | 1.91 | 0.66 |
| Gaia + parallax + deflection (0.10.0) | 0.90 | 0.29 |

Only parallax plus deflection fits both, within sub-mas and within Occult's 1-sigma (0.9 and 4.0 mas). 30819 alone is
a weak test: near opposition the parallax (towards the Sun) and the deflection (away from it) partly cancel. A
sharper test would be a star with parallax > 3 mas at elongation ~90 deg.

---

## 3. Internal and geometric checks

- **Corridor search vs the old windows search** (23 asteroids, 20 days, 200 km reach): all 40 old hits with G <= 18
  found, within 1.4 ms and 0.8 m (after the solver fix of 2026-10-01); 10 more real hits. The other old hits were on
  stars fainter than the catalog's G 18.
- **Solver** (2026-10-01): the closest approach is solved for the offset from the window centre (a bounded minimiser
  over raw ephemeris time had a ~12 s tolerance); `tests/test_solver.py`.
- **Pick screen** (blind, 465k asteroids, Oct 1 + 8 d, 20 km reach): all 13 OWC reference events with H < 17 among its
  39 events; the 14th (819762, H 18.45) with `--all`; times within 5 s, drops and durations as the search.
- **Orbits of the pick** (integrated from SBDB elements): 102 asteroids against JPL Horizons, worst 0.01".
- **Planets and moons** (0.14.0):
  - Ephemeris: the kernel built from Horizons vectors (SPK type 13, 20 min steps) reproduces Horizons to ~1 m;
    NAIF's `jup365.bsp` and Horizons agree to millimetres at sample times.
  - Contact times: for Jupiter events, D and R put the star exactly one Jupiter radius from the planet's centre in an
    independent topocentric computation (0.1 km).
  - Moon brightness (H from Horizons, phase removed with G 0.5): within ~0.2 mag of published values for the major
    moons; Phobos ~1 mag off.
  - All systems searched once (Mars, Saturn and Titan, Pluto and Charon, Himalia, Triton): events with D/R for
    Saturn and Titan, no errors.
- **Tests** (`python tests/<name>.py`, stand-ins for SPICE, astropy and the network): corridor and loop recall, local
  catalog build and lookup, solver convergence at realistic ephemeris times, size cache, pick tool, paths, astrometric
  corrections (deflection and parallax sizes, switches off = unchanged), planets and moons, results database, CSV
  exports, Stellarium pointing.

---

## 4. What the differences mean

- **Times** agree within a few seconds (mostly under 2 s). That is the along-track part of the orbit difference
  between JPL Horizons and OWC's orbits; a few km along the track is well under a second.
- **Stars** are always the same; G matches OWC's magnitude column to 0.01.
- **Drops** agree within 0.25 mag below 5 mag. Larger differences come from the asteroid's brightness (H-G with
  G 0.15 here; OWC's phase law or its V conversion is unknown), up to 0.66 mag for single asteroids; above 5 mag both
  drops are total anyway. **218001** is the open case: OWC 1.56 mag and 0.51 s, PyOccult 12.97 mag and 0.25 s. The
  duration difference is the diameter (OWC 3.56 km, PyOccult 1.77 km from H); the drop is unexplained (hypothesis,
  unverified: the 5.6 mag star's angular diameter makes the event partial; `ABOUT.md`, Part 6).
- **Durations** differ where the diameters differ: OWC often has a measured or catalogued diameter where PyOccult
  estimates one from H (marked * in the tables).
- **Missing stars:** PyOccult's local catalog keeps only Gaia stars with a full astrometric solution (parallax,
  proper motion) and RUWE < 1.4. Gaia's 2-parameter sources (position only) and poorly measured stars (often
  unresolved doubles) are left out, so their events are never predicted; OWC lists them (2 of 50 in section 1.5).
  Open item: keep them in the catalog, flagged (a 2-parameter star's position error grows with the years since 2016,
  as its proper motion is unknown).
- **Small asteroids** (H above ~17, under ~1 km): their orbits are poorly known, and JPL's and OWC's orbits can differ
  by tens of km across the track, so an event can fall inside one reach and outside the other.
- **Paths across the track:** since 0.10.0 PyOccult applies stellar parallax and light deflection as Occult does
  (section 2); for high sites OWC online is off by the site's elevation effect (1.1).
- **More events than OWC:** the pick keeps an event if it can be observable (upper size bound); a few search events
  lie just outside OWC's listing (window edges, the nominal vs upper size).
