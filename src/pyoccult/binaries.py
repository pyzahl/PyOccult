"""binaries.py - known satellites of asteroids (binary and multiple systems), as reference information with the
asteroid: a note in the report and favorites, and the satellite zone on the event map (where a satellite's shadow
can pass: the primary's shadow +/- the satellite's distance plus its radius). The satellite's position at the event
is not predicted (few satellite orbits are known well enough).

data/binaries.json, a compact extract of two NASA PDS Small Bodies Node archives (public NASA data):
  * Binary Minor Planets Compilation V3.0, W. R. Johnston (2019), doi:10.26033/bb68-pw96: per companion its
    diameter, distance from the primary (semimajor axis, km) and orbital period; complete to 2019-03-31. Newer
    discoveries: Johnston's Archive (URL_JOHNSTON_ASTEROID_MOONS), kept current.
  * Small Bodies Occultations V4.0 (Herald, Dunham et al.), doi:10.26033/ehqs-jp27: satellites seen in occultations
    (date, separation in mas, position angle, size).

Refresh (maintainers, then commit the JSON):
    python -m pyoccult.binaries build <binary compilation zip or folder> <occultations zip or folder>
"""
from pyoccult.version import __version__
from pyoccult import urls as U
import csv, io, json, os, re, sys, zipfile

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "binaries.json")
_DATA = None


def _files(src, want):
    """{basename: bytes} of the files in a zip or folder whose names match the regex want."""
    out = {}
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                if re.search(want, os.path.basename(n)):
                    out[os.path.basename(n)] = z.read(n)
    else:
        for root, _, fs in os.walk(src):
            for f in fs:
                if re.search(want, f):
                    with open(os.path.join(root, f), "rb") as fh:
                        out[f] = fh.read()
    return out


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v <= -9.9 else v                               # -9.99, -9.999: no value


def read_compilation(src):
    """[dict] of the companions in Johnston's compilation (fixed-width table, layout from its PDS4 label)."""
    f = _files(src, r"^binarytable\.(tab|xml)$")
    label = f["binarytable.xml"].decode("utf-8", errors="replace")
    fields = {}
    for blk in re.findall(r"<Field_Character>(.*?)</Field_Character>", label, re.S):
        g = lambda t: re.search(rf"<{t}[^>]*>(.*?)</{t}>", blk, re.S).group(1).strip()
        fields[g("name")] = (int(g("field_location")) - 1, int(g("field_length")))
    rows = []
    for line in f["binarytable.tab"].decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        get = lambda k: line[fields[k][0]:fields[k][0] + fields[k][1]].strip()
        rows.append(dict(number=get("AST_NUMBER"), name=get("AST_NAME"), companion=get("COMPANION_DESIGNATION"),
                         d1_km=_num(get("PRIMARY_DIAMETER")), d2_km=_num(get("COMPANION_DIAMETER")),
                         a_km=_num(get("BINARY_SEMIMAJOR_AXIS")), period_d=_num(get("BINARY_ORBITAL_PERIOD"))))
    return rows


def read_occultations(src):
    """[dict] of satellites seen in occultations (Asteroid_<date>.psv of the occultations archive)."""
    f = _files(src, r"^Asteroid_\d.*\.psv$")
    if not f:
        raise ValueError(f"Asteroid_*.psv not found in {src}")
    text = f[sorted(f)[-1]].decode("utf-8", errors="replace")
    out = []
    for r in csv.DictReader(io.StringIO(text), delimiter="|"):
        for k in (1, 2, 3, 4):
            sep = _num(r.get(f"SAT_SEP_{k}"))
            if not sep:
                continue
            out.append(dict(number=(r.get("AST_DESIG") or "").strip(), name=(r.get("AST_NAME") or "").strip(),
                            date=(r.get("OBS_DATE") or "").strip(), satellite=(r.get(f"SAT_NAME_{k}") or "").strip(),
                            sep_mas=sep, pa=_num(r.get(f"SAT_PA_{k}")),
                            major_km=_num(r.get(f"SAT_MAJOR_{k}")), minor_km=_num(r.get(f"SAT_MINOR_{k}"))))
    return out


