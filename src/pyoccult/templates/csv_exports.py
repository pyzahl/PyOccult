# csv_exports.py - the columns of the GUI's CSV buttons, one list per table. Your copy is in the data folder (created
# from the template at the first export; not in git); edit it as you like. A table your copy does not list keeps the
# template's columns, so you only need the lists you change.
#
# Each column is (heading, source), in the order of the CSV:
#   "name"          a value as the table shows it (the names are listed under each table below)
#   "raw:<column>"  a column of the search log (hits_log.csv, bodies_log.csv; for favorites the event's record) or of
#                   the pick's pick_events.csv, unformatted, e.g. "raw:star" (Gaia DR3 id), "raw:best_utc",
#                   "raw:star_ra", "raw:star_dec", "raw:min_distance", "raw:path_sigma1_km"
#   "*"             all raw columns not exported already (heading = column name)
#   a function      f(shown, raw) -> value, with shown: the table's values (dict by name), raw: the record (dict)
#                   e.g. ("RA Dec (deg)", lambda shown, raw: f'{float(raw["star_ra"]):.5f} {float(raw["star_dec"]):+.5f}')
# Values are written as text (UTF-8 with a byte order mark, so spreadsheets show the symbols right).

EXPORTS = {
    # Results tab (asteroid search). Names: asteroid, event_time, star_mag, mag_drop, max_dur, altitude, moon_dist,
    # shadow_dist, chance; also event_utc (ISO), gaia_id, kind, diameter_km, size_source, chance_pct, shadow_km
    "results": [
        ("Asteroid", "asteroid"),
        ("Event time (UT)", "event_time"),
        ("Star mag", "star_mag"),
        ("Mag drop", "mag_drop"),
        ("Max dur (s)", "max_dur"),
        ("Altitude", "altitude"),
        ("Moon dist", "moon_dist"),
        ("Shadow dist", "shadow_dist"),
        ("Chance", "chance"),
    ],
    # Planets & Moons tab. Names: body, d_time (date and D), closest, r_time, duration, star_mag, altitude, moon_dist,
    # shadow_dist, chance; and the extra names of "results"
    "bodies": [
        ("Body", "body"),
        ("D (UT)", "d_time"),
        ("Closest (UT)", "closest"),
        ("R (UT)", "r_time"),
        ("Duration", "duration"),
        ("Star mag", "star_mag"),
        ("Altitude", "altitude"),
        ("Moon dist", "moon_dist"),
        ("Shadow dist", "shadow_dist"),
        ("Chance", "chance"),
    ],
    # Favorites tab. Names: those of "results", plus site, status, note, added (as shown), added_utc (full)
    "favorites": [
        ("Asteroid", "asteroid"),
        ("Site", "site"),
        ("Event time (UT)", "event_time"),
        ("Star mag", "star_mag"),
        ("Mag drop", "mag_drop"),
        ("Max dur (s)", "max_dur"),
        ("Altitude", "altitude"),
        ("Moon dist", "moon_dist"),
        ("Shadow dist", "shadow_dist"),
        ("Chance", "chance"),
        ("Status", "status"),
        ("Note", "note"),
        ("Added (UT)", "added"),
    ],
    # Pick tab (saved pick). Names: target (✓ = a search target), number, name, H, utc, star_mag, drop, dur_s,
    # mag_margin, miss_km, star_alt
    "pick": [
        ("Target", "target"),
        ("#", "number"),
        ("Asteroid", "name"),
        ("H", "H"),
        ("UT", "utc"),
        ("G", "star_mag"),
        ("Drop", "drop"),
        ("Dur (s)", "dur_s"),
        ("Margin", "mag_margin"),
        ("Miss (km)", "miss_km"),
        ("Alt", "star_alt"),
    ],
}
