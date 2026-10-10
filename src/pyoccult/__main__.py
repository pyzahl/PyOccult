"""pyoccult - start the web interface or one of the tools.

    pyoccult                         web interface (GUI); same as `pyoccult gui`, options e.g. --port 8081 --no-browser
    pyoccult setup                   one-time setup: your site, SPICE kernels, local Gaia catalog (resumable)
    pyoccult pick ...                event finder over all asteroids (targets for the search)
    pyoccult search                  the prediction for the targets (settings: pyoccult_config.py)
    pyoccult report hits_log.csv     results as an HTML or Markdown page
    pyoccult owc-check               compare with an OWC search result (owc_reference.txt)
    pyoccult gaia build|status|...   the local Gaia catalog
    pyoccult picks list|import       saved picks
    pyoccult prescreen build|list    pre-screened target lists per region and window (pick --prescreen)
    pyoccult favorites ...           favorites list (page, CSV)
    pyoccult kstars ...              point KStars (Linux)
    pyoccult stellarium ...          point Stellarium (Remote Control plugin)
    pyoccult run <command> '<json>'  a search or pick with settings overridden for this run (used by the GUI)

`pyoccult <command> --help` shows a command's options. Also: python -m pyoccult <command> ...
Every command runs in the data folder: a checkout's project folder, else the folder chosen at the first
`pyoccult setup` (default ~/PyOccult; change it with `pyoccult setup --home <folder>`), or PYOCCULT_HOME for one run.
`pyoccult setup --status` shows which one is used.
"""
import importlib, os, runpy, sys

COMMANDS = {"gui": "gui", "setup": "setup", "pick": "pick", "search": "search", "report": "report",
            "owc-check": "owc_check", "gaia": "gaia_local", "picks": "picks", "prescreen": "prescreen", "favorites": "favorites",
            "kstars": "kstars", "stellarium": "stellarium", "run": "runner"}
SCRIPTS = {"search"}            # not import-safe (sets up SPICE at import): executed as a script


def run(command, args):
    """Run one command with its arguments, in the data folder."""
    from pyoccult import home
    if command != "setup":                                    # setup chooses the data folder itself (first run, --home)
        os.makedirs(home.HOME, exist_ok=True)
        os.chdir(home.HOME)
    module = f"pyoccult.{COMMANDS[command]}"
    sys.argv = [f"pyoccult {command}"] + list(args)
    if command in SCRIPTS:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return 0
    # imported, then main(): functions handed to worker processes (pick, gaia build) keep their module name
    return importlib.import_module(module).main()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv and argv[0] == "--version":
        from pyoccult.version import __version__, __codename__
        print(f"PyOccult {__version__} “{__codename__}”")
        return 0
    if not argv or argv[0].startswith("-"):                  # no command (or GUI options only): the GUI
        argv = ["gui"] + argv
    if argv[0] not in COMMANDS:
        sys.exit(f"pyoccult: unknown command {argv[0]!r}; commands: {', '.join(COMMANDS)} (pyoccult --help)")
    rc = run(argv[0], argv[1:])
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main())
