"""pyoccult_astrometry: light deflection and stellar parallax against known values, with a stand-in for SPICE."""
import math, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyoccult_astrometry as A

AU = 1.495978707e8


class FakeSpice:
    """spkpos(target, et, frame, corr, observer) from fixed geocentric positions (km); observer '399' or '0' (SSB)."""
    def __init__(self, geo, earth_ssb=(0.0, 0.0, 0.0)):
        self.geo, self.earth = {k: np.asarray(v, float) for k, v in geo.items()}, np.asarray(earth_ssb, float)

    def spkpos(self, target, et, frame, corr, observer):
        assert frame == "J2000"
        if target == "399" and observer == "0":
            return self.earth, 0.0
        assert observer == "399", observer
        return self.geo[str(target)], 0.0


def star_at(elong_deg):
    """Earth at (1 AU, 0, 0) from the Sun: Earth->Sun = (-1, 0, 0); star at elongation elong in the x-y plane."""
    e = math.radians(elong_deg)
    return np.array([-math.cos(e), math.sin(e), 0.0])


FAR = 1e30                                                # a body/asteroid so far away it does not matter
sun = np.array([-AU, 0.0, 0.0])

# 1) star only (asteroid at infinity along the star: its deflection equals the star's -> use deflect() directly)
d90 = A.deflect(star_at(90), -sun, star_at(90), A.GM["10"])
assert abs(np.linalg.norm(d90) * A.RAD2MAS - 4.07) < 0.01, np.linalg.norm(d90) * A.RAD2MAS
assert np.dot(d90, unit_sun := A.unit(sun)) < 0, "deflection pushes the star away from the Sun"
limb = math.degrees(math.asin(696000.0 / AU))
dl = np.linalg.norm(A.deflect(star_at(limb), -sun, star_at(limb), A.GM["10"])) * A.RAD2MAS / 1000
assert abs(dl - 1.75) < 0.01, dl

# 2) star minus asteroid, main-belt asteroid at r = 2.5 AU on the line of sight (table in ABOUT.md)
for elong, want in ((90, 1.16), (60, 2.81), (150, 0.05)):
    u = star_at(elong)
    e_vec = np.array([1.0, 0.0, 0.0])                     # Sun -> Earth, AU
    b = 2 * float(e_vec @ u); D = (-b + math.sqrt(b * b - 4 * (1 - 2.5 ** 2))) / 2
    fs = FakeSpice({"10": sun, "5": [FAR, 0, 0], "6": [FAR, 0, 0], "AST": u * D * AU})
    p, info = A.corrected_star_dir(fs, u, 0.0, 0.0, "AST", parallax=False)
    assert abs(info["deflection_mas"] - want) < 0.01, (elong, info)
    assert abs(A.angle_mas(u, p) - want) < 0.01

# 3) Jupiter at 4.2 AU, star 60" from its centre, asteroid at 1.5 AU in front: ~6.36 mas
jup_dir = A.unit([0.3, 0.9, 0.1])
perp = A.unit(np.cross(jup_dir, [0, 0, 1]))
u = A.unit(math.cos(math.radians(60 / 3600)) * jup_dir + math.sin(math.radians(60 / 3600)) * perp)
fs = FakeSpice({"10": [FAR, 0, 0], "5": jup_dir * 4.2 * AU, "6": [0, 0, FAR], "AST": u * 1.5 * AU})
p, info = A.corrected_star_dir(fs, u, 0.0, 0.0, "AST", parallax=False)
assert abs(info["deflection_by"]["Jupiter"] - 6.36) < 0.05, info
assert np.dot(p - u, jup_dir) < 0, "pushed away from Jupiter"

# 4) stellar parallax: 1.198 mas at elongation 65.4 deg -> 1.198 x sin(65.4) = 1.09 mas towards the Sun
u = star_at(65.4)
fs = FakeSpice({"10": sun, "5": [FAR, 0, 0], "6": [0, 0, FAR], "AST": u * 2.4 * AU},
               earth_ssb=[AU, 0.0, 0.0])                  # SSB at the Sun: Earth 1 AU from it
p, info = A.corrected_star_dir(fs, u, 1.198, 0.0, "AST", deflection=False)
assert abs(info["parallax_mas"] - 1.198 * math.sin(math.radians(65.4))) < 0.002, info
assert np.dot(p - u, A.unit(sun)) > 0, "parallax moves the star towards the Sun"
for bad in (0.0, -0.5, float("nan"), None):                # no parallax, negative or missing: unchanged
    assert A.angle_mas(A.parallax_dir(u, bad, [AU, 0, 0]), u) == 0.0

# 5) both off: unchanged; both on: about the sum, directions opposite (16556-like case)
p, info = A.corrected_star_dir(fs, u, 1.198, 0.0, "AST", parallax=False, deflection=False)
assert A.angle_mas(p, u) == 0.0 and info["parallax_mas"] == 0.0 and info["deflection_mas"] == 0.0
print("ASTROMETRY TESTS PASSED")
