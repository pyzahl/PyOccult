"""gui.py - local web interface for PyOccult (NiceGUI): set up observing sites on a map, run the search or the
pick tool, follow the log, look at the results.

    pyoccult                            # opens http://127.0.0.1:8080 in the browser (same as: pyoccult gui)
    pyoccult --port 8090 --no-browser

It listens on this computer only (127.0.0.1), because it can start programs. Every run is its own process
(`python -m pyoccult run ...`, pyoccult/runner.py), so SPICE stays out of the GUI; settings chosen here apply to that run only, pyoccult_config.py is
not changed. Saving a site rewrites sites.py (comments in it are not kept).
"""
from pyoccult.version import __version__, __codename__, __author__, __copyright__, __license__, __url__
import argparse, asyncio, csv, json, math, os, pprint, runpy, sys, time

from pyoccult import home
from pyoccult.home import HOME as ROOT, PKG                      # ROOT: the data folder (sites.py, maps/, ...)
os.chdir(ROOT)
from nicegui import app, run, ui
from pyoccult import geo
from pyoccult import favorites
from pyoccult import cameras
from pyoccult import occultations
from pyoccult import binaries
from pyoccult import exports

PY = sys.executable
PYOCCULT = [PY, "-u", "-m", "pyoccult"]                             # how runs are started: PYOCCULT + [command, ...]
SITE_KEYS = [  # key, label, default, step  (optional site keys, see sites_example.py)
    ("aperture_cm", "Aperture (cm)", 25.0, 1), ("focal_mm", "Focal length (mm)", None, 10),
    ("mag_adjust", "MagAdjust (mag)", 0.0, 0.1),
    ("sensor_w_mm", "Sensor width (mm)", 5.6, 0.1), ("sensor_h_mm", "Sensor height (mm)", 3.2, 0.1),
    ("frames", "Detection frames", 4, 1),
    ("extinction", "Extinction (mag/airmass)", 0.0, 0.05), ("min_alt", "Min. star altitude (°)", 10.0, 1),
    ("max_sun_alt", "Max. Sun altitude (°)", -6.0, 1), ("reach_km", "Reach (km)", None, 5),
    ("min_dur_s", "Min. duration (s)", 0.4, 0.05), ("max_exp_s", "Longest exposure (s)", 0.64, 0.01),
]


# ---------------------------------------------------------------- sites.py
UI_STATE = os.path.join(ROOT, "gui_state.json")                  # last selected site and catalog (data folder)


def load_ui_state():
    try:
        with open(UI_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_ui_state(**kw):
    """Remember GUI choices across restarts (gui_state.json in the data folder, written atomically)."""
    import tempfile
    st = dict(load_ui_state(), **kw)
    try:
        fd, tmp = tempfile.mkstemp(dir=ROOT, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, UI_STATE)
    except OSError:
        pass


def load_sites():
    path = "sites.py" if os.path.isfile("sites.py") else os.path.join(PKG, "templates", "sites_example.py")
    g = runpy.run_path(path)
    return {k: dict(v) for k, v in g["sites"].items()}, g["default_site"]


def save_sites(sites, default_site):
    text = ("# Your observing sites (not in git). Layout and optional keys: see src/pyoccult/templates/sites_example.py.\n"
            "# pyoccult_config.py uses `default_site`, or the site named in the environment variable PYOCCULT_SITE.\n"
            f"# Written by the PyOccult GUI on {time.strftime('%Y-%m-%d %H:%M')}.\n\n"
            f"sites = {pprint.pformat(sites, sort_dicts=False, width=110)}\n\ndefault_site = {default_site!r}\n")
    tmp = "sites.py.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, "sites.py")


def mag_limit(s):
    """Faintest star searched, as in pyoccult_config.py (OWC criterion at the longest usable exposure)."""
    if s.get("mag_limit"):
        return float(s["mag_limit"])
    return round(5 * math.log10(s.get("aperture_cm", 25.0)) + 2.5 * math.log10(s.get("max_exp_s", 0.64)) + 8.5
                 + s.get("mag_adjust", 0.0), 1)


def fov(s):
    focal = s.get("focal_mm") or 100.0 * s.get("aperture_cm", 25.0)
    sw, sh = s.get("sensor_mm", (5.6, 3.2))
    return tuple(2 * math.degrees(math.atan(x / 2 / focal)) * 60 for x in (sw, sh))


# ---------------------------------------------------------------- processes
class Job:
    proc = None


async def run_process(args, log, env_site=None, on_done=None, env_catalog=None):
    if Job.proc and Job.proc.returncode is None:
        ui.notify("A run is already in progress", type="warning")
        return None
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYOCCULT_HOME=ROOT)
    env["PYTHONPATH"] = os.pathsep.join(x for x in (os.path.dirname(PKG), env.get("PYTHONPATH")) if x)   # not installed
    if env_site:
        env["PYOCCULT_SITE"] = env_site
    if env_catalog:
        env["PYOCCULT_CATALOG"] = env_catalog
    def push(text):
        # the page can be gone (browser closed, reloaded or stalled past the reconnect timeout): keep going without it,
        # and keep reading the output, or the process blocks on a full pipe and stays "in progress" forever
        try:
            log.push(text)
        except RuntimeError:
            pass

    push(f"$ {' '.join(args)}" + (f"   (site {env_site})" if env_site else "")
         + (f"   (catalog {env_catalog})" if env_catalog else ""))
    t0 = time.time()
    Job.proc = await asyncio.create_subprocess_exec(*args, cwd=ROOT, env=env, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.STDOUT)
    async for line in Job.proc.stdout:
        push(line.decode(errors="replace").rstrip())
    rc = await Job.proc.wait()
    push(f"--- finished with exit code {rc} in {time.time() - t0:.0f} s")
    if on_done:
        try:
            await on_done(rc)
        except RuntimeError:                                     # page gone: results stay in their files (picks/, ...)
            pass
    return rc


def stop_process(log):
    if Job.proc and Job.proc.returncode is None:
        Job.proc.terminate()
        log.push("--- stopped")


# ---------------------------------------------------------------- resizable list boxes
RESIZE_JS = """<script>
// list boxes the user can make taller or shorter (drag the bottom-right corner): .pyo-resize[data-key][data-vh].
// The height is saved only after a drag, as a share of the window height, and restored only when plausible
// (25-92 % of the window); otherwise the box keeps its default. (Saving on every size change stored the box's
// minimum height while the tab was being laid out, so after a restart only a sliver of the list was left.)
(function(){
 var LO=25,HI=92;
 function vh(px){return 100*px/window.innerHeight;}
 function setup(b){if(b.dataset.ready)return;b.dataset.ready='1';var k='pyoccult_box_'+b.dataset.key;
  try{var v=parseFloat(localStorage.getItem(k));if(v>=LO&&v<=HI)b.style.height=v+'vh';}catch(e){}
  var h0=null;
  b.addEventListener('pointerdown',function(){h0=b.offsetHeight;});
  document.addEventListener('pointerup',function(){if(h0===null)return;var h=b.offsetHeight;
   if(Math.abs(h-h0)>4&&h>0){var v=Math.min(HI,Math.max(LO,vh(h)));b.style.height=v+'vh';
    try{localStorage.setItem(k,v.toFixed(1));}catch(e){}}h0=null;});}
 function scan(){document.querySelectorAll('.pyo-resize[data-key]').forEach(setup);}
 scan();setInterval(scan,1000);
})();
</script>"""


def resizable_box(key, default_vh, scroll=False):
    """A box for a list (iframe or table) whose height the user drags at its bottom-right corner, remembered per box
    in the browser (RESIZE_JS). scroll=True: the content scrolls inside (tables); else it fills the box (iframes)."""
    return ui.element("div").classes("w-full pyo-resize").props(f'data-key="{key}"').style(
        f"height: {default_vh}vh; min-height: 160px; resize: vertical; padding-bottom: 14px; "
        f"overflow: {'auto' if scroll else 'hidden'}; border: 1px solid #ddd; background: #f1f5f9")


