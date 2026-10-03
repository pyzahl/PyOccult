#!.venv/bin/python3
"""pyoccult_gui.py - local web interface for PyOccult (NiceGUI): set up observing sites on a map, run the search or the
pick tool, follow the log, look at the results.

    python pyoccult_gui.py              # opens http://127.0.0.1:8080 in the browser
    python pyoccult_gui.py --port 8090 --no-browser

It listens on this computer only (127.0.0.1), because it can start programs. Every run is its own process
(pyoccult_runner.py), so SPICE stays out of the GUI; settings chosen here apply to that run only, pyoccult_config.py is
not changed. Saving a site rewrites sites.py (comments in it are not kept).
"""
import argparse, asyncio, csv, json, math, os, pprint, runpy, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from nicegui import app, run, ui
import pyoccult_geo as geo

PY = sys.executable
SITE_KEYS = [  # key, label, default, step  (optional site keys, see sites_example.py)
    ("aperture_cm", "Aperture (cm)", 25.0, 1), ("focal_mm", "Focal length (mm)", None, 10),
    ("sensor_w_mm", "Sensor width (mm)", 5.6, 0.1), ("sensor_h_mm", "Sensor height (mm)", 3.2, 0.1),
    ("frames", "Detection frames", 4, 1), ("mag_adjust", "MagAdjust (mag)", 0.0, 0.1),
    ("extinction", "Extinction (mag/airmass)", 0.0, 0.05), ("min_alt", "Min. star altitude (°)", 10.0, 1),
    ("max_sun_alt", "Max. Sun altitude (°)", -6.0, 1), ("reach_km", "Reach (km)", None, 5),
    ("min_dur_s", "Min. duration (s)", 0.4, 0.05), ("max_exp_s", "Longest exposure (s)", 0.64, 0.01),
]


# ---------------------------------------------------------------- sites.py
def load_sites():
    path = "sites.py" if os.path.isfile("sites.py") else "sites_example.py"
    g = runpy.run_path(path)
    return {k: dict(v) for k, v in g["sites"].items()}, g["default_site"]


