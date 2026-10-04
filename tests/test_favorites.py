"""pyoccult_favorites: add (with copies of map and preview), duplicates, status/note, remove, lookup in a hits log."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyoccult_favorites as F

tmp = tempfile.mkdtemp()
maps, fav = os.path.join(tmp, "maps"), os.path.join(tmp, "favorites")
os.makedirs(maps)
for ext in ("kml", "svg"):
    open(os.path.join(maps, f"17834_20261003T0253.{ext}"), "w").write(f"<{ext}/>")
log = os.path.join(tmp, "hits_log.csv")
open(log, "w").write("target_id,target_name,best_utc,mag\n17834,17834 (1998 HL43),2026-10-03T02:53:07.123,7.39\n"
                     "19714,19714 (1999 UD),2026-10-04T06:38:06.900,10.29\n")

rec = F.find_record(log, "17834", "2026-10-03T02:53:07")
assert rec and rec["mag"] == "7.39", rec
assert F.find_record(log, "17834", "2026-10-03T02:54:00") is None
run = dict(site=dict(name="S", lat=1.0, lon=2.0), run_utc="2026-10-03T12:00:00", limits={}, extra="dropped")
ok, msg = F.add(rec, run, maps, fav)
assert ok and "17834" in msg, msg
assert not F.add(rec, run, maps, fav)[0], "duplicate must be refused"
e = F.load(fav)[0]
assert e["key"] == "17834_20261003T0253" and e["status"] == "planned" and e["site"]["name"] == "S"
assert "extra" not in e["run"] and e["files"] == {"kml": "17834_20261003T0253/17834_20261003T0253.kml",
                                                   "svg": "17834_20261003T0253/17834_20261003T0253.svg"}
os.remove(os.path.join(maps, "17834_20261003T0253.svg"))                     # a later search deletes maps/ files:
assert open(os.path.join(fav, e["files"]["svg"])).read() == "<svg/>"        # the favorite keeps its copy
ok, msg = F.add(F.find_record(log, "19714", "2026-10-04T06:38:06"), None, maps, fav)
assert ok and "no map or preview" in msg, msg
assert F.keys(fav) == ["19714_20261004T0638", "17834_20261003T0253"], "newest first"
assert F.update("17834_20261003T0253", fav, status="observed", note="clear, positive")[0]
assert not F.update("17834_20261003T0253", fav, status="bogus")[0]
assert F.load(fav)[1]["status"] == "observed" and F.load(fav)[1]["note"] == "clear, positive"
assert F.remove("17834_20261003T0253", fav)[0] and not F.remove("17834_20261003T0253", fav)[0]
assert not os.path.isdir(os.path.join(fav, "17834_20261003T0253")) and F.keys(fav) == ["19714_20261004T0638"]
# several at once, cleanup of past events, the page
open(log, "a").write("70141,70141 (1999 NE18),2099-01-03T07:07:42.5,14.06\n")
F.add(F.find_record(log, "17834", "2026-10-03T02:53:07"), run, maps, fav)
F.add(F.find_record(log, "70141", "2099-01-03T07:07:42"), run, maps, fav)
assert len(F.keys(fav)) == 3
assert F.update_many(["17834_20261003T0253", "70141_20990103T0707"], fav, status="clouded")[0]
assert not F.update_many(["17834_20261003T0253"], fav, status="bogus")[0]
assert sorted(e["status"] for e in F.load(fav)) == ["clouded", "clouded", "planned"]
ok, msg = F.cleanup("2050-01-01", fav)                                       # 2026 events are past, 2099 is not
assert ok and "2 favorites removed" in msg and F.keys(fav) == ["70141_20990103T0707"], (msg, F.keys(fav))
assert F.cleanup("2050-01-01", fav)[1].startswith("no favorites before")
page = F.write_page(fav)
html = open(page, encoding="utf-8").read()
assert 'class="favrow" data-key="70141_20990103T0707"' in html and 'id="favall"' in html and "favsetst" in html
assert 'class="mapbtn favbtn"' not in html, "no star buttons on the favorites page"
assert F.remove_many(["70141_20990103T0707", "nope"], fav)[0] and F.keys(fav) == []
print("FAVORITES TESTS PASSED")