# ---------------------------------------------------------------- page
@ui.page("/")
def index():
    from pyoccult import config
    sites, default_site = load_sites()
    last = load_ui_state()                                       # the site and catalog chosen last time
    state = dict(name=last["site"] if last.get("site") in sites else default_site)
    ui.page_title("PyOccult")
    ui.add_body_html(RESIZE_JS)                                  # resizable list boxes (resizable_box)
    with ui.header().classes("items-center bg-slate-800"):
        ui.element("img").props('src=/pyoccult_logo.svg alt=""').classes("w-9 h-9")
        ui.label("PyOccult").classes("text-xl font-semibold")
        ui.label(f"v{__version__}").classes("text-xs text-slate-400 self-end mb-1").tooltip(
            f"PyOccult {__version__} \u201c{__codename__}\u201d")
        ui.label("asteroid occultation search").classes("text-slate-300")
        ui.space()
        ui.label("Site for all runs:").classes("text-slate-300")
        sel = ui.select(list(sites), value=state["name"]).props("dark dense options-dense standout").classes("w-48")
        from pyoccult import gaia_local
        found = gaia_local.find_catalogs(ROOT)
        complete = {d for d, g, ok, _ in found if ok}
        cat_gmax = {d: float(g) for d, g, ok, _ in found if g is not None}
        cats = {d: f"{d} (G \u2264 {g:g})" + ("" if ok else f", incomplete {gaia_local.status(os.path.join(ROOT, d))['done']}"
                                                         f"/{gaia_local.status(os.path.join(ROOT, d))['total']}")
                for d, g, ok, _ in found}
        ui.label("Catalog:").classes("text-slate-300")
        cat_sel = ui.select(cats, value=last["catalog"] if last.get("catalog") in complete else
                            config.gaia_local_dir if config.gaia_local_dir in complete else
                            (min(complete) if complete else (next(iter(cats)) if cats else None))
                            ).props("dark dense options-dense standout").classes("w-64").tooltip(
            "Local Gaia catalogs in the project folder. Install or add one with: pyoccult setup [--gmax 16]")
        ui.button("About", on_click=lambda: about.open()).props("flat dense color=white no-caps")
    with ui.dialog() as about, ui.card().classes("max-w-xl"):
        with ui.row().classes("items-center gap-4 no-wrap"):
            ui.element("img").props('src=/pyoccult_logo.svg alt=""').classes("w-20 h-20")
            with ui.column().classes("gap-0"):
                ui.label("PyOccult").classes("text-2xl font-semibold")
                ui.label(f"Version {__version__} \u201c{__codename__}\u201d").classes("text-slate-600")
                ui.label(f"by {__author__}").classes("text-sm text-slate-600")
        ui.label("Asteroid occultation prediction for your observing sites: picks the events at your site from all "
                 "numbered asteroids, computes them exactly (JPL Horizons orbits, NAIF SPICE, a local Gaia DR3 "
                 "catalog), and shows shadow paths, star-field previews and whole-Earth plots. A portable Python "
                 "successor to the Windows predictor Occult, validated against Occult Watcher Cloud. Every observed "
                 "event, positive or negative, adds to what we know about the sizes, shapes and orbits of the small "
                 "bodies of the Solar System.").classes("text-sm")
        ui.label("Credits").classes("font-semibold mt-2")
        ui.label("Stars: ESA Gaia DR3 (Gaia/DPAC) \u00b7 orbits and sizes: JPL Horizons and Small-Body Database \u00b7 "
                 "planets and Earth orientation: NAIF SPICE (SpiceyPy), DE440 \u00b7 coastlines: Natural Earth \u00b7 "
                 "maps: OpenStreetMap contributors, Leaflet \u00b7 interface: NiceGUI \u00b7 also Astropy, astroquery, "
                 "NumPy, SciPy, pandas \u00b7 reference predictions: Occult (D. Herald) and Occult Watcher Cloud "
                 "(H. Pavlov) \u00b7 the IOTA community \u00b7 developed with the help of Claude (Anthropic) via "
                 "Claude Code. Full references: README.md.").classes("text-xs text-slate-600")
        ui.label(f"Data folder: {home.describe()}. Change it with: pyoccult setup --home <folder>").classes(
            "text-xs text-slate-600 mt-2")
        ui.label(f"{__copyright__}. Free software under the GNU GPL v3 or later ({__license__}); no warranty. "
                 "Gaia data: CC BY-NC 3.0 IGO.").classes("text-xs text-slate-600 mt-2")
        with ui.row().classes("w-full items-center justify-between mt-2"):
            ui.link(__url__, __url__, new_tab=True).classes("text-sm")
            ui.button("Close", on_click=lambda: about.close()).props("flat")
    with ui.tabs().classes("w-full") as tabs:
        t_site, t_pick = ui.tab("Site"), ui.tab("Pick")
        t_bod = ui.tab("Planets & Moons")
        t_search, t_res = ui.tab("Search"), ui.tab("Results")
        t_fav = ui.tab("Favorites")
    log_card = None

    with ui.tab_panels(tabs, value=t_site).classes("w-full"):
        # ------------------------------------------------ site
        with ui.tab_panel(t_site):
            with ui.row().classes("w-full items-end gap-4"):
                site_title = ui.label().classes("text-lg font-semibold")
                new_name = ui.input("New site name").classes("w-48")
                ui.button("Add site", on_click=lambda: add_site()).props("outline")
                is_default = ui.checkbox("Default for command-line runs").tooltip(
                    "default_site in sites.py: used by `pyoccult search` / `pyoccult pick` run without the GUI")
                ui.button("Save sites.py", on_click=lambda: save()).props("color=primary")
                ui.button("Remove site", on_click=lambda: remove_site()).props("outline color=negative").tooltip(
                    "Remove the site selected at the top right from sites.py (asks first; saved at once)")
                unsaved = ui.label().classes("text-sm text-amber-700")
            with ui.row().classes("w-full no-wrap gap-4"):
                with ui.column().classes("w-1/2"):
                    m = ui.leaflet(center=(40.7, -74.0), zoom=9).classes("w-full").style("height: 430px")
                    marker = m.marker(latlng=(40.7, -74.0))
                    with ui.row().classes("w-full items-end"):
                        q = ui.input("Find a place").classes("grow")
                        ui.button("Search", on_click=lambda: find_place()).props("outline")
                        ui.button("My IP location", on_click=lambda: ip_loc()).props("outline")
                    hits = ui.column().classes("w-full gap-1")
                    occ = geo.mpc_observatories()               # MPC observatory codes (downloaded once into data/)
                    with ui.row().classes("w-full no-wrap gap-4"):
                        occ_sel = ui.select({i: f"{x['code']} {x['name']}" for i, x in enumerate(occ)},  # searchable:
                                                                                      # code and name only
                                            with_input=True, clearable=True,
                                            label="MPC observatory (type code or name)" if occ else
                                            "MPC observatory list: not available (offline?)").classes("w-1/2").props(
                            "dense options-dense" + ("" if occ else " disable")).tooltip(
                            f"{len(occ)} observatories with their official MPC codes (Minor Planet Center): sets position, "
                            "elevation, description and MPC code; the equipment stays as it is")
                        cam_sel = ui.select({i: cameras.label(c) for i, c in enumerate(cameras.SENSORS)},
                                            with_input=True, clearable=True,
                                            label="Sensor (cameras; type a name)").classes(
                            "grow").props("dense options-dense").tooltip(
                            "Sensors common in occultation work, each with the cameras built with it (MM / MC, M / C: "
                            "the mono and color versions of a camera, same sensor size). Picking one fills sensor "
                            "width and height, computed from pixel count and pixel size. Not listed, or a cropped "
                            "readout: enter width and height yourself")
                    ui.button("Add as new site", on_click=lambda: add_site()).props("outline").tooltip(
                        "Add the current map site (position, description, MPC code and the equipment in the form) as a "
                        "new site to the site selector at the top right, named as in 'New site name'; saved at once")
                    ui.label("Click the map to set the position; the elevation is looked up. "
                             "Use an exact position (GPS, map) for observing.").classes("text-xs text-slate-500")
                with ui.column().classes("w-1/2"):
                    with ui.row().classes("w-full no-wrap gap-4"):
                        desc = ui.input("Description").classes("grow")
                        mpc = ui.input("MPC code").classes("w-28").tooltip(
                            "The site's official Minor Planet Center observatory code, if it has one (kept in sites.py "
                            "as mpc_code; filled in when you pick an observatory below)")
                    with ui.row():
                        lat = ui.number("Latitude (°)", format="%.5f", step=0.0001)
                        lon = ui.number("Longitude (°, east +)", format="%.5f", step=0.0001)
                        ele = ui.number("Elevation (m)", format="%.0f", step=1)
                    fields = {}
                    with ui.grid(columns=3).classes("w-full"):
                        for key, label, default, step in SITE_KEYS:
                            fields[key] = ui.number(label, value=default, step=step)
                    derived = ui.label().classes("text-sm text-slate-600")

        # ------------------------------------------------ search
        with ui.tab_panel(t_search):
            site_note_s = ui.label().classes("text-sm text-slate-600")
            with ui.row().classes("items-end gap-4"):
                s_start = ui.input("Start (UTC date)", value=today_utc()).props("type=date")
                s_days = ui.number("Days", value=config.days, min=1, step=1)
                s_mag = ui.number("Star G limit", step=0.1, min=6, max=21).classes("w-28").tooltip(
                    "Faintest star (Gaia G) searched. Default: from the site's telescope (aperture, detection frames, longest "
                    "exposure, MagAdjust; Site tab), capped at the catalog's limit; change it for one run")
                s_drop = ui.number("Min. drop (mag)", value=getattr(config, "min_mag_drop", 0.1), step=0.05)
            s_use_file = ui.switch("Targets from the saved pick of this site (Pick tab)", value=True).tooltip(
                "Uses the newest saved pick of the selected site whose window covers the search window; "
                "without one, targets.py or the list in pyoccult_config.py")
            targets_warn_s = ui.label().classes("text-sm w-full")
            s_targets = ui.textarea("Targets (asteroid numbers, comma or space separated)",
                                    value=", ".join(config.targets)).classes("w-full")
            with ui.row():
                s_fresh = ui.checkbox("Start a fresh results list", value=True).tooltip(
                    "On: the Results tab shows only this search (a new series in the results database; older "
                    "results stay in pyoccult.db). Off: add this search's events to the current list")
                s_maps = ui.checkbox("KML maps", value=bool(config.write_maps))
                s_prev = ui.checkbox("Previews", value=bool(getattr(config, "write_previews", True)))
            with ui.row().classes("items-center"):
                ui.label("Astrometric corrections of the star:").classes("text-sm text-slate-600")
                s_plx = ui.checkbox("Stellar parallax", value=bool(getattr(config, "star_parallax", True))).tooltip(
                    "The star as seen from the Earth, not the Sun (Gaia parallax); up to several km on the path")
                s_defl = ui.checkbox("Light deflection (Sun, Jupiter, Saturn)",
                                     value=bool(getattr(config, "light_deflection", True))).tooltip(
                    "Gravitational light bending, star minus asteroid; up to ~6 km away from opposition. "
                    "Both off reproduce results before version 0.10.0")
                s_dbl = ui.checkbox("Online Gaia check of the event stars",
                                    value=bool(getattr(config, "gaia_online_check", True))).tooltip(
                    "After the search, one query to the Gaia archive: Gaia's double-star hints for each event star, "
                    "and close neighbours the local catalog leaves out. Close neighbours from the local catalog "
                    "are always checked. Skipped when offline")
            with ui.row():
                ui.button("Run search", on_click=lambda: run_search()).props("color=primary")
                ui.button("Stop", on_click=lambda: stop_process(log)).props("outline color=negative")

        # ------------------------------------------------ pick
        with ui.tab_panel(t_pick):
            site_note_p = ui.label().classes("text-sm text-slate-600")
            with ui.row().classes("items-end gap-4"):
                p_start = ui.input("Start (UTC date)", value=today_utc()).props("type=date").classes("w-36")
                p_days = ui.number("Days", value=config.days, min=1, step=1).classes("w-28")
                p_mag = ui.number("Star G limit", step=0.1, min=6, max=21).classes("w-28").tooltip(
                    "Faintest star (Gaia G) searched. Default: from the site's telescope (aperture, detection "
                    "frames, longest exposure, MagAdjust; Site tab), capped at the catalog's limit; change it for one "
                    "pick run. Above G 15 the first pick builds a deeper star index once (a few minutes)")
                p_hmax = ui.number("H below", value=getattr(config, "pick_hmax", 17.0), step=0.5).classes(
                    "w-28").tooltip(
                    "Only asteroids with H below this are screened (fainter H = smaller asteroids; more asteroids "
                    "take longer). An asteroid with a larger H is never found by the pick, but the search finds it if "
                    "you enter its number")
                p_all = ui.checkbox("All numbered (slow)")
                p_top = ui.number("Targets (top)", value=40, min=1, step=5).classes("w-28")
                p_workers = ui.number("Workers", value=max(1, (os.cpu_count() or 2) // 2), min=1, step=1).classes(
                    "w-28")
                p_sort = ui.select(["mag", "date", "margin", "drop"], value="mag", label="Rank by").classes("w-28")
                p_pre = ui.select(dict(PRE_FIXED), value="auto", label="Asteroids").classes("w-80").tooltip(
                    "auto: if a pre-screen fits (its region holds the site, its window this pick's window, its limits "
                    "are as loose), only its asteroids are screened: the same events, much faster; else all. "
                    "all: every asteroid, for any place and time (slower, no pre-screen needed). "
                    "Or one pre-screen by name (listed if it fits)")
            with ui.row().classes("items-center"):
                ui.button("Run pick", on_click=lambda: run_pick()).props("color=primary")
                ui.button("Stop", on_click=lambda: stop_process(log)).props("outline color=negative")
                pre_info = ui.label().classes("text-sm text-slate-600")
            with ui.expansion("Pre-screens: build once for a region and window, then picks there are fast",
                              icon="speed").classes("w-full border rounded"):
                ui.label("A pick screens every asteroid (~465k) against the stars for your site, which takes many "
                         "minutes for a few weeks. A pre-screen does the site-independent part once for a region and a "
                         "window (about 1-2 hours for 20 days, 4 workers) and keeps only the asteroids with possible "
                         "events there; every later pick of a site inside that region and window ('Asteroids: auto') "
                         "then screens only those. Build it for the next weeks, around all your sites; rebuild after a "
                         "few weeks (orbits are those of the build day). Uses the H limit and workers above; star limit "
                         "at least G 16; loose limits (reach 200 km, Sun below 0, star above 0). Stop saves; the same "
                         "build again resumes.").classes("text-sm text-slate-600")
                with ui.row().classes("items-end gap-4"):
                    ps_start = ui.input("Start (UTC date)", value=today_utc()).props("type=date").classes("w-36")
                    ps_days = ui.number("Days", value=30, min=1, step=1).classes("w-24")
                    ps_where = ui.select({"site": "around this site", "sites": "around all my sites",
                                          "global": "whole Earth"}, value="sites", label="Region").classes("w-48")
                    ps_km = ui.number("Box (km)", value=300, min=50, step=50).classes("w-28").tooltip(
                        "The region is a latitude/longitude box (a rectangle on the map, not a circle): this many km "
                        "north, south, east and west of the site (around all sites: of every site, at least this "
                        "far everywhere). Around one site the poleward edge is a little narrower in km (about 465 of "
                        "500 km at 41 N). Events count if the shadow path comes within the asteroid's radius + 200 km "
                        "(reach) of the box, so the effective region is the box widened by 200 km or more")
                    ui.button("Build pre-screen", on_click=lambda: run_prescreen()).props("outline")
                    ui.button("Delete selected", on_click=lambda: delete_prescreens()).props(
                        "flat dense color=negative")
                ps_cols = [dict(name=k, label=lbl, field=k, sortable=True, align="left") for k, lbl in
                           (("name", "Name"), ("window", "Window"), ("region", "Region"), ("sites", "Sites inside"),
                            ("limits", "Limits"), ("found", "Asteroids / events"), ("age", "Built"), ("fits", "This pick"))]
                ps_table = ui.table(columns=ps_cols, rows=[], row_key="path", selection="multiple").classes(
                    "w-full").props("flat dense")
            with ui.row().classes("w-full items-center gap-4"):
                p_saved = ui.select({}, label="Saved picks of this site").classes("w-96")
                ui.button("Use for search", on_click=lambda: use_saved()).props("outline").tooltip(
                    "Set the search window to this pick's window and go to the Search tab")
                ui.button("Reload", on_click=lambda: load_pick()).props("flat dense")
                ui.button("CSV", on_click=lambda: pick_csv()).props("outline dense").tooltip(
                    "Download the selected pick's events as a CSV table."
                    " Columns: csv_exports.py in the data folder (default: as the table shows them; any log column can be added)")
            pick_info = ui.label().classes("text-sm text-slate-600 w-full")
            targets_info = ui.label().classes("text-sm text-slate-600 w-full")
            cols = [dict(name=k, label=lbl, field=k, sortable=True, align="left") for k, lbl in
                    (("target", "Target"), ("number", "#"), ("name", "Asteroid"), ("H", "H"), ("utc", "UT"),
                     ("star_mag", "G"), ("drop", "Drop"), ("dur_s", "Dur (s)"), ("mag_margin", "Margin"),
                     ("miss_km", "Miss (km)"), ("star_alt", "Alt"))]
            with resizable_box("pick", 55, scroll=True):                # drag the corner to resize (remembered)
                p_table = ui.table(columns=cols, rows=[], row_key="key", pagination=0).classes("w-full").props(
                    "flat dense")

        # ------------------------------------------------ planets & moons (bodies.py)
        with ui.tab_panel(t_bod):
            site_note_b = ui.label().classes("text-sm text-slate-600")
            from pyoccult import bodies as bodies_mod
            b_checks, b_small = {}, {}
            with ui.row().classes("items-start gap-6"):
                for grp in bodies_mod.GROUPS:
                    major, small = bodies_mod.featured(grp)
                    with ui.column().classes("gap-0"):
                        ui.label(f"{grp.capitalize()} system").classes("font-semibold")
                        for t in major:
                            kind = bodies_mod.kind(t)
                            b_checks[t] = ui.checkbox(f"{bodies_mod.name(t)}" + (f" ({kind})" if kind != "moon" else ""),
                                                      value=(grp == "jupiter")).props("dense")
                        if small:
                            b_small[grp] = ui.checkbox(f"smaller moons ({len(small)})", value=False).props(
                                "dense").tooltip(", ".join(bodies_mod.name(t) for t in small[:40])
                                                 + (" ..." if len(small) > 40 else "")
                                                 + ": like small asteroids (faint, narrow paths, less certain orbits)")
                with ui.column().classes("gap-0"):
                    ui.label("Coming").classes("font-semibold text-slate-400")
                    ui.label("Earth's Moon").classes("text-sm text-slate-400")
            with ui.row().classes("items-end gap-4"):
                b_start = ui.input("Start (UTC date)", value=today_utc()).props("type=date").classes("w-36")
                b_days = ui.number("Days", value=30, min=1, step=1).classes("w-28")
                b_mag = ui.number("Star G limit", step=0.1, min=6, max=21).classes("w-28").tooltip(
                    "Faintest star (Gaia G) searched. Default: from the site's telescope (aperture, detection frames, longest "
                    "exposure, MagAdjust; Site tab), capped at the catalog's limit; change it for one run. "
                    "Planets have no drop limit (any star they cover disappears); moons also need the min. drop")
                b_drop = ui.number("Moons: min. drop (mag)", value=getattr(config, "min_mag_drop", 0.1),
                                   step=0.05).classes("w-36").tooltip(
                    "Moons are bright (about mag 5 for Jupiter's): only bright stars give a measurable drop")
                b_fresh = ui.checkbox("Start a fresh list", value=True)
            with ui.row():
                ui.button("Run", on_click=lambda: run_bodies()).props("color=primary")
                ui.button("Stop", on_click=lambda: stop_process(log)).props("outline color=negative")
                ui.button("Rebuild report", on_click=lambda: build_bodies_report()).props("outline")
                ui.link("Open in a new tab", "/out/bodies_report.html", new_tab=True).classes("self-center")
                ui.button("CSV", on_click=lambda: bodies_csv()).props("outline dense").tooltip(
                    "Download these events with disappearance and reappearance times."
                    " Columns: csv_exports.py in the data folder (default: as the table shows them; any log column can be added)")
            ui.label("Disappearance (D) and reappearance (R) at your site, from JPL Horizons positions (a small "
                     "kernel per window). The results are their own list (bodies_log.csv), apart from the asteroid "
                     "search.").classes("text-xs text-slate-500")
            with resizable_box("bodies", 60):
                b_frame = ui.element("iframe").style("width: 100%; height: 100%; border: 0; display: block")

        # ------------------------------------------------ results
        with ui.tab_panel(t_res):
            with ui.row().classes("items-center"):
                ui.button("Rebuild report", on_click=lambda: build_report()).props("outline")
                if getattr(config, "owc_lookup", False):                  # experimental, set in pyoccult_config.py
                    ui.button("Check OWC", on_click=lambda: owc_check("results")).props("outline dense").tooltip(
                        "Look these events up in OccultWatcher Cloud: prediction feeds (tags) and signed-up stations, "
                        "shown under the asteroid with a link to the OWC event page (one request per second)")
                ui.link("Open in a new tab", "/out/hits_report.html", new_tab=True)
                ui.button("CSV", on_click=lambda: hits_csv()).props("outline dense").tooltip(
                    "Download the search results as a CSV table."
                    " Columns: csv_exports.py in the data folder (default: as the table shows them; any log column can be added)")
                ui.checkbox("KStars/Stellarium: set its location to the event site", value=KSTARS_OPT["set_location"],
                            on_change=lambda e: KSTARS_OPT.update(set_location=bool(e.value))).tooltip(
                    "The report's KStars buttons (Linux, KStars running) and Stellarium buttons (Remote Control "
                    "plugin). Off: they keep their location (KStars tells you if that is far from the site).")
            with resizable_box("results", 75):                            # drag the corner to resize (remembered)
                frame = ui.element("iframe").style("width: 100%; height: 100%; border: 0; display: block")

        # ------------------------------------------------ favorites
        with ui.tab_panel(t_fav):
            with ui.row().classes("w-full items-center gap-4"):
                fav_info = ui.label().classes("text-sm text-slate-600")
                ui.button("Reload", on_click=lambda: load_favs()).props("flat dense")
                ui.link("Open in a new tab", "/fav/favorites.html", new_tab=True)
                ui.button("CSV", on_click=lambda: fav_csv()).props("outline dense").tooltip(
                    "Download all favorites as a table, named favorites_<today>.csv."
                    " Columns: csv_exports.py in the data folder (default: as the table shows them; any log column can be added). "
                    "The full table with all columns stays in favorites/favorites.csv")
                if getattr(config, "owc_lookup", False):                  # experimental, set in pyoccult_config.py
                    ui.button("Check OWC", on_click=lambda: owc_check("favorites")).props("outline dense").tooltip(
                        "Look the favorites up in OccultWatcher Cloud: prediction feeds (tags) and signed-up stations "
                        "(one request per second)")
            ui.label("Add events with the ☆ button in the Results report (opened from this GUI). Each favorite keeps "
                     "its own copy of map and preview, so later searches do not change it. Click a row for its preview, "
                     "map and note below; check rows for the actions above the table. Drag the table's bottom-right corner to make "
                     "it taller or shorter (remembered).").classes("text-xs text-slate-500")
            with resizable_box("favorites", 60):                          # drag the corner to resize (remembered)
                f_frame = ui.element("iframe").style("width: 100%; height: 100%; border: 0; display: block")
            with ui.column().classes("w-full gap-3") as f_detail:
                with ui.row().classes("w-full no-wrap gap-4 items-stretch"):
                    f_img = ui.element("img").style("width: 420px; max-width: 45vw; border: 1px solid #ddd")
                    f_map = ui.leaflet(center=(40.7, -74.0), zoom=9).classes("grow").style(   # as tall as the
                        "height: calc(min(420px, 45vw) * 634 / 560); border: 1px solid #ddd")    # preview (560x634)
                    f_nomap = ui.label("No map copied for this event.").classes("text-sm text-slate-500")
                with ui.row().classes("gap-3 items-center text-xs text-slate-600") as f_legend:   # no ui.html:
                    for sym, col, txt in (("━", "#15803d", "centre line"), ("━", "#dc2626", "shadow limits"),  # its
                                          ("┄", "#7c3aed", "1σ"), ("╌", "#d97706", "3σ")):         # signature differs
                        with ui.row().classes("gap-1 items-center"):                              # across versions
                            ui.label(sym).style(f"color: {col}; font-weight: 700")
                            ui.label(txt)
                    ui.label("marker: site")
                with ui.column().classes("w-full"):
                    f_title = ui.label().classes("text-lg font-semibold")
                    f_info = ui.grid(columns=4).classes("w-full gap-x-6 gap-y-1")   # OWC-style event summary
                    with ui.row().classes("w-full no-wrap gap-6 items-start"):
                        f_err = ui.element("img").style("width: 300px; flex: none").tooltip(
                            "Uncertainty ellipses (sky plane, 1 sigma) at one scale: the target's (JPL Horizons), the star's "
                            "(Gaia DR3, carried to the event date; '!' = a typical star of that G when Gaia's errors "
                            "are not at hand) and the combined one, which moves the path. Only the part across the "
                            "target's motion (dashed) shifts the path on the ground")
                        with ui.column().classes("grow"):
                            f_occ = ui.label().classes("text-sm text-slate-600").tooltip(
                                "Earlier occultations of this asteroid in NASA's archive of observed occultations (PDS "
                                "Small Bodies Node; Herald, Dunham et al.; doi:10.26033/ehqs-jp27). Reference only: the "
                                "prediction uses the size above. Event quality: astrometry only < limits on size < "
                                "reliable size < better than shape models")
                            f_added = ui.label().classes("text-xs text-slate-500")
                            with ui.row().classes("items-end gap-4"):
                                f_status = ui.select(list(favorites.STATUSES), label="Status").classes("w-40")
                                f_kml = ui.link("KML (ground track)", "#")
                                f_globe = ui.link("Globe (Occult-style plot)", "#", new_tab=True)
                            f_note = ui.textarea("Note").classes("w-full")
                            with ui.row():
                                ui.button("Save", on_click=lambda: save_fav()).props("color=primary")
                                ui.button("Remove from favorites", on_click=lambda: remove_fav()).props(
                                    "outline color=negative")
            f_detail.set_visibility(False)

    with ui.card().classes("w-full") as log_card:
        with ui.row().classes("w-full items-center"):
            ui.label("Log").classes("font-semibold")
            ui.button("Clear", on_click=lambda: log.clear()).props("flat dense")
        log = ui.log(max_lines=3000).classes("w-full h-64 text-xs")

    # ------------------------------------------------ site logic
    def show_site(name):
        s = sites[name]
        state["name"] = name
        lat.value, lon.value, ele.value, desc.value = s["lat"], s["lon"], s["ele"], s.get("name", name)
        mpc.value = str(s.get("mpc_code", "") or "")
        for key, _, default, _ in SITE_KEYS:
            if key == "sensor_w_mm":
                fields[key].value = s.get("sensor_mm", (5.6, 3.2))[0]
            elif key == "sensor_h_mm":
                fields[key].value = s.get("sensor_mm", (5.6, 3.2))[1]
            else:
                fields[key].value = s.get(key, default)
        is_default.value = name == state.get("default", default_site)
        site_title.text = f"Site: {name}"
        try:
            load_pick()
            prescreen_options()
        except NameError:                         # first call, while the page is built: load_pick() runs later
            pass
        for note in (site_note_s, site_note_p, site_note_b):
            note.text = (f"Runs use site {name} ({s['lat']:.4f}, {s['lon']:.4f}, {s.get('aperture_cm', 25):g} cm); "
                         f"change it at the top right.")
        marker.move(s["lat"], s["lon"])
        m.set_center((s["lat"], s["lon"]))
        update_derived()

    def collect():
        s = dict(lat=float(lat.value or 0), lon=float(lon.value or 0), ele=float(ele.value or 0),
                 name=desc.value or state["name"])
        if (mpc.value or "").strip():
            s["mpc_code"] = mpc.value.strip()
        for key, _, default, _ in SITE_KEYS:
            v = fields[key].value
            if key in ("sensor_w_mm", "sensor_h_mm") or v is None or v == "":
                continue
            s[key] = int(v) if key == "frames" else float(v)
        s["sensor_mm"] = (float(fields["sensor_w_mm"].value or 5.6), float(fields["sensor_h_mm"].value or 3.2))
        return s

    def pick_mag_default(s):
        """Faintest star for the pick: the site's telescope limit, capped at the selected catalog's G limit."""
        return round(min(mag_limit(s), cat_gmax.get(cat_sel.value, 18.0)), 1)

    def update_derived(*_):
        s = collect()
        unsaved.text = "" if saved_site(state["name"]) == effective(s, state["name"]) else "unsaved changes"
        w, h = fov(s)
        p_mag.value = s_mag.value = b_mag.value = pick_mag_default(s)
        derived.text = (f"Stars searched to G {mag_limit(s):.1f} · camera field {w:.1f}′ × {h:.1f}′ "
                        f"(focal {s.get('focal_mm') or 100 * s.get('aperture_cm', 25):.0f} mm)")

    for el in [lat, lon, ele, mpc, *fields.values()]:
        el.on_value_change(update_derived)

    def set_position(la, lo, el=None):
        lat.value, lon.value = round(la, 5), round(lo, 5)
        if el is not None:
            ele.value = round(el)
        marker.move(la, lo)

    async def on_click(e):
        ll = e.args.get("latlng", {})
        set_position(ll["lat"], ll["lng"])
        el = await run.io_bound(geo.elevation, ll["lat"], ll["lng"])
        if el is not None:
            ele.value = round(el)

    m.on("map-click", on_click)

    async def pick_occult(e):
        if e.value is None:
            return
        x = occ[e.value]
        set_position(x["lat"], x["lon"], x["ele"] if x["ele_ok"] else None)
        m.set_center((x["lat"], x["lon"]))
        desc.value, mpc.value = x["name"], x["code"]
        auto = f"{x['code']} {x['name'].split(',')[0].strip()}"
        if not (new_name.value or "").strip() or new_name.value == state.get("auto_name"):   # keep a name you typed
            new_name.value = auto
        state["auto_name"] = auto
        if not x["ele_ok"]:                                       # old low-precision entry: look the height up
            el = await run.io_bound(geo.elevation, x["lat"], x["lon"])
            if el is not None:
                ele.value = round(el)
        ui.notify(f"MPC {x['code']} {x['name']}: shown on the map and in the form. 'Add as new site' adds it to the "
                  f"site selector; 'Save sites.py' would instead move {state['name']} there.",
                  multi_line=True, timeout=9000)

    occ_sel.on_value_change(pick_occult)

    def pick_camera(e):
        if e.value is None:
            return
        c = cameras.SENSORS[e.value]
        w, h = cameras.sensor_mm(c)
        fields["sensor_w_mm"].value, fields["sensor_h_mm"].value = w, h       # updates the camera field line too
        ui.notify(f"{c[0]} ({c[4]}): sensor {w:.2f} × {h:.2f} mm; 'Save sites.py' keeps it for this site",
                  timeout=6000)

    cam_sel.on_value_change(pick_camera)

    async def find_place():
        hits.clear()
        res = await run.io_bound(geo.places, q.value or "")
        with hits:
            if not res:
                ui.label("No place found (or offline)").classes("text-sm text-slate-500")
            for la, lo, el, label in res:
                ui.button(f"{label}: {la:.4f}, {lo:.4f}, {el or 0:.0f} m",
                          on_click=lambda la=la, lo=lo, el=el: (set_position(la, lo, el), m.set_center((la, lo)),
                                                                hits.clear())).props("flat dense no-caps align=left")

    async def ip_loc():
        r = await run.io_bound(geo.ip_location)
        if r is None:
            ui.notify("IP lookup failed", type="warning")
            return
        set_position(r[0], r[1], r[2])
        m.set_center((r[0], r[1]))
        ui.notify(f"Approximate (from your IP address): {r[3]}")

    def add_site():
        """The position and settings in the form as a new site (name from 'New site name'), selected and saved."""
        name = (new_name.value or "").strip()
        if not name or name in sites:
            ui.notify("Enter a new, unused site name (field 'New site name' at the top)", type="warning")
            return
        sites[name] = collect()                                   # keeps the description from the form
        sel.options = list(sites)
        sel.update()
        sel.value = name                                          # shows it (show_site) and makes it the run site
        new_name.value, state["auto_name"] = "", None
        save_sites(sites, state.get("default", default_site))
        unsaved.text = ""
        ui.notify(f"Site {name} added and saved in sites.py; it is now selected for all runs (top right)",
                  type="positive")

    def effective(s, name):
        """A site with every optional key filled in with its default, for comparing form and file."""
        e = {k: (tuple(v) if isinstance(v, list) else v) for k, v in s.items()}
        e.setdefault("name", name)
        e.setdefault("sensor_mm", (5.6, 3.2))
        for key, _, default, _ in SITE_KEYS:
            if key not in ("sensor_w_mm", "sensor_h_mm") and default is not None:
                e.setdefault(key, default)
        return e

    def saved_site(name):
        """The site as it is in sites.py now (what a run will use), with defaults filled in; None if not there."""
        try:
            s = load_sites()[0].get(name)
        except Exception:
            return None
        return effective(s, name) if s else None

    def ensure_saved():
        """Runs read sites.py: save the selected site first if it was edited or is new."""
        s = collect()
        if not os.path.isfile("sites.py") or saved_site(state["name"]) != effective(s, state["name"]):
            save()
            ui.notify(f"Saved the changes to site {state['name']} for this run", type="info")

    async def remove_site():
        name = state["name"]
        if len(sites) < 2:
            ui.notify("This is the only site: add another one before removing it", type="warning")
            return
        with ui.dialog() as dlg, ui.card():
            ui.label(f"Remove site {name} ({sites[name].get('name', name)}) from sites.py?")
            with ui.row():
                ui.button("Remove", on_click=lambda: dlg.submit(True)).props("color=negative")
                ui.button("Cancel", on_click=lambda: dlg.submit(False)).props("flat")
        if not await dlg:
            return
        del sites[name]
        default = state.get("default", default_site)
        note = ""
        if default == name or default not in sites:
            default = state["default"] = next(iter(sites))
            note = f"; {default} is now the default for command-line runs"
        save_sites(sites, default)
        sel.options = list(sites)
        sel.update()
        sel.value = default                                       # shows it (show_site)
        unsaved.text = ""
        ui.notify(f"Site {name} removed from sites.py{note}", type="positive")

    def save():
        sites[state["name"]] = collect()
        if is_default.value:
            state["default"] = state["name"]
        save_sites(sites, state.get("default", default_site))
        ui.notify(f"sites.py saved (default site: {state.get('default', default_site)})", type="positive")
        unsaved.text = ""

    sel.on_value_change(lambda e: (show_site(e.value), save_ui_state(site=e.value, catalog=cat_sel.value))
                        if e.value in sites else None)
    def catalog_limit(*_):                                        # the catalog's limit caps the star limits
        p_mag.value = s_mag.value = b_mag.value = pick_mag_default(collect())
    cat_sel.on_value_change(catalog_limit)
    cat_sel.on_value_change(lambda e: save_ui_state(catalog=e.value, site=state["name"]) if e.value else None)
    show_site(state["name"])

    # ------------------------------------------------ runs
    async def owc_check(which):
        """Look the Results or Favorites events up in OccultWatcher Cloud (owc.py), then show the tables again."""
        from pyoccult import owc
        if which == "results":
            path = os.path.join(ROOT, config.hits_output_cvs_file)
            with open(path, newline="") if os.path.isfile(path) else open(os.devnull) as f:
                recs = list(csv.DictReader(f))
        else:
            recs = [f["record"] for f in favorites.load()]
        uniq = {owc.key(r): r for r in recs if str(r.get("target_id", "")).strip().isdigit() and r.get("best_utc")}
        if not uniq:
            ui.notify("No events to check", type="warning")
            return
        ui.notify(f"Checking {len(uniq)} event(s) in OccultWatcher Cloud (about {2 * len(uniq)} s) ...")
        found, n, errors = await run.io_bound(owc.check, list(uniq.values()), ROOT)
        for err in errors:                                      # which request failed and how (log and terminal)
            log.push(f"OWC check failed: {err}")
            print(f"OWC check failed: {err}")
        ui.notify(f"OccultWatcher Cloud: {found} of {n} event(s) found"
                  + (f"; {len(errors)} failed: details in the Log at the bottom of the page" if errors else ""),
                  type="warning" if errors else "positive", multi_line=True)
        if which == "results":
            await build_report()
        else:
            load_favs(fav_cur["key"])

    async def run_bodies():
        """Planets & Moons tab: search the ticked bodies (their own results list), then show their report."""
        if not catalog_ok():
            return
        targets = [t for t, c in b_checks.items() if c.value]
        for grp, c in b_small.items():                  # a system's smaller moons, all at once
            if c.value:
                targets += bodies_mod.featured(grp)[1]
        if not targets:
            ui.notify("Tick at least one body", type="warning")
            return
        ensure_saved()
        over = dict(ct=f"{b_start.value}T00:00:00", days=int(b_days.value), targets=targets, targets_source="list",
                    results_list="bodies", hits_output_cvs_file="bodies_log.csv",
                    results_new_series=bool(b_fresh.value),
                    min_mag_drop=float(b_drop.value), gaia_online_check=False,
                    **({"MAG_MIN": float(b_mag.value)} if b_mag.value else {}))

        async def done(rc):
            if rc == 0:
                await build_bodies_report()
        await run_process(PYOCCULT + ["run", "search", json.dumps(over)], log,
                          env_site=state["name"], on_done=done, env_catalog=cat_sel.value)

    async def build_bodies_report(rc=0):
        if not os.path.isfile(os.path.join(ROOT, "bodies_log.csv")) and not os.path.isfile(
                os.path.join(ROOT, "bodies_log.runs.jsonl")):
            ui.notify("No planet or moon search yet", type="warning")
            return
        await run_process(PYOCCULT + ["report", "bodies_log.csv", "-o", "bodies_report.html", "--layout", "bodies"],
                          log)
        b_frame.props(f"src=/out/bodies_report.html?t={int(time.time())}")

    def bodies_csv():
        path = os.path.join(ROOT, "bodies_log.csv")
        if not os.path.isfile(path):
            ui.notify("No planet or moon events yet", type="warning")
            return
        download_csv("bodies", exports.results_rows(results_db(), "bodies"), f"bodies_{today_utc()}.csv")

    async def build_report(rc=0):
        await run_process(PYOCCULT + ["report", config.hits_output_cvs_file], log)
        frame.props(f"src=/out/hits_report.html?t={int(time.time())}")

    def catalog_ok():
        """Runs need a complete catalog: tell the user how to get one otherwise."""
        if cat_sel.value in complete:
            return True
        ui.notify(("No complete Gaia catalog yet" if not cat_sel.value else f"Catalog {cat_sel.value} is incomplete")
                  + ": run  pyoccult setup  (it resumes), then restart the GUI", type="warning", timeout=10000)
        return False

    async def run_search():
        if not catalog_ok():
            return
        ensure_saved()
        over = dict(ct=f"{s_start.value}T00:00:00", days=int(s_days.value), min_mag_drop=float(s_drop.value),
                    **({"MAG_MIN": float(s_mag.value)} if s_mag.value else {}),
                    write_maps=bool(s_maps.value), write_previews=bool(s_prev.value),
                    star_parallax=bool(s_plx.value), light_deflection=bool(s_defl.value),
                    gaia_online_check=bool(s_dbl.value))
        if not s_use_file.value:
            over["targets"] = [t for t in s_targets.value.replace(",", " ").split() if t]
        over["results_new_series"] = bool(s_fresh.value)          # db.py: a fresh results list = a new series

        async def done(rc):
            if rc == 0:
                await build_report()
                tabs.value = t_res
        await run_process(PYOCCULT + ["run", "search", json.dumps(over)], log,
                          env_site=state["name"], on_done=done, env_catalog=cat_sel.value)

    def saved_info(*_):
        """Search tab: which saved pick the search will use for the selected site and window."""
        if not s_use_file.value:
            targets_warn_s.text = "The search uses the list below."
            targets_warn_s.classes(replace="text-sm w-full text-slate-600")
            return
        try:
            s = sites.get(state["name"], {})
            p = picks.best_for(state["name"], s_start.value, float(s_days.value or 1), picks_dir, s.get("lat"), s.get("lon"))
        except ValueError:
            p = None
        if p:
            targets_warn_s.text = f"The search uses the {picks.describe(p)}."
            targets_warn_s.classes(replace="text-sm w-full text-slate-600")
        else:
            targets_warn_s.text = (f"No saved pick of site {state['name']} covers this window: the search uses "
                                   f"targets.py or the config list. Run a pick for it (Pick tab) for better targets.")
            targets_warn_s.classes(replace="text-sm w-full text-amber-700")

    def show_saved(*_):
        """Pick tab: show the events of the selected saved pick."""
        p = next((p for p in saved_list if p["py"] == p_saved.value), None)
        rows = []
        if p is None:
            pick_info.text = f"No saved pick for site {state['name']} yet: run a pick."
            targets_info.text = ""
        else:
            if os.path.isfile(p["csv"]):
                with open(p["csv"]) as f:
                    rows = list(csv.DictReader(f))
            rows = [dict(exports.pick_shown(r, p["targets"]), key=f"{r.get('number')}_{r.get('utc')}") for r in rows]
            pick_info.text = f"{picks.describe(p)}: {len(rows)} events ({p['csv']})"
            targets_info.text = ("Targets: " + ", ".join(p["targets"][:60]) + (" ..." if len(p["targets"]) > 60 else ""))
        p_table.rows = rows
        return len(rows)

    def load_pick(select=None):
        """Fill the list of saved picks of the selected site (newest window first) and show one. Returns #events."""
        saved_list[:] = picks.list_for(state["name"], picks_dir)
        p_saved.options = {p["py"]: f"{p['start']} + {p['days']:g} d · {len(p['targets'])} targets · picked "
                                    f"{p['picked'][:16].replace('T', ' ') or '?'}" for p in saved_list}
        p_saved.update()
        keep = select or p_saved.value
        p_saved.value = keep if keep in p_saved.options else (saved_list[0]["py"] if saved_list else None)
        n = show_saved()
        saved_info()
        return n

    def prescreen_options(*_):
        """Pick tab: the Asteroids choices (auto, all, the pre-screens that fit this site and window), the line saying
        what the pick will screen, and the pre-screens table."""
        from pyoccult import prescreen as PS
        opts, rows, fit = dict(PRE_FIXED), [], []
        s = sites.get(state["name"], {})
        try:
            t0 = _day_et(p_start.value)
            t1 = t0 + float(p_days.value or 1) * 86400
            want = dict(cam_limit=float(p_mag.value or 0), hmax=None if p_all.value else float(p_hmax.value or 17),
                        hmax_all=bool(p_all.value))
            files = PS.list_files(os.path.join(ROOT, PS.DIR))
        except Exception:
            files, t0, t1, want = [], 0, 0, {}
        for path, m in files:
            m = dict(m, et0=_day_et(m["start"]), et1=_day_et(m["start"]) + m["days"] * 86400)
            bad = PS.check(m, t0, t1, s.get("lat", 0), s.get("lon", 0), want) if s.get("lat") is not None else ["no site"]
            if not bad:
                opts[path] = "pre-screen " + PS.describe(path, m)
                fit.append((m.get("built", ""), path, m))
            reg = m.get("region")
            inside = [n for n, v in sites.items() if "lat" in v and PS.contains(m, v["lat"], v["lon"])]
            try:
                n_ev, n_ast = PS.counts(path)
            except Exception:
                n_ev = n_ast = "?"
            age = PS.age_days(m)
            rows.append(dict(path=path, name=m.get("name", "?"),
                             window=f"{m['start']} + {m['days']:g} d",
                             region="whole Earth" if not reg else f"lat {reg['lat_min']:.0f}..{reg['lat_max']:.0f}, "
                                                                  f"lon {reg['lon_min']:.0f}..{reg['lon_max']:.0f}",
                             sites=", ".join(inside) or "-",
                             limits=f"G <= {m['cam_limit']:g}, H < {m.get('hmax')}, reach {m['reach_km']:g} km",
                             found=f"{n_ast} / {n_ev}",
                             age="?" if age is None else (f"{age:.0f} d ago" + (" (old: rebuild)" if age > 30 else "")),
                             fits="fits" if not bad else "; ".join(bad)))
        p_pre.options = opts
        if p_pre.value not in opts:
            p_pre.value = "auto"
        p_pre.update()
        ps_table.rows = rows
        ps_table.update()
        if p_pre.value == "all":
            pre_info.text = "Screens all asteroids (any place and time; slower)."
        elif fit:
            _, path, m = max(fit, key=lambda x: x[0]) if p_pre.value == "auto" else \
                next(x for x in fit if x[1] == p_pre.value)
            pre_info.text = f"Screens only the asteroids of pre-screen {os.path.basename(path)} (fast)."
        else:
            pre_info.text = ("No pre-screen fits this site and window: screens all asteroids (slower). "
                             "Build one below for fast picks.")

    async def delete_prescreens():
        sel = [r["path"] for r in ps_table.selected]
        if not sel:
            ui.notify("Select pre-screens in the table first", type="warning")
            return
        for p in sel:
            try:
                os.remove(p)
            except OSError as e:
                ui.notify(f"{os.path.basename(p)}: {e}", type="negative")
        ps_table.selected = []
        prescreen_options()
        ui.notify(f"{len(sel)} pre-screen(s) deleted", type="positive")

    def pick_csv():
        p = next((p for p in saved_list if p["py"] == p_saved.value), None)
        if p is None or not os.path.isfile(p["csv"]):
            ui.notify("No saved pick with a CSV selected", type="warning")
            return
        download_csv("pick", exports.pick_rows(p["csv"], p["targets"]), os.path.basename(p["csv"]))

    def fav_csv():
        items = favorites.load(os.path.join(ROOT, favorites.DIR))
        if not items:
            ui.notify("No favorites yet", type="warning")
            return
        download_csv("favorites", exports.favorite_rows(items), f"favorites_{today_utc()}.csv")

    def hits_csv():
        path = os.path.join(ROOT, config.hits_output_cvs_file)
        if not os.path.isfile(path):
            ui.notify("No search results yet (run a search)", type="warning")
            return
        from pyoccult import report
        run = report.read_last_run(path) or {}             # name it like the picks: site, window
        site, start = (run.get("site") or {}).get("name"), str(run.get("window_start") or "")[:10]
        name = (f"hits_{picks._safe(site)}__{start}_{float(run['window_days']):g}d.csv"
                if site and start and run.get("window_days") else os.path.basename(path))
        download_csv("results", exports.results_rows(results_db(), "main"), name)

    def results_db():
        return os.path.join(ROOT, getattr(config, "results_db", "pyoccult.db"))

    def download_csv(kind, rows, name):
        """A CSV download with the columns of csv_exports.py (data folder) for this table."""
        folder = os.path.join(config.cache_path, "pyoccult_exports")
        os.makedirs(folder, exist_ok=True)
        try:
            exports.write(kind, rows, os.path.join(folder, name), home=ROOT)
        except Exception as ex:                                  # a broken csv_exports.py: say so
            ui.notify(f"CSV export failed ({type(ex).__name__}: {ex}); check csv_exports.py in the data folder",
                      type="negative", timeout=10000)
            return
        ui.download(os.path.join(folder, name), name)

    def use_saved():
        p = next((p for p in saved_list if p["py"] == p_saved.value), None)
        if p is None:
            ui.notify("No saved pick selected", type="warning")
            return
        s_start.value, s_days.value, s_use_file.value = p["start"], p["days"], True
        tabs.value = t_search

    from pyoccult import picks
    picks_dir = getattr(config, "picks_dir", "picks")
    saved_list = []
    p_saved.on_value_change(show_saved)
    for el in (s_start, s_days, s_use_file):
        el.on_value_change(saved_info)
    load_pick()
    for el in (p_start, p_days, p_mag, p_hmax, p_all, p_pre):
        el.on_value_change(prescreen_options)
    prescreen_options()

    fav_cur = {"key": None}

    def load_favs(select=None):
        """Rebuild the favorites page (report table) and show it; keep or set the selected favorite."""
        favorites.write_page()
        items = favorites.load()
        fav_info.text = f"{len(items)} favorite event{'s' if len(items) != 1 else ''}"
        f_frame.props(f"src=/fav/favorites.html?t={time.time():.0f}")
        if select:
            fav_cur["key"] = select
        if fav_cur["key"] not in {e["key"] for e in items}:
            fav_cur["key"] = None
        show_fav()

    def current_fav():
        return next((e for e in favorites.load() if e["key"] == fav_cur["key"]), None)

    def show_fav(*_):
        e = current_fav()
        f_detail.set_visibility(e is not None)
        if e is None:
            return
        r, site, files = e["record"], e.get("site") or {}, e.get("files") or {}
        f_title.text = favorites.title_text(e)
        f_info.clear()
        with f_info:
            for group, rows in favorites.event_info(e):
                with ui.column().classes("gap-0"):
                    ui.label(group).classes("text-lg font-semibold")
                    for k, v in rows:
                        with ui.row().classes("gap-1 no-wrap text-base"):
                            ui.label(f"{k}:").classes("text-slate-500 whitespace-nowrap")
                            ui.label(str(v)).classes("text-slate-800 min-w-0 break-words")
        err = favorites.error_svg(e)
        f_err.set_visibility(err is not None)
        if err:
            import base64
            f_err.props(f'src="data:image/svg+xml;base64,{base64.b64encode(err.encode()).decode()}" alt="Error ellipses"')
        f_occ.text = occultations.text(e["record"].get("target_id", ""))
        f_added.text = f"added {e.get('added', '')[:16].replace('T', ' ')} UT"
        f_status.value, f_note.value = e.get("status", "planned"), e.get("note", "")
        f_img.set_visibility("svg" in files)
        if "svg" in files:
            f_img.props(f'src=/fav/{files["svg"]}?t={int(time.time())} alt="Event preview"')
        f_globe.set_visibility("globe" in files)
        if "globe" in files:
            f_globe.props(f'href=/fav/{files["globe"]}')
        f_kml.set_visibility("kml" in files)
        if "kml" in files:
            f_kml.props(f'href=/fav/{files["kml"]} download')
        draw_fav_map(e)

    fav_layers = []

    def draw_fav_map(e):
        """The favorite's own KML copy on the map: shadow path lines and the site, zoomed to the nearest path part."""
        from pyoccult import report
        for layer in fav_layers:
            f_map.remove_layer(layer)
        fav_layers.clear()
        kml = (e.get("files") or {}).get("kml")
        try:
            data = report.kml_to_data(os.path.join(favorites.DIR, kml)) if kml else None
        except Exception:
            data = None
        for el in (f_map, f_legend):
            el.set_visibility(data is not None)
        f_nomap.set_visibility(data is None)
        if data is None:
            return
        for ln in data["lines"]:
            if len(ln["pts"]) > 1:
                opts = {"color": ln["color"], "weight": ln["width"]}
                if ln.get("dash"):
                    opts["dashArray"] = ln["dash"]
                fav_layers.append(f_map.generic_layer(name="polyline", args=[ln["pts"], opts]))
        site = e.get("site") or {}
        centre = next((ln["pts"] for ln in data["lines"] if ln["name"].startswith("Centre")), [])
        if site.get("lat") is not None and site.get("lon") is not None:
            obs = [site["lat"], site["lon"]]
            fav_layers.append(f_map.marker(latlng=tuple(obs)))
            near = min(centre, key=lambda p: (p[0] - obs[0]) ** 2 + ((p[1] - obs[1]) * math.cos(math.radians(obs[0]))) ** 2,
                       default=obs)
            bounds = [obs, near]
        else:
            bounds = centre or [[0, 0]]

        def fit():
            f_map.run_map_method("invalidateSize")
            f_map.run_map_method("fitBounds", bounds, {"padding": [50, 50], "maxZoom": 11})
        ui.timer(0.3, fit, once=True)

    def save_fav():
        e = current_fav()
        if e:
            ok, msg = favorites.update(e["key"], status=f_status.value, note=f_note.value or "")
            ui.notify(msg, type="positive" if ok else "warning")
            load_favs(select=e["key"])

    async def remove_fav():
        e = current_fav()
        if not e:
            return
        with ui.dialog() as dlg, ui.card():
            ui.label(f"Remove {f_title.text} and its copied map and preview?")
            with ui.row():
                ui.button("Remove", on_click=lambda: dlg.submit(True)).props("color=negative")
                ui.button("Cancel", on_click=lambda: dlg.submit(False)).props("flat")
        if await dlg:
            ok, msg = favorites.remove(e["key"])
            ui.notify(msg, type="positive" if ok else "warning")
            fav_cur["key"] = None
            load_favs()

    def on_fav_select(e):
        fav_cur["key"] = e.args if isinstance(e.args, str) else (e.args or [None])[0]
        show_fav()

    def on_fav_changed(_):                        # the page changed favorites (mass actions): refresh the panel
        if fav_cur["key"] not in set(favorites.keys()):
            fav_cur["key"] = None
        show_fav()

    ui.on("fav_select", on_fav_select)
    ui.on("fav_changed", on_fav_changed)
    tabs.on_value_change(lambda e: load_favs() if e.value == t_fav or e.value == "Favorites" else None)
    load_favs()

    async def run_pick():
        if not catalog_ok():
            return
        ensure_saved()
        args = PYOCCULT + ["pick", "--start", p_start.value, "--days", str(int(p_days.value)),
                "--top", str(int(p_top.value)), "--workers", str(int(p_workers.value)), "--sort", p_sort.value]
        args += ["--all"] if p_all.value else ["--hmax", str(p_hmax.value)]
        if p_mag.value:
            args += ["--cam-limit", f"{float(p_mag.value):g}"]
        if p_pre.value != "all":
            args += ["--prescreen", p_pre.value]                # "auto" or a file

        async def done(rc):
            if rc == 0:
                n = load_pick(select=picks.paths(state["name"], p_start.value, int(p_days.value), picks_dir)[0])
                s_use_file.value = True
                ui.notify(f"{n} events; saved for site {state['name']}", type="positive")
        await run_process(args, log, env_site=state["name"], on_done=done, env_catalog=cat_sel.value)


    async def run_prescreen():
        if not catalog_ok():
            return
        ensure_saved()
        where = {"site": ["--around-site", f"{float(ps_km.value or 300):g}"],
                 "sites": ["--around-sites", f"{float(ps_km.value or 300):g}"], "global": ["--global"]}[ps_where.value]
        args = PYOCCULT + ["prescreen", "build", "--start", ps_start.value, "--days", str(int(ps_days.value)),
                           *where, "--workers", str(int(p_workers.value))]
        args += ["--all"] if p_all.value else ["--hmax", str(p_hmax.value)]
        args += ["--cam-limit", f"{max(16.0, float(p_mag.value or 0)):g}"]

        async def done(rc):
            prescreen_options()
            if rc == 0:
                ui.notify("Pre-screen built; picks inside its region and window use it ('Asteroids: auto')",
                          type="positive")
            else:
                ui.notify("Pre-screen not finished; the same build again resumes it", type="warning")
        await run_process(args, log, env_site=state["name"], on_done=done, env_catalog=cat_sel.value)


def local_double_check(config):
    """check(record) for favorites.backfill_doubles: the close/double-star check (doubles.py) from the local catalog,
    without SPICE; None for every record when no complete catalog is there."""
    from pyoccult import doubles, gaia_local
    state = {}

    def check(r):
        if "local" not in state:
            try:
                state["local"] = gaia_local.LocalGaia(config.gaia_local_dir)
            except Exception:                                    # no or incomplete catalog: try again next start
                state["local"] = None
        local = state["local"]
        try:
            ra, dec, g, et = (float(r[k]) for k in ("star_ra", "star_dec", "mag", "best_et"))
            m_ast = float(r.get("m_ast")) if str(r.get("m_ast", "")) not in ("", "nan", "None") else None
        except (KeyError, TypeError, ValueError):
            return None
        if local is None:
            return None
        rad = float(getattr(config, "companion_radius_arcsec", 4.0))
        years = 2000.0 + et / (365.25 * 86400) - doubles.GAIA_EPOCH
        comps = doubles.companions(local.cone(ra, dec, (rad + 3.0) / 3600.0), int(str(r["star"]).split(".")[0]), ra, dec, g,
                                   years, rad)
        return doubles.fields(comps, g, m_ast, "local")
    return check


PRE_FIXED = {"auto": "auto: a fitting pre-screen, else all", "all": "all asteroids (any place and time; slower)"}


def _day_et(date):
    """Seconds of 00:00 UTC of a YYYY-MM-DD date on one scale (for comparing pick and pre-screen windows in the GUI,
    which has no SPICE; both start at 00:00 UTC, so the offset to ET cancels)."""
    import calendar
    return float(calendar.timegm(time.strptime(str(date)[:10], "%Y-%m-%d")))


KSTARS_OPT = dict(set_location=True)                   # Results tab option, read by /api/kstars/show


def today_utc():
    """Today's date (UTC), the default start of the Pick and Search windows in the GUI (pyoccult_config.ct is only the
    command-line default)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"PyOccult {__version__}")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    print(f"PyOccult {__version__}, data folder: {home.describe()}")
    from pyoccult import config
    os.makedirs(config.map_dir, exist_ok=True)
    app.add_static_files("/out/maps", os.path.join(ROOT, config.map_dir), max_cache_age=0)
    app.add_static_file(local_file=os.path.join(PKG, "pyoccult_logo.svg"), url_path="/pyoccult_logo.svg")
    from pyoccult import kstars                                      # report's KStars buttons (Linux; hidden elsewhere)
    from pyoccult import stellarium                                  # report's Stellarium buttons (any system)
    os.makedirs(os.path.join(ROOT, favorites.DIR), exist_ok=True)
    from pyoccult import sbdb                                        # full SBDB data (shape, rotation) for older favorites
    favorites.backfill_phys(lambda t: sbdb.get_full(t, config.cache_path))
    favorites.backfill_globes(config.map_dir)                   # globe plots of later searches for older favorites
    favorites.backfill_doubles(local_double_check(config))      # close/double stars for favorites added before
    favorites.backfill_timezones(geo.timezone)                  # site time zones (online, once per site)
    favorites.backfill_event()                                  # OWC-style event data for older favorites (Horizons)
    import threading                                            # error ellipses (Horizons, one Gaia job): may be slow
    threading.Thread(target=favorites.backfill_errors, daemon=True).start()
    favorites.write_csv()
    app.add_static_files("/fav", os.path.join(ROOT, favorites.DIR), max_cache_age=0)

    @app.get("/api/favorites/keys")
    def favorites_keys():
        return {"keys": favorites.keys()}

    @app.get("/api/favorites/update")
    def favorites_update(keys: str, status: str):
        ok, msg = favorites.update_many([k for k in keys.split(",") if k], status=status)
        favorites.write_page()
        return {"ok": ok, "msg": msg}

    @app.get("/api/favorites/remove")
    def favorites_remove(keys: str):
        ok, msg = favorites.remove_many([k for k in keys.split(",") if k])
        favorites.write_page()
        return {"ok": ok, "msg": msg}

    @app.get("/api/favorites/cleanup")
    def favorites_cleanup():
        ok, msg = favorites.cleanup()
        favorites.write_page()
        return {"ok": ok, "msg": msg}

    @app.get("/api/favorites/add")
    def favorites_add(tid: str, utc: str):
        from pyoccult import config as cfg, report, db
        con = db.connect(os.path.join(ROOT, getattr(cfg, "results_db", db.DEFAULT)))
        try:                                                # any results list (asteroids, planets & moons)
            rec, run = db.find_event_run(con, tid, utc[:16])
        finally:
            con.close()
        if rec is None:                                     # an older log without the database
            rec, run = favorites.find_record(cfg.hits_output_cvs_file, tid, utc), report.read_last_run(cfg.hits_output_cvs_file)
        if rec is None:
            return {"ok": False, "msg": f"event {tid} {utc[:19]} not found in the results"}
        from pyoccult import sbdb
        rec = {k: db._cell(v) for k, v in rec.items()}       # as a hit-log row ('' for none/NaN, as the export)
        ok, msg = favorites.add(rec, run, cfg.map_dir, sbdb=sbdb.get_full(tid, cfg.cache_path))
        if ok:
            favorites.backfill_timezones(geo.timezone)          # the new favorite's site time zone (once per site)
        favorites.write_page()
        return {"ok": ok, "msg": msg}

    @app.get("/api/kstars/status")
    def kstars_status():
        ok, msg = kstars.available()
        return {"ok": ok, "msg": msg}

    @app.get("/api/kstars/show")
    def kstars_show(ra: float, dec: float, utc: str, fov: float = 2.0, lat: float = None, lon: float = None,
                    ele: float = 0.0):
        ok, msg = kstars.show(ra, dec, utc, fov, lat, lon, ele, set_location=KSTARS_OPT["set_location"])
        return {"ok": ok, "msg": msg}

    @app.get("/api/stellarium/show")
    def stellarium_show(ra: float, dec: float, utc: str, fov: float = 2.0, lat: float = None, lon: float = None,
                        ele: float = 0.0):
        ok, msg = stellarium.show(ra, dec, utc, fov, lat, lon, ele, set_location=KSTARS_OPT["set_location"])
        return {"ok": ok, "msg": msg}
    app.add_static_file(local_file=os.path.join(ROOT, "hits_report.html"), url_path="/out/hits_report.html",
                        strict=False, max_cache_age=0)
    app.add_static_file(local_file=os.path.join(ROOT, "bodies_report.html"), url_path="/out/bodies_report.html",
                        strict=False, max_cache_age=0)
    ui.run(host="127.0.0.1", port=a.port, title="PyOccult", favicon=os.path.join(PKG, "pyoccult_logo.svg"),
           show=not a.no_browser, reload=False, reconnect_timeout=60)   # a busy browser keeps its page


if __name__ in {"__main__", "__mp_main__"}:
    main()
