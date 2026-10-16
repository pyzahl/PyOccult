# data/

`ne_110m_earth.json`: coastlines and land borders for the globe plot (`globe.py`), from Natural Earth
1:110m (`ne_110m_coastline`, `ne_110m_admin_0_boundary_lines_land`, `ne_110m_land` outer rings, https://www.naturalearthdata.com), which is in
the public domain. Coordinates rounded to 0.01 deg, stored as flat lists lon, lat, lon, lat, ...

`occultations_pds.json`: earlier asteroid occultations, a compact extract (per numbered asteroid: number of events and
years, quality counts, best measured profile, shape-model diameter; no chords or observer data) of NASA PDS Small
Bodies Node "Small Bodies Occultations" V4.0 (Herald, Dunham et al., doi:10.26033/ehqs-jp27), public NASA data.
Rebuilt with `python -m pysyzygos.occultations build <bundle folder or zip>` (`occultations.py`).

`binaries.json`: known asteroid satellites, a compact extract (per numbered primary: each companion's diameter,
distance and period; satellites seen in occultations) of W. R. Johnston's Binary Minor Planets Compilation V3.0 (NASA
PDS 2019, doi:10.26033/bb68-pw96) and the occultations archive above. Rebuilt with
`python -m pysyzygos.binaries build <compilation zip> <occultations zip>` (`binaries.py`).

`egm96_30min.npy`: the geoid's height above the WGS84 ellipsoid (EGM96, NGA, public domain), a 0.5 deg grid (361 x 720
from 90 N and 0 E, int16 centimetres) sampled from GeographicLib's EGM96 15-minute grid (egm96-15.pgm,
`URL_EGM96_GEOID`); bilinear interpolation: 0.12 m rms, at most 3 m against the 15-minute grid. Used to turn site
elevations above mean sea level into heights above the ellipsoid (`geoid.py`). Rebuilt with
`python -m pysyzygos.geoid build <egm96-15.pgm>`.

`gaia_dr3_rv_fast.npy`: Gaia DR3 radial velocities (source_id, rv, rv_error; sorted by source_id) of the 164,602 stars
where the radial velocity moves the position by more than 0.01 mas within 20 years of Gaia's epoch (pm x |rv| x
parallax > 24445 mas/yr x km/s x mas): the perspective acceleration of nearby fast stars, which the local catalog
(no radial velocities) would otherwise miss. From the Gaia archive (ESA/Gaia/DPAC; query in `starrv.QUERY`, run in
16 source_id ranges below the 50000-row cap for anonymous jobs, 2026-10-16). Rebuilt with
`python -m pysyzygos.starrv build <csv>`.