def save_sites(sites, default_site):
    text = ("# Your observing sites (not in git). Layout and optional keys: see sites_example.py.\n"
            "# pyoccult_config.py uses `default_site`, or the site named in the environment variable PYOCCULT_SITE.\n"
            f"# Written by pyoccult_gui.py on {time.strftime('%Y-%m-%d %H:%M')}.\n\n"
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
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    if env_site:
        env["PYOCCULT_SITE"] = env_site
    if env_catalog:
        env["PYOCCULT_CATALOG"] = env_catalog
    log.push(f"$ {' '.join(args)}" + (f"   (site {env_site})" if env_site else "")
             + (f"   (catalog {env_catalog})" if env_catalog else ""))
    t0 = time.time()
    Job.proc = await asyncio.create_subprocess_exec(*args, cwd=ROOT, env=env, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.STDOUT)
    async for line in Job.proc.stdout:
        log.push(line.decode(errors="replace").rstrip())
    rc = await Job.proc.wait()
    log.push(f"--- finished with exit code {rc} in {time.time() - t0:.0f} s")
    if on_done:
        await on_done(rc)
    return rc


def stop_process(log):
    if Job.proc and Job.proc.returncode is None:
        Job.proc.terminate()
        log.push("--- stopped")


# ---------------------------------------------------------------- page
@ui.page("/")
def index():
    import pyoccult_config as config
    sites, default_site = load_sites()
    state = dict(name=default_site)
    ui.page_title("PyOccult")
    with ui.header().classes("items-center bg-slate-800"):
        ui.label("PyOccult").classes("text-xl font-semibold")
        ui.label("asteroid occultation search").classes("text-slate-300")
        ui.space()
        ui.label("Site for all runs:").classes("text-slate-300")
        sel = ui.select(list(sites), value=state["name"]).props("dark dense options-dense standout").classes("w-48")
        import pyoccult_gaia_local as gaia_local
        cats = {d: f"{d} (G \u2264 {g:g})" for d, g, ok, _ in gaia_local.find_catalogs(ROOT) if ok}
        ui.label("Catalog:").classes("text-slate-300")
        cat_sel = ui.select(cats, value=config.gaia_local_dir if config.gaia_local_dir in cats else
                            (next(iter(cats)) if cats else None)).props("dark dense options-dense standout").classes("w-56")
    with ui.tabs().classes("w-full") as tabs:
        t_site, t_search, t_pick, t_res = ui.tab("Site"), ui.tab("Search"), ui.tab("Pick"), ui.tab("Results")
    log_card = None

    with ui.tab_panels(tabs, value=t_site).classes("w-full"):
        # ------------------------------------------------ site
        with ui.tab_panel(t_site):
            with ui.row().classes("w-full items-end gap-4"):
                site_title = ui.label().classes("text-lg font-semibold")
                new_name = ui.input("New site name").classes("w-48")
                ui.button("Add site", on_click=lambda: add_site()).props("outline")
                is_default = ui.checkbox("Default for command-line runs").tooltip(
                    "default_site in sites.py: used by pyoccult.py / pyoccult_pick.py run without the GUI")
                ui.button("Save sites.py", on_click=lambda: save()).props("color=primary")
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
                    ui.label("Click the map to set the position; the elevation is looked up. "
                             "Use an exact position (GPS, map) for observing.").classes("text-xs text-slate-500")
                with ui.column().classes("w-1/2"):
                    desc = ui.input("Description").classes("w-full")
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
                s_start = ui.input("Start (UTC date)", value=str(config.ct)[:10]).props("type=date")
                s_days = ui.number("Days", value=config.days, min=1, step=1)
                s_drop = ui.number("Min. drop (mag)", value=getattr(config, "min_mag_drop", 0.1), step=0.05)
            s_use_file = ui.switch("Targets from targets.py (written by Pick)", value=os.path.isfile("targets.py"))
            targets_warn_s = ui.label().classes("text-sm text-amber-700 w-full")
            s_targets = ui.textarea("Targets (asteroid numbers, comma or space separated)",
                                    value=", ".join(config.targets)).classes("w-full")
            with ui.row():
                s_fresh = ui.checkbox("Start a fresh hits_log.csv", value=True)
                s_maps = ui.checkbox("KML maps", value=bool(config.write_maps))
                s_prev = ui.checkbox("Previews", value=bool(getattr(config, "write_previews", True)))
            with ui.row():
                ui.button("Run search", on_click=lambda: run_search()).props("color=primary")
                ui.button("Stop", on_click=lambda: stop_process(log)).props("outline color=negative")

        # ------------------------------------------------ pick
        with ui.tab_panel(t_pick):
            site_note_p = ui.label().classes("text-sm text-slate-600")
            with ui.row().classes("items-end gap-4"):
                p_start = ui.input("Start (UTC date)", value=str(config.ct)[:10]).props("type=date")
                p_days = ui.number("Days", value=config.days, min=1, step=1)
                p_hmax = ui.number("H below", value=getattr(config, "pick_hmax", 17.0), step=0.5)
                p_all = ui.checkbox("All numbered (slow)")
                p_top = ui.number("Targets (top)", value=40, min=1, step=5)
                p_workers = ui.number("Workers", value=max(1, (os.cpu_count() or 2) // 2), min=1, step=1)
                p_sort = ui.select(["mag", "date", "margin", "drop"], value="mag", label="Rank by")
            with ui.row():
                ui.button("Run pick", on_click=lambda: run_pick()).props("color=primary")
                ui.button("Stop", on_click=lambda: stop_process(log)).props("outline color=negative")
            with ui.row().classes("w-full items-center"):
                pick_info = ui.label().classes("text-sm text-slate-600")
                ui.button("Reload", on_click=lambda: load_pick()).props("flat dense")
            targets_info = ui.label().classes("text-sm text-slate-600 w-full")
            targets_warn_p = ui.label().classes("text-sm text-amber-700 w-full")
            cols = [dict(name=k, label=lbl, field=k, sortable=True, align="left") for k, lbl in
                    (("target", "In targets.py"), ("number", "#"), ("name", "Asteroid"), ("utc", "UT"),
                     ("star_mag", "G"), ("drop", "Drop"), ("dur_s", "Dur (s)"), ("mag_margin", "Margin"),
                     ("miss_km", "Miss (km)"), ("star_alt", "Alt"))]
            p_table = ui.table(columns=cols, rows=[], row_key="key", pagination=15).classes("w-full")

        # ------------------------------------------------ results
        with ui.tab_panel(t_res):
            with ui.row().classes("items-center"):
                ui.button("Rebuild report", on_click=lambda: build_report()).props("outline")
                ui.link("Open in a new tab", "/out/hits_report.html", new_tab=True)
            frame = ui.element("iframe").classes("w-full").style("height: 75vh; border: 1px solid #ddd")

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
            check_targets_site()
        except NameError:                         # first call, while the page is built: load_pick() checks it later
            pass
        for note in (site_note_s, site_note_p):
            note.text = (f"Runs use site {name} ({s['lat']:.4f}, {s['lon']:.4f}, {s.get('aperture_cm', 25):g} cm); "
                         f"change it at the top right.")
        marker.move(s["lat"], s["lon"])
        m.set_center((s["lat"], s["lon"]))
        update_derived()

    def collect():
        s = dict(lat=float(lat.value or 0), lon=float(lon.value or 0), ele=float(ele.value or 0),
                 name=desc.value or state["name"])
        for key, _, default, _ in SITE_KEYS:
            v = fields[key].value
            if key in ("sensor_w_mm", "sensor_h_mm") or v is None or v == "":
                continue
            s[key] = int(v) if key == "frames" else float(v)
        s["sensor_mm"] = (float(fields["sensor_w_mm"].value or 5.6), float(fields["sensor_h_mm"].value or 3.2))
        return s

    def update_derived(*_):
        s = collect()
        unsaved.text = "" if saved_site(state["name"]) == effective(s, state["name"]) else "unsaved changes"
        w, h = fov(s)
        derived.text = (f"Stars searched to G {mag_limit(s):.1f} · camera field {w:.1f}′ × {h:.1f}′ "
                        f"(focal {s.get('focal_mm') or 100 * s.get('aperture_cm', 25):.0f} mm)")

    for el in [lat, lon, ele, *fields.values()]:
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
        name = (new_name.value or "").strip()
        if not name or name in sites:
            ui.notify("Enter a new, unused site name", type="warning")
            return
        sites[name] = collect()
        sites[name]["name"] = name
        sel.options = list(sites)
        sel.value = name
        new_name.value = ""

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

    def save():
        sites[state["name"]] = collect()
        if is_default.value:
            state["default"] = state["name"]
        save_sites(sites, state.get("default", default_site))
        ui.notify(f"sites.py saved (default site: {state.get('default', default_site)})", type="positive")
        unsaved.text = ""

    sel.on_value_change(lambda e: show_site(e.value))
    show_site(state["name"])

    # ------------------------------------------------ runs
    async def build_report(rc=0):
        await run_process([PY, "-u", "pyoccult_report.py", config.hits_output_cvs_file], log)
        frame.props(f"src=/out/hits_report.html?t={int(time.time())}")

    async def run_search():
        ensure_saved()
        over = dict(ct=f"{s_start.value}T00:00:00", days=int(s_days.value), min_mag_drop=float(s_drop.value),
                    write_maps=bool(s_maps.value), write_previews=bool(s_prev.value))
        if not s_use_file.value:
            over["targets"] = [t for t in s_targets.value.replace(",", " ").split() if t]
        if s_fresh.value and os.path.isfile(config.hits_output_cvs_file):
            os.remove(config.hits_output_cvs_file)

        async def done(rc):
            if rc == 0:
                await build_report()
                tabs.value = t_res
        await run_process([PY, "-u", "pyoccult_runner.py", "pyoccult.py", json.dumps(over)], log,
                          env_site=state["name"], on_done=done, env_catalog=cat_sel.value)

    def targets_site():
        """The site targets.py was picked for (from its header line), or None."""
        import re
        try:
            with open("targets.py") as f:
                m = re.search(r"^# events .*?, site ([^,]+),", f.read(2000), re.M)
            return m[1].strip() if m else None
        except OSError:
            return None

    def check_targets_site():
        t = targets_site()
        msg = (f"Note: targets.py was picked for site {t}, runs use site {state['name']}. The search runs anyway; "
               f"targets picked for {state['name']} usually give more events here." if t and t != state["name"] else "")
        targets_warn_s.text = targets_warn_p.text = msg

    def load_pick():
        """Show the last pick run (pick_events.csv) and the current targets.py, e.g. after a restart. Returns #events."""
        stamp = lambda f: time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(f)))
        targets = []
        if os.path.isfile("targets.py"):
            try:
                targets = [str(t) for t in runpy.run_path("targets.py").get("targets", [])]
            except Exception as ex:
                targets_info.text = f"targets.py could not be read: {ex}"
            else:
                targets_info.text = (f"targets.py ({stamp('targets.py')}): {len(targets)} targets: "
                                     + ", ".join(targets[:60]) + (" ..." if len(targets) > 60 else ""))
        else:
            targets_info.text = "no targets.py yet: the search uses the list in pyoccult_config.py"
        rows = []
        if os.path.isfile("pick_events.csv"):
            with open("pick_events.csv") as f:
                rows = list(csv.DictReader(f))
            for r in rows:
                for k in ("star_mag", "drop", "dur_s", "mag_margin", "miss_km", "star_alt"):
                    r[k] = f"{float(r[k]):.2f}" if r.get(k) else ""
                r["key"] = f"{r.get('number')}_{r.get('utc')}"
                r["target"] = "\u2713" if str(r.get("number")) in targets else ""
            pick_info.text = f"Last pick run ({stamp('pick_events.csv')}): {len(rows)} events in pick_events.csv"
        else:
            pick_info.text = "No pick run yet (pick_events.csv)."
        p_table.rows = rows
        check_targets_site()
        return len(rows)

    load_pick()

    async def run_pick():
        ensure_saved()
        args = [PY, "-u", "pyoccult_pick.py", "--start", p_start.value, "--days", str(int(p_days.value)),
                "--top", str(int(p_top.value)), "--workers", str(int(p_workers.value)), "--sort", p_sort.value]
        args += ["--all"] if p_all.value else ["--hmax", str(p_hmax.value)]

        async def done(rc):
            if rc == 0:
                n = load_pick()
                s_use_file.value = True
                ui.notify(f"{n} events; targets.py written", type="positive")
        await run_process(args, log, env_site=state["name"], on_done=done, env_catalog=cat_sel.value)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    import pyoccult_config as config
    os.makedirs(config.map_dir, exist_ok=True)
    app.add_static_files("/out/maps", os.path.join(ROOT, config.map_dir), max_cache_age=0)
    app.add_static_file(local_file=os.path.join(ROOT, "hits_report.html"), url_path="/out/hits_report.html",
                        strict=False, max_cache_age=0)
    ui.run(host="127.0.0.1", port=a.port, title="PyOccult", favicon=os.path.join(ROOT, "pyoccult_logo.svg"),
           show=not a.no_browser, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