def build(compilation_src, occultations_src, out=FILE):
    """Write the compact JSON from both archives. Returns the number of systems."""
    systems = {}
    for c in read_compilation(compilation_src):
        if not c["number"].isdigit() or c["number"] == "0":
            continue                                               # unnumbered systems: no lookup by number
        s = systems.setdefault(c["number"], dict(name=c["name"], sats=[], occ=[]))
        s["sats"].append({k: c[k] for k in ("companion", "d1_km", "d2_km", "a_km", "period_d")})
    for o in read_occultations(occultations_src):
        if o["number"].isdigit():
            s = systems.setdefault(o["number"], dict(name=o["name"], sats=[], occ=[]))
            s["occ"].append({k: o[k] for k in ("date", "satellite", "sep_mas", "pa", "major_km", "minor_km")})
    data = dict(meta=dict(compilation="Johnston, W. R. (2019), Binary Minor Planets Compilation V3.0, NASA PDS, "
                          "doi:10.26033/bb68-pw96", occultations="Herald, Dunham et al., Small Bodies Occultations "
                          "V4.0, NASA PDS, doi:10.26033/ehqs-jp27", current=U.URL_JOHNSTON_ASTEROID_MOONS,
                          systems=len(systems)), systems=systems)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, out)
    return len(systems)


def load(path=FILE):
    global _DATA
    if _DATA is None:
        try:
            with open(path, encoding="utf-8") as f:
                _DATA = json.load(f)
        except (OSError, ValueError):
            _DATA = dict(meta={}, systems={})
    return _DATA


def lookup(number):
    """The system of an asteroid number ({name, sats, occ}), or None if no satellite is known."""
    return load()["systems"].get(str(number).strip())


def zone_km(number):
    """Half-width added to the primary's shadow for the satellite zone: the largest known distance plus that
    satellite's radius (km), or None (no satellite with a known distance)."""
    s = lookup(number)
    best = None
    for c in (s or {}).get("sats", []):
        if c.get("a_km"):
            w = c["a_km"] + (c.get("d2_km") or 0.0) / 2.0
            best = w if best is None else max(best, w)
    return best


def short(number):
    """'+moon' / '+2 moons' for the asteroid label, '+moon?' if only reported in occultations, '' if none known."""
    s = lookup(number)
    if not s:
        return ""
    if not s["sats"]:
        return "+moon?"                                           # only reported in occultations, not confirmed
    return "+moon" if len(s["sats"]) == 1 else f"+{len(s['sats'])} moons"


def text(number):
    """'Satellites: Linus D 28 km, 1099 km from the primary, period 3.60 d (Johnston 2019); seen in occultations:
    2021-10-02 at 32 mas' or '' if none known."""
    s = lookup(number)
    if not s:
        return ""
    parts = []
    for c in s["sats"]:
        name = re.sub(r"^(I|II|III|IV|V|VI)\s+", "", c["companion"]).strip()
        name = name if name and name != "-" else "unnamed satellite"
        bits = [f"D {c['d2_km']:g} km" if c.get("d2_km") else "",
                f"{c['a_km']:.0f} km from the primary" if c.get("a_km") else "",
                f"period {c['period_d']:.2f} d" if c.get("period_d") else ""]
        parts.append(f"{name} " + ", ".join(b for b in bits if b))
    out = ("Satellites (Johnston 2019): " + "; ".join(parts) if parts else
           "Satellite reported in occultations, not confirmed (not in Johnston's list)")
    if s["occ"]:
        seen = [f"{o['date']} at {o['sep_mas']:g} mas" + (f" ({o['satellite']})" if o["satellite"] else "")
                for o in sorted(s["occ"], key=lambda o: o["date"])]
        out += "; seen in occultations: " + ", ".join(seen)
    return out


def main():
    if len(sys.argv) < 4 or sys.argv[1] != "build":
        sys.exit(__doc__)
    n = build(sys.argv[2], sys.argv[3])
    print(f"{n} systems -> {FILE}")


if __name__ == "__main__":
    sys.exit(main())
