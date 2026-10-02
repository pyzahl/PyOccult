import os, sys, math, xml.etree.ElementTree as ET, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyoccult_preview as P

# camera field of view: 2 atan(s / 2f); 5.6 x 3.2 mm at 2500 mm is 7.70' x 4.40'
w, h = P.camera_fov_arcmin(2500.0, (5.6, 3.2))
assert abs(w - 7.7006) < 1e-3 and abs(h - 4.4004) < 1e-3, (w, h)

# synthetic field: target at (100, 20), a star 3' east and 2' north of it, one far outside the field
ra0, dec0 = 100.0, 20.0
east, north = 3.0 / 60 / math.cos(math.radians(dec0)), 2.0 / 60
stars = dict(ra=np.array([ra0, ra0 + east, ra0 + 5.0]), dec=np.array([dec0, dec0 + north, dec0]), g=np.array([11.0, 14.0, 9.0]))
track = [(m, ra0 + m * 0.5 / 3600, dec0) for m in range(-60, 61, 10)]       # 0.5"/min eastwards
svg = P.render_svg(stars, dict(ra=ra0, dec=dec0, g=11.0), track, (w, h), title="T <test> & co", subtitle="s")
root = ET.fromstring(svg)                                                      # valid XML (title is escaped)
ns = "{http://www.w3.org/2000/svg}"
circles = [c for c in root.iter(ns + "circle")]
star_dots = [c for c in circles if c.find(ns + "title") is not None]
assert len(star_dots) == 2, len(star_dots)                                      # the far star is outside the field
field = max(3 * max(w, h), 10.0); scale = P.SIZE / field
c0 = next(c for c in star_dots if c.find(ns + "title").text == "G 11.00")
c1 = next(c for c in star_dots if c.find(ns + "title").text == "G 14.00")
assert abs(float(c0.get("cx")) - P.SIZE / 2) < 0.1 and abs(float(c0.get("cy")) - P.SIZE / 2) < 0.1
assert abs(float(c1.get("cx")) - (P.SIZE / 2 - 3.0 * scale)) < 0.3, "east must be left"
assert abs(float(c1.get("cy")) - (P.SIZE / 2 - 2.0 * scale)) < 0.3, "north must be up"
assert float(c0.get("r")) > float(c1.get("r")), "brighter stars are larger"
poly = next(root.iter(ns + "polyline")); xs = [float(p.split(",")[0]) for p in poly.get("points").split()]
assert xs[0] > xs[-1], "eastward motion goes to the left"
assert "T &lt;test&gt; &amp; co" in svg and "camera 7.7" in svg and "track -60 to +60 min" in svg
print("PREVIEW TESTS PASSED")
