"""pyoccult_geo.occult_sites: parsing Occult's InstallSites.zip (fixed-width .site files), without network."""
import os, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyoccult_geo as G

folder = tempfile.mkdtemp()
lines_eu = ("   8.551667  47.376667  469   15  0.0  100 Zurich, Switzerland              1 Zurich, S   1.0 0\r\n"
            "  -2.066667  57.166667    0   15  0.0  100 Aberdeen, Scotland               1 Aberdeen,   0.0 0\r\n")
lines_world = ("   8.551667  47.376667  469   10  0.0  100 Zurich, Switzerland              1 Zurich, S   1.0 0\r\n"
               "-149.985000  61.166667   36   10  0.0  100 Anchorage AK                     1 Anchorage -10.0 0\r\n"
               "   8.216667  49.950000    3   20  0.0  100 _Test                            1 _Test       1.0 0\r\n"
               "this line is not a site\r\n")
with zipfile.ZipFile(os.path.join(folder, "InstallSites.zip"), "w") as z:
    z.writestr("Europe.site", lines_eu)
    z.writestr("World Main.site", lines_world)
G._OCCULT_SITES = None
s = G.occult_sites(folder, url="http://invalid.invalid/none.zip")   # local file present: no download
names = [x["name"] for x in s]
assert names == ["Aberdeen, Scotland", "Anchorage AK", "Zurich, Switzerland"], names   # sorted, merged, _Test skipped
z_ = s[2]
assert (z_["lat"], z_["lon"], z_["ele"], z_["tz"], z_["region"]) == (47.376667, 8.551667, 469.0, 1.0, "Europe")
assert s[1]["lon"] == -149.985 and s[1]["tz"] == -10.0, "west longitudes and negative time zones"
G._OCCULT_SITES = None
assert G.occult_sites(tempfile.mkdtemp(), url="http://invalid.invalid/none.zip") == [], "no file, no network: empty"
print("OCCULT SITES TESTS PASSED")
