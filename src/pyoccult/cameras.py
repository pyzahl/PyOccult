"""cameras.py - sensors often used for occultations and the cameras built with them, for the Site tab's camera list
(fills sensor width and height). The size is computed from the active pixels and the pixel size of the maker's data
sheet; check yours if it is not listed or uses a cropped readout. Analog video: the nominal size of the format.
"""
from pyoccult.version import __version__

# (sensor, pixels wide, pixels high, pixel size in micrometres, cameras with it); sorted by sensor
SENSORS = [
    ("Aptina AR0130", 1280, 960, 3.75, "ZWO ASI120MM / MC"),
    ("Panasonic MN34230", 4656, 3520, 3.8, "ZWO ASI1600MM / MC, QHY163M / C"),
    ("Sony IMX174", 1936, 1216, 5.86, "ZWO ASI174MM / MC, QHY174M-GPS, QHY174M / C, DVTI+CAM 174"),
    ("Sony IMX178", 3096, 2080, 2.4, "ZWO ASI178MM / MC, QHY5III178M / C"),
    ("Sony IMX183", 5496, 3672, 2.4, "ZWO ASI183MM / MC, QHY183M / C"),
    ("Sony IMX224", 1304, 976, 3.75, "ZWO ASI224MC, QHY5III224C, Unistellar eVscope / eQuinox (first generation)"),
    ("Sony IMX290", 1936, 1096, 2.9, "ZWO ASI290MM / MC, QHY5III290M / C"),
    ("Sony IMX294", 4144, 2822, 4.63, "ZWO ASI294MC Pro, QHY294M / C Pro"),
    ("Sony IMX296 mono, global shutter", 1456, 1088, 3.45, "ASTRID (CAM-MIPI296RAW-Trigger)"),
    ("Sony IMX385", 1936, 1096, 3.75, "ZWO ASI385MC"),
    ("Sony IMX430 mono", 1624, 1240, 4.5, "DVTI+CAM 430"),
    ("Sony IMX432", 1608, 1104, 9.0, "ZWO ASI432MM"),
    ("Sony IMX455", 9576, 6388, 3.76, "ZWO ASI6200MM / MC, QHY600M / C"),
    ("Sony IMX462", 1936, 1096, 2.9, "ZWO ASI462MC, QHY5III462C, ZWO Seestar S50"),
    ("Sony IMX482", 1920, 1080, 5.8, "ZWO ASI482MC"),
    ("Sony IMX533", 3008, 3008, 3.76, "ZWO ASI533MM / MC, QHY533M / C"),
    ("Sony IMX571", 6248, 4176, 3.76, "ZWO ASI2600MM / MC, QHY268M / C"),
    ("Sony IMX585", 3840, 2160, 2.9, "ZWO ASI585MC, QHY5III585C"),
    ("Sony IMX662", 1920, 1080, 2.9, "ZWO ASI662MC"),
    ("Sony IMX678", 3840, 2160, 2.0, "ZWO ASI678MC"),
    ("Sony IMX715", 3840, 2160, 1.45, "ZWO ASI715MC"),
    # analog video: the nominal format (the digitized frame shows about this field)
    ("1/2-inch CCD format", None, None, None, "analog video: Watec 910HX, Mintron 12V6HC-EX", 6.4, 4.8),
    ("1/3-inch CCD format", None, None, None, "analog video: PC165DNR", 4.8, 3.6),
]


def sensor_mm(entry):
    """(width, height) in mm of a SENSORS entry."""
    if len(entry) > 5:
        return entry[5], entry[6]
    _, nx, ny, um, _ = entry
    return round(nx * um / 1000.0, 2), round(ny * um / 1000.0, 2)


def label(entry):
    """'Sony IMX174: 11.34 x 7.13 mm, 1936 x 1216 px of 5.86 um (ZWO ASI174MM / MC, QHY174M-GPS, ...)' for the list;
    its search matches any part, so typing a camera name finds the sensor."""
    w, h = sensor_mm(entry)
    px = f", {entry[1]} x {entry[2]} px of {entry[3]:g} µm" if entry[1] else ""
    return f"{entry[0]}: {w:.2f} × {h:.2f} mm{px} ({entry[4]})"
