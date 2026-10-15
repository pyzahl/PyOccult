# PySyzygos: verification

How PySyzygos's predictions were checked: against OccultWatcher Cloud (OWC) search results and Occult's (occult.exe)
event plots, against its own older code paths, and with independent geometry. What is computed and how: `ABOUT.md`;
open items: `ABOUT.md`, Part 6. Updated 2026-10-14 (version 1.0.0).

Contents:

- [1. Against OWC search results](#1-against-owc-search-results)
  - [1.1 How the comparison works](#11-how-the-comparison-works)
  - [1.2 The observer's site, Oct 2-9 2026 (16 events)](#12-the-observers-site-oct-2-9-2026-16-events)
  - [1.3 A second site, sets A and B (OWC data of 2026-10-02, events Oct 3-6 2026; checked 2026-10-03)](#13-a-second-site-sets-a-and-b-owc-data-of-2026-10-02-events-oct-3-6-2026-checked-2026-10-03)
  - [1.4 The second site, 50 events Oct 4-7 2026 (OWC data of 2026-10-04)](#14-the-second-site-50-events-oct-4-7-2026-owc-data-of-2026-10-04)
  - [1.5 The second site, 50 events Oct 8-11 2026 (checked 2026-10-08, PySyzygos 0.14.0)](#15-the-second-site-50-events-oct-8-11-2026-checked-2026-10-08-pysyzygos-0140)
- [2. Against Occult's event plots: star positions](#2-against-occults-event-plots-star-positions)
- [3. Against Occult's geodetic path: (3200) Phaethon, 2019-07-29](#3-against-occults-geodetic-path-3200-phaethon-2019-07-29)
- [4. Internal and geometric checks](#4-internal-and-geometric-checks)
- [5. What the differences mean](#5-what-the-differences-mean)

---

## 1. Against OWC search results

### 1.1 How the comparison works

An OWC search result (OWC's web page, copied as text) is saved as a reference file. `pysyzygos owc-check --ref <file>`
reads its events and its filter line (reach from the shadow, star magnitude limit, minimum duration, aperture,
detection frames, minimum altitude), runs PySyzygos's full search with the same settings at the same site for the
asteroids and window of the list, and compares event by event: time, star, drop, duration, diameter. It runs in its
own results database (`owc_check.db`), apart from your results. The reference sets are private (they name the site)
and are kept with their check output, so every check can be rerun with a later version.

- **Star magnitudes:** PySyzygos's Gaia G equals OWC's "Star Mag (V)" column to 0.01 in every set: OWC shows Gaia G.
- **Twilight events:** OWC lists them with the Sun's altitude after the time ("☼ -7°"); the check reads it and sets
  the Sun limit to the brightest listed altitude + 1 deg (OWC shows no Sun limit).
- **Site elevation:** OWC online computes for the site at sea level; it ignores the given elevation. PySyzygos uses
  the real height. A site h metres up is moved across the track by up to h x cos(star altitude): 958 m gives 0.90 km
  at altitude 20 deg, 0.68 km at 45 deg, 0.33 km at 70 deg; 29 m stays below 30 m. Times change only by fractions of
  a second. So for high sites OWC's path differs from ours by that much, and ours is the right one.
  `pysyzygos owc-check --sea-level` computes our side at elevation 0 for a like-for-like comparison. The sets below
  are at near-sea-level sites unless noted.
- **Match:** same asteroid, time within 10 s; drops compared below 5 mag (above that both are total and differ only
  by the asteroid's estimated brightness), within 0.25 mag; durations within 10 % where both use the same diameter.

### 1.2 The observer's site, Oct 2-9 2026 (16 events)

20 km reach, G <= 15, 25 cm, 4 frames. All 16 found with the same stars; times within 5.4 s (13 within 3 s). Drops
agree within 0.25 mag below 5 mag. Durations agree within 10 % wherever both use the same diameter; 4 events differ
only by diameter (sizes from H, or OWC using another source than NEOWISE). 218001 is the open case (section 5).

### 1.3 A second site, sets A and B (OWC data of 2026-10-02, events Oct 3-6 2026; checked 2026-10-03)

Two OWC filters: A = 25 km from shadow, G <= 15, 15 cm, 8 frames, min altitude 10 (6 events); B = 20 km, G <= 15,
15 cm, 4 frames, min altitude 5 (10 events). Search: `owc-check` with the OWC filter and the Sun below -6. Pick:
`pysyzygos pick` blind over all asteroids with the same filter, Oct 1 + 7 d.

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

- PySyzygos 0.9: 46 of 50 match (8 of the 9 twilight events; they need the Sun-altitude parser, fixed 2026-10-04:
  before, such lines were skipped). Not found: 17871 (Sun -1, altitude 85), 484605, 54567; 281158 17.8 s off.
- PySyzygos 0.10.0 (stellar parallax and light deflection, section 2): 48 of 50 (17871 and 54567 now found: both
  borderline). Times change by at most 0.69 s (median 0.06 s); paths move by up to 10.6 km (772902: parallax
  3.37 mas, asteroid at 5.3 AU). For the 31 events with an expected shift over 0.5 km, the path moved by exactly the
  star's angular shift times the asteroid's distance (ratio 1.00; one event 0.74, from the simplified along-track
  speed in that check).
- PySyzygos 0.14.0 (rerun 2026-10-08, the list below): 48 of 50, the same as 0.10.0. 484605 (H 17.8, ~0.8 km): the
  same star (Gaia DR3 42300553080330752, G 12.74, in the catalog) and time (-1.2 s), but our path passes 29.0 km from
  the site, outside the 20 km reach: an orbit difference of a small asteroid. 281158 (H 17.9, ~0.9 km): 17.1 s
  later than OWC, an along-track orbit difference. Six more small asteroids differ by 2 to 9 s (🟠), all of them
  with diameters of 0.9 to 2.7 km.

Full lists by star magnitude, as `pysyzygos owc-check --markdown` writes them. ✅ match; 🟠 match, but the time
differs by more than 1.5 s (bold); 🔴 OWC event not found, or time or drop outside the match limits; 🔵 an event only
PySyzygos lists. Δt = PySyzygos minus OWC; Star G for a missing event is OWC's magnitude; Shadow dist = PySyzygos's
distance of the site from the centre line; OWC-implied diameter = OWC's duration x our shadow speed.

| | Asteroid | OWC time (UT) | Δt (s) | Star G | Drop ours / OWC | Duration ours / OWC (s) | Diameter ours / OWC-implied (km) | Shadow dist (km) | Result |
|---|---|---|---:|---:|---|---|---|---:|---|
| ✅ | (21641) Tiffanyko | 2026-10-06 04:26:26 | +0.5 | 8.10 | 10.85 / 10.89 | 0.79 / 0.95 | 3.04 / 3.66 | 1.1 | match, *size differs* |
| ✅ | (797051) 2010 WA80 | 2026-10-05 02:45:29 | +0.2 | 9.47 | 12.33 / 13.18 | 0.21 / 0.28 | 1.55 / 2.08 | 9.7 | match, *size differs* |
| ✅ | (19714) 1999 UD | 2026-10-04 06:38:06 | +1.0 | 10.29 | 6.70 / 6.69 | 0.57 / 0.61 | 3.26 / 3.50 | 11.8 | match |
| ✅ | (111287) 2001 XT47 | 2026-10-04 00:55:26 | +1.0 | 10.42 | 9.25 / 9.30 | 0.80 / 0.86 | 5.57 / 6.00 | 20.5 | match |
| ✅ | (16556) 1991 VQ1 | 2026-10-04 10:31:25 | +1.0 | 10.59 | 7.91 / 7.98 | 0.22 / 0.21 | 6.35 / 5.95 | 0.9 | match |
| ✅ | (133490) 2003 SR271 | 2026-10-06 00:28:48 | +0.8 | 11.29 | 8.59 / 8.66 | 0.26 / 0.28 | 3.16 / 3.35 | 18.0 | match |
| ✅ | (219500) 2001 FN124 | 2026-10-05 09:35:27 | +0.3 | 11.33 | 9.45 / 9.45 | 0.31 / 0.27 | 3.17 / 2.76 | 8.5 | match, *size differs* |
| ✅ | (695487) 2015 XX349 | 2026-10-05 10:24:29 | -0.1 | 11.41 | 9.84 / 9.87 | 0.24 / 0.23 | 2.01 / 1.96 | 6.4 | match |
| ✅ | (261744) 2006 AS105 | 2026-10-05 09:30:11 | +0.5 | 11.43 | 8.50 / 8.82 | 0.27 / 0.27 | 2.10 / 2.10 | 4.0 | match |
| ✅ | (121701) 1999 XR78 | 2026-10-04 06:39:56 | +0.4 | 11.93 | 8.56 / 8.48 | 0.66 / 0.67 | 6.78 / 6.91 | 16.5 | match |
| ✅ | (362905) 2012 CB19 | 2026-10-04 10:41:49 | +0.9 | 12.02 | 8.40 / 8.47 | 0.26 / 0.23 | 2.80 / 2.48 | 13.2 | match, *size differs* |
| ✅ | (819762) 2014 MK56 | 2026-10-06 08:46:25 | +1.3 | 12.11 | 11.22 / 11.85 | 0.31 / 0.54 | 0.73 / 1.26 | 17.6 | match, *size differs* |
| ✅ | (17871) 1998 RD58 | 2026-10-04 10:55:05 | +0.9 | 12.11 | 6.35 / 6.43 | 1.82 / 1.79 | 23.53 / 23.14 | 27.8 | match |
| ✅ | (317752) 2003 ST61 | 2026-10-05 07:55:30 | +0.1 | 12.28 | 7.37 / 7.53 | 0.47 / 0.48 | 5.87 / 6.00 | 21.7 | match |
| 🔴 | (484605) 2008 SZ33 | 2026-10-05 05:56:55 |  | 12.74 (OWC) |  / 7.60 |  / 0.27 |  /  |  | **not found** |
| 🟠 | (258134) 2001 RW54 | 2026-10-05 01:22:02 | **+3.1** | 12.79 | 8.18 / 8.38 | 0.50 / 0.50 | 1.64 / 1.64 | 15.0 | match |
| ✅ | (101577) 1999 BV2 | 2026-10-04 10:15:23 | +0.2 | 12.95 | 6.80 / 6.81 | 0.23 / 0.22 | 3.69 / 3.60 | 18.5 | match |
| ✅ | (800) Kressmannia | 2026-10-07 00:43:35 | +0.6 | 12.97 | 1.93 / 1.94 | 0.79 / 0.74 | 15.43 / 14.40 | 3.3 | match |
| ✅ | (5137) Frevert Steve Conard | 2026-10-04 00:23:20 | +0.9 | 13.03 | 4.92 / 4.98 | 0.39 / 0.38 | 6.74 / 6.57 | 7.4 | match |
| ✅ | (125924) 2001 XG236 | 2026-10-07 00:25:53 | +1.1 | 13.07 | 6.94 / 6.96 | 0.36 / 0.34 | 4.99 / 4.75 | 0.2 | match |
| ✅ | (120385) 2005 QB36 | 2026-10-06 23:17:59 | +0.6 | 13.08 | 7.24 / 7.26 | 0.54 / 0.48 | 3.02 / 2.68 | 9.8 | match, *size differs* |
| 🟠 | (167022) 2003 QL33 | 2026-10-04 08:38:45 | **-3.6** | 13.13 | 7.31 / 7.46 | 1.58 / 1.83 | 2.67 / 3.08 | 9.8 | match, *size differs* |
| 🟠 | (269971) 2000 TQ3 | 2026-10-04 22:36:08 | **+2.6** | 13.18 | 7.32 / 7.37 | 0.94 / 0.86 | 2.15 / 1.98 | 1.1 | match |
| ✅ | (323521) 2004 RX100 | 2026-10-04 06:39:54 | +0.6 | 13.27 | 6.58 / 6.82 | 0.22 / 0.20 | 1.69 / 1.54 | 5.5 | match, *size differs* |
| ✅ | (772902) 2018 FG60 | 2026-10-04 06:13:47 | +0.1 | 13.30 | 9.01 / 9.21 | 0.28 / 0.27 | 4.77 / 4.59 | 10.6 | match |
| ✅ | (263663) 2008 GJ109 | 2026-10-06 00:04:31 | +0.1 | 13.34 | 6.89 / 7.01 | 0.26 / 0.24 | 2.69 / 2.53 | 2.5 | match |
| ✅ | (54653) 2000 SB350 | 2026-10-04 07:56:05 | +0.2 | 13.37 | 6.78 / 6.84 | 2.13 / 2.07 | 19.82 / 19.24 | 12.9 | match |
| ✅ | (22336) 1992 EA19 | 2026-10-05 22:33:49 | +0.8 | 13.41 | 7.37 / 7.57 | 0.28 / 0.29 | 6.16 / 6.35 | 6.9 | match |
| ✅ | (5891) Gehrig | 2026-10-04 00:24:56 | +1.2 | 13.45 | 4.79 / 4.78 | 0.40 / 0.38 | 5.51 / 5.30 | 11.4 | match |
| ✅ | (374419) 2005 WB69 | 2026-10-06 09:47:19 | +0.6 | 13.56 | 6.38 / 6.75 | 0.22 / 0.21 | 2.88 / 2.77 | 15.1 | match |
| ✅ | (377378) 2004 RU207 | 2026-10-05 05:11:12 | -0.6 | 13.58 | 5.91 / 5.98 | 0.23 / 0.21 | 1.43 / 1.32 | 11.5 | match |
| 🟠 | (672566) 2014 WD3 | 2026-10-06 00:16:59 | **+9.3** | 13.58 | 7.74 / 7.86 | 0.31 / 0.31 | 0.88 / 0.89 | 14.0 | match |
| ✅ | (146785) 2001 XA253 | 2026-10-05 00:32:36 | +1.5 | 13.59 | 7.16 / 8.22 | 0.43 / 0.49 | 7.69 / 8.77 | 4.4 | match, *size differs* |
| ✅ | (99974) 1981 EJ6 | 2026-10-06 23:52:19 | +0.3 | 13.68 | 6.21 / 6.26 | 0.74 / 0.73 | 6.19 / 6.14 | 1.0 | match |
| 🟠 | (38898) 2000 SD155 | 2026-10-04 06:16:36 | **+2.2** | 13.72 | 6.58 / 6.61 | 0.30 / 0.27 | 2.28 / 2.02 | 7.2 | match, *size differs* |
| 🟠 | (198159) 2004 TA71 | 2026-10-06 02:41:32 | **+2.1** | 13.82 | 7.50 / 7.90 | 0.67 / 0.59 | 1.65 / 1.47 | 6.2 | match, *size differs* |
| ✅ | (21463) Nickerson | 2026-10-06 08:17:06 | +0.1 | 13.85 | 5.91 / 5.94 | 0.23 / 0.22 | 2.61 / 2.52 | 14.8 | match |
| 🔴 | (281158) 2007 DU106 | 2026-10-06 04:39:06 | **+17.1** | 13.98 | 7.42 / 7.48 | 0.78 / 0.72 | 0.95 / 0.87 | 15.4 | **differs: time** |
| ✅ | (265041) 2003 QB7 | 2026-10-05 04:49:20 | -0.0 | 14.13 | 5.71 / 6.02 | 0.32 / 0.31 | 2.39 / 2.33 | 16.7 | match |
| ✅ | (36961) 2000 SL280 | 2026-10-05 06:08:06 | +0.4 | 14.25 | 4.37 / 4.40 | 0.37 / 0.35 | 2.47 / 2.34 | 12.4 | match |
| ✅ | (154858) 2004 RK69 | 2026-10-05 06:51:23 | +1.1 | 14.26 | 5.83 / 6.45 | 0.38 / 0.39 | 3.47 / 3.52 | 5.6 | match |
| ✅ | (18163) Jennalewis | 2026-10-06 01:47:22 | +0.2 | 14.40 | 3.88 / 3.90 | 0.45 / 0.43 | 3.63 / 3.46 | 12.5 | match |
| ✅ | (1718) Namibia | 2026-10-06 04:14:46 | +1.0 | 14.49 | 2.90 / 2.90 | 1.70 / 1.67 | 9.75 / 9.57 | 22.8 | match |
| ✅ | (1803) Zwicky | 2026-10-06 03:02:22 | +0.9 | 14.70 | 2.15 / 2.19 | 0.66 / 0.66 | 9.93 / 9.93 | 21.6 | match |
| ✅ | (63450) 2001 NP17 | 2026-10-06 05:38:02 | +0.9 | 14.89 | 2.51 / 2.57 | 0.73 / 0.79 | 7.96 / 8.59 | 3.7 | match |
| ✅ | (377) Campania | 2026-10-05 10:01:59 | +0.7 | 15.24 | 0.28 / 0.26 | 6.21 / 6.24 | 90.35 / 90.82 | 45.9 | match |
| ✅ | (378) Holmia | 2026-10-05 00:23:25 | -0.1 | 15.54 | 0.55 / 0.60 | 1.55 / 1.51 | 27.83 / 27.15 | 8.9 | match |
| ✅ | (54567) 2000 QZ151  | 2026-10-04 04:24:49 | +0.4 | 15.59 | 4.43 / 4.19 | 1.07 / 1.11 | 9.57 / 9.90 | 23.3 | match |
| ✅ | (589) Croatia | 2026-10-05 09:31:41 | +0.4 | 15.71 | 0.41 / 0.35 | 7.40 / 6.81 | 93.62 / 86.18 | 20.1 | match |
| ✅ | (1336) Zeelandia | 2026-10-06 05:18:23 | +0.1 | 15.90 | 0.47 / 0.46 | 3.92 / 3.94 | 21.44 / 21.54 | 8.7 | match |

### 1.5 The second site, 50 events Oct 8-11 2026 (checked 2026-10-08, PySyzygos 0.14.0)

Same filter as 1.4 (20 km from shadow, G <= 16, min duration 0.2 s, 50 cm, 4 frames, min altitude 0); 9 twilight
events. **44 of 50 match**:

- Same stars (G = OWC "V" to 0.01); times within 1.8 s except 86427 (4.5 s).
- Drops within 0.25 mag; durations within 10 % except 10 events with another diameter (mostly H+albedo estimates;
  largest 12439: OWC-implied 17.0 km, ours 9.5 km from H).
- Two extra hits of ours, outside OWC's listing (20370 on Oct 10, 4451 on Oct 12).

The 6 others, by cause:

| Asteroid | OWC | PySyzygos | Cause |
|---|---|---|---|
| (69085) 2003 BE2 | Oct 8 08:22:20, G 11.62 | not found | star not in the local catalog: Gaia DR3 19293959462010496 is a **2-parameter source** (position only: no parallax, proper motion or RUWE) |
| (325516) 2009 RF60 | Oct 8 01:44:11, G 11.98 | not found | the same: Gaia DR3 91626190888697088, 2-parameter source |
| (549201) 2011 EO72 | Oct 8 05:25:53, G 13.85 | same star, 7 s later, path 46.7 km from the site | orbit: H 18.0 (~0.7 km), poorly known; our path is outside the 20 km reach, OWC's inside |
| (66923) 1999 VL186 | drop 5.23 | drop 4.95 | asteroid brightness (H-only body) |
| (20370) 1998 KR29 | drop 5.14 | drop 4.48 | asteroid brightness; the star is also a close pair (Gaia: two peaks in 64 % of scans; companion G 18.9 at 2.8") |
| (28336) 1999 DZ4 | drop 3.37 | drop 3.11 | asteroid brightness |

The full list (484605's and 549201's kind of miss, and the 2-parameter stars, are discussed in section 5):

| | Asteroid | OWC time (UT) | Δt (s) | Star G | Drop ours / OWC | Duration ours / OWC (s) | Diameter ours / OWC-implied (km) | Shadow dist (km) | Result |
|---|---|---|---:|---:|---|---|---|---:|---|
| ✅ | (10701) Marilynsimons | 2026-10-09 10:26:38 | +0.1 | 10.82 | 7.70 / 7.83 | 0.94 / 0.93 | 5.58 / 5.54 | 6.3 | match |
| ✅ | (297726) 2001 WN31 | 2026-10-08 04:26:42 | -0.7 | 10.85 | 10.47 / 10.53 | 0.39 / 0.39 | 2.05 / 2.05 | 5.9 | match |
| 🔴 | (69085) 2003 BE2 | 2026-10-08 08:22:20 |  | 11.62 (OWC) |  / 8.07 |  / 0.27 |  /  |  | **not found** |
| ✅ | (40640) 1999 RQ181 | 2026-10-08 01:20:06 | +0.7 | 11.75 | 8.37 / 8.38 | 0.43 / 0.43 | 6.87 / 6.91 | 13.6 | match |
| 🔴 | (325516) 2009 RF60 | 2026-10-08 01:44:11 |  | 11.98 (OWC) |  / 7.88 |  / 0.22 |  /  |  | **not found** |
| ✅ | (282065) 1999 VT109 | 2026-10-08 23:06:30 | +0.6 | 12.49 | 8.96 / 9.64 | 0.29 / 0.28 | 5.21 / 5.11 | 13.0 | match |
| ✅ | (438198) 2005 UO74 | 2026-10-08 01:38:44 | +0.1 | 12.53 | 6.72 / 6.96 | 0.45 / 0.47 | 2.68 / 2.82 | 15.0 | match |
| ✅ | (98252) 2000 SY170 | 2026-10-10 23:14:50 | +0.2 | 12.60 | 7.07 / 7.20 | 0.39 / 0.38 | 3.87 / 3.75 | 4.7 | match |
| ✅ | (23509) 1992 HQ3 | 2026-10-09 01:58:46 | +1.0 | 12.62 | 7.37 / 7.49 | 0.20 / 0.20 | 3.61 / 3.61 | 14.9 | match |
| ✅ | (253358) 2003 GL2 | 2026-10-10 06:52:15 | +1.4 | 12.67 | 7.58 / 7.65 | 0.49 / 0.49 | 5.34 / 5.32 | 17.5 | match |
| ✅ | (149937) 2005 SH209 | 2026-10-09 22:32:09 | +0.1 | 12.71 | 8.31 / 9.13 | 0.25 / 0.25 | 4.71 / 4.79 | 5.5 | match |
| ✅ | (95355) 2002 CQ141 | 2026-10-08 00:48:57 | -0.1 | 12.83 | 7.44 / 7.46 | 0.19 / 0.20 | 3.47 / 3.68 | 3.4 | match |
| ✅ | (28220) York | 2026-10-09 05:48:27 | +1.0 | 12.91 | 7.03 / 7.11 | 0.27 / 0.24 | 2.95 / 2.64 | 17.8 | match, *size differs* |
| ✅ | (220684) 2004 RR229 | 2026-10-08 02:19:50 | -0.2 | 13.14 | 7.33 / 7.63 | 0.42 / 0.39 | 2.85 / 2.67 | 10.8 | match |
| ✅ | (116302) 2003 YH61 | 2026-10-10 10:16:47 | -0.1 | 13.20 | 7.67 / 7.67 | 0.27 / 0.27 | 5.94 / 5.89 | 16.7 | match |
| ✅ | (10885) Horimasato | 2026-10-11 01:49:59 | +0.9 | 13.34 | 4.44 / 4.61 | 1.85 / 1.81 | 11.40 / 11.17 | 16.3 | match |
| ✅ | (226212) 2002 VP49 | 2026-10-08 02:36:26 | -1.2 | 13.43 | 4.97 / 4.97 | 0.27 / 0.24 | 1.26 / 1.13 | 2.8 | match, *size differs* |
| ✅ | (427402) 1998 MU15 | 2026-10-09 04:44:54 | +0.7 | 13.44 | 8.45 / 8.67 | 0.34 / 0.34 | 4.06 / 4.04 | 7.1 | match |
| ✅ | (191127) 2002 FC1 | 2026-10-10 00:48:25 | +0.8 | 13.48 | 8.30 / 8.71 | 0.21 / 0.21 | 4.03 / 4.01 | 5.3 | match |
| ✅ | (90571) 2004 GQ15 | 2026-10-09 10:08:03 | +1.4 | 13.66 | 7.16 / 7.16 | 0.37 / 0.36 | 5.70 / 5.59 | 14.4 | match |
| ✅ | (3645) Fabini | 2026-10-11 06:48:36 | +0.5 | 13.70 | 3.00 / 3.12 | 7.73 / 8.52 | 19.93 / 21.95 | 12.2 | match |
| ✅ | (675515) 2015 XB182 | 2026-10-09 09:03:32 | -0.0 | 13.72 | 7.98 / 8.17 | 0.20 / 0.20 | 1.52 / 1.49 | 3.3 | match |
| 🔴 | (66923) 1999 VL186 | 2026-10-09 01:38:08 | -0.3 | 13.73 | 4.95 / 5.23 | 0.28 / 0.26 | 2.59 / 2.38 | 5.1 | **differs: drop** |
| ✅ | (49838) 1999 XS86 | 2026-10-08 22:34:46 | +1.1 | 13.74 | 5.86 / 6.53 | 0.25 / 0.26 | 5.25 / 5.55 | 8.8 | match |
| ✅ | (260114) 2004 PL21 | 2026-10-09 01:01:07 | +0.8 | 13.80 | 5.66 / 5.76 | 0.40 / 0.40 | 5.34 / 5.38 | 7.0 | match |
| ✅ | (64542) 2001 VB120 | 2026-10-08 03:56:50 | +1.1 | 13.82 | 7.30 / 7.39 | 0.71 / 0.63 | 2.98 / 2.63 | 6.2 | match, *size differs* |
| 🟠 | (196907) 2003 TC19 | 2026-10-10 00:55:28 | **+1.8** | 13.85 | 6.69 / 6.87 | 0.77 / 0.60 | 2.03 / 1.58 | 3.8 | match, *size differs* |
| 🔴 | (549201) 2011 EO72 | 2026-10-08 05:25:53 |  | 13.85 (OWC) |  / 7.62 |  / 0.41 |  /  |  | **not found** |
| ✅ | (422727) 2001 FN147 | 2026-10-10 04:00:44 | +0.6 | 13.89 | 8.02 / 8.04 | 1.06 / 1.01 | 3.34 / 3.17 | 2.2 | match |
| ✅ | (105831) 2000 SD148 | 2026-10-10 05:13:06 | +0.2 | 13.89 | 5.03 / 5.10 | 0.41 / 0.42 | 5.56 / 5.71 | 7.1 | match |
| 🔴 | (20370) 1998 KR29 | 2026-10-08 22:44:06 | +0.5 | 13.92 | 4.48 / 5.14 | 0.37 / 0.37 | 7.66 / 7.66 | 5.1 | **differs: drop** |
| ✅ | (91643) 1999 TX91 | 2026-10-10 10:03:20 | +0.3 | 13.96 | 5.64 / 5.88 | 0.38 / 0.35 | 6.26 / 5.70 | 3.9 | match |
| ✅ | (33900) 2000 KS55 | 2026-10-08 01:40:44 | +0.3 | 13.96 | 3.90 / 3.91 | 0.42 / 0.41 | 2.60 / 2.53 | 12.4 | match |
| 🟠 | (86427) 2000 BG25 | 2026-10-08 06:28:16 | **+4.5** | 14.09 | 6.06 / 6.10 | 0.67 / 0.58 | 2.47 / 2.12 | 3.1 | match, *size differs* |
| ✅ | (21014) Daishi | 2026-10-10 01:45:03 | +0.8 | 14.15 | 5.24 / 5.18 | 0.77 / 0.75 | 7.68 / 7.47 | 0.8 | match |
| ✅ | (109581) 2001 QO274 | 2026-10-08 03:57:15 | +0.4 | 14.15 | 4.52 / 4.50 | 0.67 / 0.69 | 8.55 / 8.78 | 10.0 | match |
| ✅ | (158211) 2001 SQ67 | 2026-10-10 03:56:49 | +0.3 | 14.18 | 5.48 / 5.45 | 0.51 / 0.45 | 1.87 / 1.66 | 10.6 | match, *size differs* |
| ✅ | (77113) 2001 DU74 | 2026-10-08 09:24:47 | +0.3 | 14.18 | 5.56 / 5.65 | 0.38 / 0.37 | 7.84 / 7.71 | 2.8 | match |
| ✅ | (19441) Trucpham | 2026-10-10 00:18:48 | +0.0 | 14.59 | 4.00 / 4.07 | 0.64 / 0.56 | 5.09 / 4.43 | 10.3 | match, *size differs* |
| ✅ | (86146) 1999 RA194 | 2026-10-08 04:17:49 | +0.3 | 14.65 | 3.75 / 3.63 | 0.89 / 0.92 | 7.30 / 7.56 | 17.0 | match |
| ✅ | (4451) Grieve | 2026-10-11 01:25:56 | +0.6 | 14.66 | 1.02 / 1.06 | 0.57 / 0.51 | 12.96 / 11.58 | 6.2 | match, *size differs* |
| ✅ | (16156) 2000 AP39 | 2026-10-09 01:42:00 | +0.7 | 14.68 | 3.48 / 3.48 | 1.54 / 1.49 | 16.88 / 16.37 | 8.2 | match |
| ✅ | (14221) 1999 WL | 2026-10-10 05:06:49 | +0.1 | 14.69 | 3.45 / 3.57 | 0.59 / 0.58 | 3.46 / 3.41 | 15.9 | match |
| ✅ | (6142) Tantawi | 2026-10-08 08:44:20 | -0.2 | 14.81 | 4.29 / 4.04 | 0.68 / 0.59 | 9.17 / 7.94 | 7.3 | match, *size differs* |
| ✅ | (57875) 2001 YV114 | 2026-10-09 08:35:20 | +0.2 | 14.84 | 4.29 / 4.38 | 0.82 / 0.81 | 9.06 / 8.97 | 15.0 | match |
| ✅ | (50333) 2000 CZ57 | 2026-10-10 02:11:13 | +1.2 | 14.85 | 2.20 / 2.32 | 0.88 / 0.84 | 5.92 / 5.67 | 10.7 | match |
| 🔵 | (4451) | 2026-10-12 04:39:53 (ours) | | 14.86 | 0.91 / — | 0.56 / — | 12.96 / — | 24.5 | **only ours** |
| ✅ | (12439) Okasaki | 2026-10-10 07:56:21 | +0.1 | 14.86 | 3.18 / 3.15 | 0.71 / 1.26 | 9.52 / 16.99 | 14.4 | match, *size differs* |
| ✅ | (3999) Aristarchus | 2026-10-09 02:02:02 | +0.8 | 15.14 | 1.54 / 1.56 | 1.66 / 1.67 | 18.27 / 18.42 | 2.9 | match |
| 🔵 | (20370) | 2026-10-10 23:24:17 (ours) | | 15.15 | 3.30 / — | 0.36 / — | 7.66 / — | 9.5 | **only ours** |
| ✅ | (32650) 4070 P-L | 2026-10-10 03:16:47 | +0.7 | 15.27 | 3.52 / 3.64 | 1.96 / 1.81 | 4.37 / 4.03 | 5.8 | match |
| 🔴 | (28336) 1999 DZ4 | 2026-10-09 00:53:41 | +0.5 | 15.82 | 3.11 / 3.37 | 1.40 / 1.42 | 12.76 / 12.93 | 13.8 | **differs: drop** |

---

## 2. Against Occult's event plots: star positions

Occult's event plot prints the star's "astrometric" position. Compared with PySyzygos's star direction it shows which
corrections Occult applies.

**16556 (Oct 4 2026, elongation 65 deg, morning twilight; Occult's 1-sigma (0.9 x 0.2) mas).** Occult's star position
differed from PySyzygos's (Gaia DR3 with proper motion only, version 0.9) by 4.5 mas at PA 280, nearly the direction
away from the Sun (PA 286). Expected if Occult applies the light deflection (6.34 mas away from the Sun) and the
stellar parallax (Gaia parallax 1.198 mas x sin 65.4 deg = 1.09 mas towards the Sun): 5.25 mas at PA 286; the
residual 0.75 mas is within Occult's 1-sigma. So Occult includes both. What moves the path is the star relative to
the asteroid (whose light is bent too, 3.71 mas): 2.63 mas differential deflection minus 1.09 mas parallax =
1.54 mas, about 2.7 km across the track at 2.42 AU, about 1.7 of Occult's 1-sigma. Both corrections were then built
into PySyzygos 0.10.0 (`ABOUT.md`, Part 6, "Gravitational light deflection and stellar parallax"). Afterwards the star
moved by 1.55 mas (predicted 1.54), and Occult's printed position minus ours (Gaia + parallax + full star deflection,
Occult's "astrometric" place) went from 4.52 mas to 0.90 mas, within Occult's 1-sigma; the rest may be Occult's star
catalog or its propagation (to ask the IOTA experts).

**30819 (Oct 11 2026 at the observer's site, elongation 164 deg, control case near opposition).** Occult
4.2025.6.12, JPL#55 orbit: 1-sigma (4.0 x 0.5) mas in PA 76, diameter 5.8 +/- 0.6 km; star TYC 0041-00123-1 = Gaia DR3
2514569868519950720 (G 9.67, parallax 3.339 mas). PySyzygos 0.10.0 (parallax 0.944 mas, deflection 0.008 mas
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

## 3. Against Occult's geodetic path: (3200) Phaethon, 2019-07-29 ** PRELIMINARY RESULTS -- PENDING DETAILS FROM OCCULT RUN **

A whole path, not only one event time: Occult's listing of the shadow's centre line and limits on the Earth, compared
point by point with PySyzygos's path at the same instants. Both computed on the same day (2026-10-14), so both use the
same JPL orbit solution. (Occult was run by Steve Preston, IOTA; his listing and plot are kept privately in
`owc_refs/occult_paths/` with the comparison scripts.)

**The two predictions**

| | Occult | PySyzygos |
|---|---|---|
| Version, date | Occult v4.2026.8.29, "Prediction of 2026 Oct 15.0" | 1.0.0, 2026-10-14 |
| Orbit | "JPL#1016+Ephem" | JPL solution #1016 (SBDB solution date 2026-10-14), Horizons SPK |
| Star | HIP 24973, Mv 7.3; "astrometric" RA 5h20m54.7283s, Dec +40°53'05.373" | Gaia DR3 194811405789498112, G 7.29 (= HIP 24973), propagated, + parallax 3.78 mas, + light deflection 7.39 mas (star minus asteroid) |
| Size | D 5.0 ± 0.4 km (DAMIT), 7.2 mas | D 6.25 km (SBDB), r 3.125 km |
| Path | "at MSL": 732 points every 1.45 s, 11:03:39.82-11:21:22.40 UT, centre, path limits, error limits | WGS84 ellipsoid, height 0 (`paths.shadow_path`, as for the KML) |
| Other | 1 km = 0.092 s, 1 mas = 0.064 s; max duration 0.46 s; 1-sigma (0.9 x 0.2) mas in PA 99; Phaethon's parallax 9.233" | regular search at a test site on the path (lon -111.49, lat 37.19, height 0): 11:19:35.031 UT, 0.217 km from the centre line, 0.56 s |

Phaethon was 0.95 AU from the Earth: 1 mas = 0.69 km in the fundamental plane (Occult: 5.0 km = 7.2 mas, the same).

**Method.** For each of Occult's 732 times (UTC -> TDB with the SPICE leap-second kernel), PySyzygos's shadow axis
was computed at exactly that instant with the same function that draws its maps (`paths.shadow_path`, star direction
and radius of the search's event; the event's debug path file, `debug_save_paths = True`). Two comparisons:

1. *On the ground*: Occult's centre point minus ours, split along and across our ground track (our ground velocity
   at that instant); along-track also in seconds.
2. *In the fundamental plane* (through the Earth's centre, perpendicular to the star; x east, y north): Occult's
   ground point, turned to J2000 with the Earth orientation at that instant, projected into the plane, minus our shadow
   axis there. Unlike the ground differences, these are not stretched where the star is low. A difference in the star
   or asteroid direction is a constant offset here; a difference in the Earth's rotation is not (it depends on where
   the point is), so a least-squares fit separates the two.

**On the ground (selected rows; Occult minus PySyzygos; across: positive to the left of the motion)**

| UT | Star alt | Across (km) | Along (km) | Along (s) | Path width Occult / ours (km) | In the plane x, y (km) | (mas) |
|---|---|---|---|---|---|---|---|
| 11:03:39.82 | 4 | +0.283 | +4.026 | +0.027 | 37.09 / 44.44 | -0.459, +0.153 | -0.66, +0.22 |
| 11:04:21.98 | 21 | +0.444 | +0.462 | +0.017 | 8.06 / 9.69 | -0.541, +0.038 | -0.78, +0.05 |
| 11:06:28.44 | 42 | +0.583 | +0.354 | +0.024 | 6.01 / 7.41 | -0.680, +0.010 | -0.99, +0.01 |
| 11:08:34.90 | 54 | +0.648 | +0.397 | +0.032 | 5.68 / 7.05 | -0.755, +0.007 | -1.09, +0.01 |
| 11:10:41.36 | 62 | +0.705 | +0.462 | +0.041 | 5.54 / 6.92 | -0.817, +0.001 | -1.18, +0.00 |
| 11:12:47.83 | 65 | +0.712 | +0.445 | +0.040 | 5.51 / 6.89 | -0.774, -0.062 | -1.12, -0.09 |
| 11:14:54.29 | 61 | +0.710 | +0.560 | +0.048 | 5.57 / 6.94 | -0.788, -0.037 | -1.14, -0.05 |
| 11:17:00.75 | 51 | +0.660 | +0.700 | +0.054 | 5.65 / 7.10 | -0.757, +0.001 | -1.10, +0.00 |
| 11:19:07.21 | 37 | +0.546 | +0.926 | +0.056 | 6.10 / 7.61 | -0.664, +0.060 | -0.96, +0.09 |
| 11:20:31.52 | 23 | +0.482 | +1.422 | +0.056 | 7.46 / 9.19 | -0.604, +0.087 | -0.88, +0.13 |
| 11:21:22.40 | 3 | +0.294 | +6.790 | +0.036 | 38.04 / 44.59 | -0.411, +0.085 | -0.60, +0.12 |

All 732 points: across +0.283 to +0.730 km (mean +0.615), along +0.016 to +0.062 s (mean +0.042 s). With the star
above 20 deg (681 points): across +0.426 to +0.730 km (mean +0.631), largest distance 1.74 km (it grows towards the
ends of the track only because the ground speed does: 0.04 s there are kilometres along the track).

**Fit in the fundamental plane (all 732 points)**

| Model | Result | Residual rms (max) |
|---|---|---|
| constant offset | x -0.724 km (-1.05 mas), y +0.023 km (+0.03 mas) | 70 m (313 m) |
| constant offset + Earth rotation | x -0.658 ± 0.005 km, y +0.003 ± 0.003 km, rotation = UT1 -202 ± 14 ms | 66 m (289 m) |
| the same, star above 20 deg (681 points) | x -0.689 ± 0.005 km, y +0.002 ± 0.003 km, UT1 -147 ± 13 ms | 55 m |

A time offset cannot be fitted separately: over 18 minutes the shadow moves on a nearly straight line in the plane,
so a time offset and a constant offset along the motion are the same. The residual of 55-70 m is about the
listing's rounding (whole arcseconds, about 30 m on the ground, stretched where the star is low; times to 0.01 s).

**The star corrections decide it.** The same comparison with PySyzygos's star corrections switched off
(`star_parallax`, `light_deflection`); every variant leaves the same 70 m rms around a constant offset, only its size
changes:

| PySyzygos star direction | Across, star > 20 deg (km) | Along (s) | Constant offset in the plane x, y (mas) |
|---|---|---|---|
| Gaia + parallax + deflection (default) | +0.43 to +0.73 | +0.016 to +0.062 | -1.05, +0.03 |
| Gaia + deflection | +2.21 to +2.51 | +0.14 to +0.31 | -4.73, +0.92 |
| Gaia + parallax | -3.18 to -2.73 | -0.43 to -0.21 | +6.13, -1.71 |
| Gaia only | -1.32 to -0.96 | -0.18 to -0.09 | +2.45, -0.82 |

So Occult applies both, as found from its star positions in section 2.

**Occult's printed star position** ("astrometric") minus PySyzygos's (mas):

| PySyzygos star direction | RA x cos(Dec) | Dec |
|---|---|---|
| Gaia only (propagated to the date) | +6.86 | -1.94 |
| Gaia + parallax | +10.53 | -2.83 |
| Gaia + deflection | -0.32 | -0.19 |
| Gaia + parallax + deflection | +3.36 | -1.08 |

Occult's printed place is Gaia DR3 propagated plus the light deflection, without the stellar parallax, to within its
printing precision (about 1 mas); the parallax then enters its path geometry, since the path agrees only with it.
(For 16556 in section 2, Occult's printed place fitted Gaia + parallax + deflection; whether its printing has changed
since or the parallax was small there, 1.1 mas against 3.8 mas here, is open.) The deflection is "star minus
asteroid" in both: Phaethon's own light is bent too, by the Sun 1.93 mas (x -1.929, y +0.470 mas in the plane;
the star's 9.105 mas: x -9.105, y +2.217; Jupiter and Saturn below 0.001 mas). Deflecting only the star would move
Occult's printed place by 1.9 mas from ours; it agrees to 0.3 mas.

**What the difference is**

- **Same geometry to about 1 mas.** Apart from one constant offset of 0.66-0.72 km (about 1.0 mas) east-west in the
  fundamental plane, Occult's centre line and PySyzygos's agree to the listing's rounding along the whole track, from
  3 deg star altitude on one side of the Earth to 3 deg on the other. That covers the shadow geometry, the projection
  onto the Earth, the ellipsoid and the time scales. The offset is about Occult's 1-sigma path uncertainty
  (0.9 x 0.2 mas) and PySyzygos's (path 1 sigma 0.69 km).
- **Where the 1 mas comes from (open).** Not the star: Occult's printed place equals ours to 0.3 mas. Most likely the
  asteroid's position: Occult reports "JPL#1016+Ephem", which suggests that it propagates JPL's orbital elements
  itself, while PySyzygos takes JPL Horizons' own ephemeris of the solution (an SPK file). For Phaethon (perihelion
  0.14 AU, where general relativity and the solution's non-gravitational terms matter) 1 mas between two
  propagations is plausible. To be checked with Occult's geocentric position of Phaethon at one instant, or the
  event's elements, and with a second event of a main-belt asteroid in a different geometry.
- **Earth rotation (indication).** The fitted rotation equals UT1 -147 to -202 ms (formal error 13-14 ms; the
  formal errors are optimistic, as rounding residuals are correlated). UT1 - UTC on 2019-07-29 was -162 ms (IERS
  Bulletin B). So Occult's Earth rotation for this past date appears to differ from the measured one by about
  UT1 - UTC, as if it rotated the Earth with UTC; PySyzygos uses the measured Earth orientation (NAIF's high-precision
  Earth orientation file with IERS data). It adds at most about 75 m east-west (0.16 s of the Earth's rotation at the
  equator) and improves the fit only from 70 to 66 m rms, so it is an indication, not a finding; to ask the Occult
  side.
- **Earth model.** PySyzygos computes on the WGS84 ellipsoid at height 0. Occult's listing is "at MSL" (mean sea level,
  the geoid): if that means height 0 on the geoid rather than on the ellipsoid, a point moves by the geoid height
  divided by the tangent of the star's altitude towards the star's azimuth: geoid heights are tens of metres, so
  tens of metres at most where the star is not low. Below what this comparison can resolve.
- **Path width** differs only by the diameter: Occult 5.5 km where PySyzygos has 6.9 km at 64 deg star altitude, that
  is 5.0 km (DAMIT) against 6.25 km (SBDB) across the track.

**Found on the way (PySyzygos):** the event's path file and KML start only at 11:06:49 (Occult: 11:03:40): the path's
time span is centred on the time at the observer's site, here near the end of the track, so its first three minutes
were cut. Fixed after this comparison: the span is now centred on the shadow axis's closest approach to the Earth's
centre, and the path runs 11:03:44-11:21:17 (Occult 11:03:40-11:21:22; the ends are within one sample step, about
9 s here). And the whole-Earth view failed for a search window ending soon after the event (it asks for the
asteroid's position a day later): to fix.

---

## 4. Internal and geometric checks

- **Corridor search vs the old windows search** (23 asteroids, 20 days, 200 km reach): all 40 old hits with G <= 18
  found, within 1.4 ms and 0.8 m (after the solver fix of 2026-10-01); 10 more real hits. The other old hits were on
  stars fainter than the catalog's G 18.
- **Solver** (2026-10-01): the closest approach is solved for the offset from the window centre (a bounded minimiser
  over raw ephemeris time had a ~12 s tolerance); `tests/test_solver.py`.
- **Pick screen** (blind, 465k asteroids, Oct 1 + 8 d, 20 km reach): all 13 OWC reference events with H < 17 among its
  39 events; the 14th (819762, H 18.45) with `--all`; times within 5 s, drops and durations as the search.
- **Orbits of the pick** (integrated from SBDB elements): 102 asteroids against JPL Horizons, worst 0.01".
- **Pre-screens** (0.16.0, 2026-10-10; `ABOUT.md` 3.7), all at the observer's site unless stated:
  - Region pre-screen (500 km around the site, Oct 10 + 20 d, built with the first version): the pick with it found
    38 of the full pick's 39 events, identical in star and time (0.0 s), screening 10273 of 464740 asteroids in
    ~10 s. The 39th lay 19 min after the window end, beyond the build's orbit grid; the grid now reaches 12 h beyond.
  - Region test against dense sampling (1000 asteroids, 20 d, 500 km box): the first version (41 samples) missed 55 of
    256 asteroids (21 %); 161 samples with the widened tests miss none against 1281 samples (13 % extra).
  - Shadow elements (2039 asteroids incl. the 39 with events, 20 d): quadratic misfit at most 0.3 km (median 0.000);
    site test kept 40 asteroids, all 39 with events among them; the exact pick screen on the same asteroids found
    those 39.
  - Whole Earth, Oct 17 + 4 d, all 464740 asteroids with H < 17 (1.73 M events, 132 MB, 13.5 min with 4 workers):
    pick with it 134 asteroids, the same 12 events as the full pick (asteroids, stars, times identical), 14 s
    against 210 s.
  - Index and region test against the exact site test (G <= 13.2 events of the same file): nothing dropped for the
    site at reach 200/45/100 km and star >= 0/10/5 deg, for 20 random sites in a 500 km box, and for sites in
    Iceland, Sydney, Svalbard and Tierra del Fuego; the index passes 14-26 % of the events to the exact test. A first
    index that took the reach as ground km dropped 1 % at the loosest limits (low-altitude events seen off the track):
    found and fixed with `ground_reach`.
- **Near-Earth asteroids, historic events** (2026-10-12; four test cases given without locations): (3200) Phaethon
  occulting HIP 24973 on 2019-07-29 ~11:20 UT and UCAC4 646-021974 on 2021-10-03 "17:30 UT"; (99942) Apophis occulting
  TYC 0789-01041-1 on 2021-04-04 ~05:24 UT and TYC 1929-01244-1 on 2021-05-06 ~03:00 UT. Demanding: small objects
  close to the Earth (Apophis 0.14-0.17 AU: 1" is ~100 m, and its position seen from different places on the Earth
  differs by up to ~1').
  1. *Stars*: HIP 24973 through the Gaia archive's Hipparcos cross-match; the others as the only bright Gaia star
     within the asteroid's parallax range of its Horizons position at the given time (for HIP 24973 the same star).
     All four have full astrometry (5-parameter, RUWE 0.87-1.22) and are in the local main catalog.
  2. *Geometry from the Earth's centre* (Horizons SPK for the date, the local Gaia star with proper motion, parallax
     and light deflection, `paths.shadow_path` on WGS84): the shadow reaches the Earth in all four cases.
  3. *The regular PySyzygos search* at a test site placed on each computed centre line (dark, star above 20 deg) found
     each event by itself, on that star, within 1-3 m of the centre line and at the same second:

  | Event | PySyzygos (test site) | Gaia DR3 star | Shadow on the Earth | Duration, drop | Path 1 sigma |
  |---|---|---|---|---|---|
  | Phaethon 2019-07-29 | 11:19:35.0 UT (lon -111.49, lat 37.19) | 194811405789498112, G 7.29 | 11:04-11:21 UT | 0.56 s, 8.9 mag | 0.69 km |
  | Phaethon 2021-10-03 | 16:58:44.0 UT (lon 157.34, lat 27.25) | 199543119717831424, G 12.02 | 16:46-17:12 UT | 0.75 s, 6.6 mag | 0.43 km |
  | Apophis 2021-04-04 | 05:21:53.1 UT (lon -104.66, lat 27.49) | 650172153566702208, G 11.01 | 04:51-05:53 UT | 0.14 s, 6.1 mag | 0.55 km |
  | Apophis 2021-05-06 | 02:57:36.3 UT (lon -110.80, lat 28.91) | 681575923641521536, G 11.57 | 02:16-03:48 UT | 0.18 s, 7.0 mag | 0.57 km |

  Three given times lie on the computed tracks (the 2019 Phaethon test site in Utah/Arizona at 11:19:35 matches
  ~11:20, where that event was observed). **The Phaethon 2021-10-03 "17:30 UT" does not fit**: no other Gaia star down
  to G 17 lies within 14" of Phaethon then, and with the only candidate the shadow left the Earth at 17:12 (closest
  approach 16:59): the given time is probably rounded or wrong (to be checked at its source). The 2019 Phaethon path
  was later compared point by point with Occult's (section 3). This is a consistency
  check (corridor search, exact solver, WGS84 ground track, star corrections agree for very close objects); an
  absolute check needs the observers' positions and timings (open).
- **Whole-Earth pre-screen on another computer** (2026-10-11, Apple M4, 32 GB, macOS, 8 workers): a 30-day
  whole-Earth pre-screen with the supplement (Oct 11 + 30 d, G <= 16: 14,867,681 events of 458,051 asteroids,
  1.1 GB + 0.34 GB index, built in 77 min). Picks for two sites (one in the US, one in Europe), Oct 11 + 20 d, with
  it and without it (the full pick over all 464,740 asteroids): the pre-screen picks screened 3,050 and 2,417
  asteroids and gave the same 260 and 259 events, identical in every field (time, star, drop, duration, miss
  distance, supplement flags: 37 and 30 events on supplement stars), and the same 80 targets each.
- **2-parameter stars: (4089) Galbraith, 2026-10-13** (2026-10-12): PySyzygos predicted a central event at a site
  (1.6 km) on Gaia DR3 3383655504436521856 (G 9.82, 2-parameter, ipd_frac_multi_peak 41 %: a close double, UCAC4
  573-029535/029536 2.9" apart); OWC (star U029535) put the path over 100 km away. With UCAC5's proper motion
  (-4.0, -13.0 +- 1.7 mas/yr; UCAC4: -5.6, -15.8) the path lies 206 km from the site, 7.4 s earlier, +-27 km (1 sigma)
  from the star; UCAC4's pm gives ~250 km. Fixed by `supplement_pm` and the star uncertainty in the path sigma.
- **High-RUWE supplement** (2026-10-10; `ABOUT.md` 2.4): (86288) 1999 UC45 occulted Gaia DR3 2846821043820040832
  (G 11.73, RUWE 1.65) on 2026-09-30 at 05:28:2x UT, observed from three California sites (1.17 s at one,
  https://www.dr-ricknolthenius.com/events/20260930-1999UC45/index.html). The star was not in the local catalog
  (RUWE >= 1.4 left out), so the full pick for that night at one of the sites found 3 events without it. With the
  supplement (8.0 M stars to G 16, 0.42 GB, built in 106 min): 4 events, among them 86288 at 05:28:26 UT on that
  star, 3.3 km from the centre line, 1.17 s, drop 5.24 mag, flagged "RUWE 1.65". The same check showed that no
  catalogued small body (JPL SB Identification, numbered or not) came near any star brighter than G 16 in that
  field at the time of the unexplained 3.5 s dip of a reference star a minute later (nearest: 44" from a G 15.5 star).
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
  exports, Stellarium pointing, pre-screens (regions, fit check, global file and selection) and shadow elements
  (fit, ground track, gap margin).

---

## 5. What the differences mean

- **Times** agree within a few seconds (mostly under 2 s). Larger differences are small asteroids (under ~3 km):
  2 to 9 s for six of them and 17 s for 281158 (H 17.9) in section 1.4, 4.5 s for 86427 in 1.5. That is the
  along-track part of the orbit difference between JPL Horizons and OWC's orbits.
- **Stars** are always the same; G matches OWC's magnitude column to 0.01.
- **Drops** agree within 0.25 mag below 5 mag. Larger differences come from the asteroid's brightness (H-G with
  G 0.15 here; OWC's phase law or its V conversion is unknown), up to 0.66 mag for single asteroids; above 5 mag both
  drops are total anyway. **218001** is the open case: OWC 1.56 mag and 0.51 s, PySyzygos 12.97 mag and 0.25 s. The
  duration difference is the diameter (OWC 3.56 km, PySyzygos 1.77 km from H); the drop is unexplained (hypothesis,
  unverified: the 5.6 mag star's angular diameter makes the event partial; `ABOUT.md`, Part 6).
- **Durations** differ where the diameters differ: OWC often has a measured or catalogued diameter where PySyzygos
  estimates one from H (marked * in the tables).
- **Missing stars:** PySyzygos's local catalog keeps only Gaia stars with a full astrometric solution (parallax,
  proper motion) and RUWE < 1.4. Gaia's 2-parameter sources (position only) and poorly measured stars (often
  unresolved doubles) are left out, so their events are never predicted; OWC lists them (2 of 50 in section 1.5).
  Open item: keep them in the catalog, flagged (a 2-parameter star's position error grows with the years since 2016,
  as its proper motion is unknown).
- **Small asteroids** (H above ~17, under ~1 km): their orbits are poorly known, and JPL's and OWC's orbits can differ
  by tens of km across the track, so an event can fall inside one reach and outside the other: 484605 (our path
  29 km from the site) and 549201 (47 km), both with OWC's within 20 km.
- **Paths across the track:** since 0.10.0 PySyzygos applies stellar parallax and light deflection as Occult does
  (section 2); for high sites OWC online is off by the site's elevation effect (1.1). A whole path compared with
  Occult's (section 3: Phaethon 2019, same orbit solution) agrees to about 1 mas, with 55-70 m rms around that.
- **More events than OWC:** the pick keeps an event if it can be observable (upper size bound); a few search events
  lie just outside OWC's listing (window edges, the nominal vs upper size).
