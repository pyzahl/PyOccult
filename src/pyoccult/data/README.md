# data/

`ne_110m_earth.json`: coastlines and land borders for the globe plot (`globe.py`), from Natural Earth
1:110m (`ne_110m_coastline`, `ne_110m_admin_0_boundary_lines_land`, `ne_110m_land` outer rings, https://www.naturalearthdata.com), which is in
the public domain. Coordinates rounded to 0.01 deg, stored as flat lists lon, lat, lon, lat, ...

`occultations_pds.json`: earlier asteroid occultations, a compact extract (per numbered asteroid: number of events and
years, quality counts, best measured profile, shape-model diameter; no chords or observer data) of NASA PDS Small
Bodies Node "Small Bodies Occultations" V4.0 (Herald, Dunham et al., doi:10.26033/ehqs-jp27), public NASA data.
Rebuilt with `python -m pyoccult.occultations build <bundle folder or zip>` (`occultations.py`).
