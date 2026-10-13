"""Earth orientation coverage (pyoccult.kernels): which loaded files cover a search window; the historic file
(earth_1962_*_combined.bpc) is found by its pattern and loaded before earth_latest_high_prec.bpc. No SPICE."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pyoccult import kernels as K

DAY = 86400.0
Y2000, Y1962, Y2027 = 0.0, -38 * 365.25 * DAY, 27 * 365.25 * DAY        # ET ~ seconds from J2000 (rough is fine)
latest = ("earth_latest_high_prec.bpc", Y2000 - 0.5 * DAY, Y2027)
hist = ("earth_1962_260806_2126_combined.bpc", Y1962, Y2000 + 126 * 365.25 * DAY)

# today's windows: the high-precision file alone covers them
assert K.window_coverage([latest], 26 * 365.25 * DAY, 26 * 365.25 * DAY + 20 * DAY) == (True, "")
# a historic window (1998) without the historic file: refused, "starts before"
ok, why = K.window_coverage([latest], -2 * 365.25 * DAY, -2 * 365.25 * DAY + 5 * DAY)
assert not ok and why == "starts before", (ok, why)
# with the historic file loaded first: covered; also a window across 2000
assert K.window_coverage([hist, latest], -2 * 365.25 * DAY, -2 * 365.25 * DAY + 5 * DAY)[0]
assert K.window_coverage([hist, latest], -3 * DAY, 3 * DAY)[0]
# before 1962: refused even with the historic file
assert K.window_coverage([hist, latest], Y1962 - 10 * DAY, Y1962 + 10 * DAY) == (False, "starts before")
# a gap between two files inside the window is found
gap = [("a", 0.0, 10 * DAY), ("b", 20 * DAY, 30 * DAY)]
assert K.window_coverage(gap, 5 * DAY, 25 * DAY) == (False, "gap") and K.window_coverage(gap, 1 * DAY, 9 * DAY)[0]
assert K.window_coverage([], 0, 1) == (False, "no Earth orientation file loaded")

# the newest historic file by name; loaded before the high-precision one
d = tempfile.mkdtemp()
for n in ("earth_1962_250826_2125_combined.bpc", "earth_1962_260806_2126_combined.bpc", "earth_620120_260806.bpc"):
    open(os.path.join(d, n), "w").close()
assert os.path.basename(K.historic_earth_pck(d)) == "earth_1962_260806_2126_combined.bpc"
assert [os.path.basename(p) for p in K.earth_kernels(d)] == ["earth_1962_260806_2126_combined.bpc", K.EARTH_PCK]
assert K.historic_earth_pck(tempfile.mkdtemp()) is None and K.earth_kernels(tempfile.mkdtemp())[-1].endswith(K.EARTH_PCK)
assert K.EARTH_HISTORIC_RE.fullmatch("earth_1962_260806_2126_combined.bpc") and not K.EARTH_HISTORIC_RE.fullmatch(
    "earth_2026_260806_2126_predict.bpc")
print("KERNEL COVERAGE TESTS PASSED")
