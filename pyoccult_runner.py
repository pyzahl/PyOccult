#!.venv/bin/python3
"""pyoccult_runner.py - run pyoccult.py or pyoccult_pick.py with settings overridden for this run only.

    python pyoccult_runner.py pyoccult.py '{"ct": "2026-10-01T00:00:00", "days": 8}'
    python pyoccult_runner.py pyoccult_pick.py '{}' --days 8 --top 30

The JSON object sets attributes of pyoccult_config after it is loaded (pyoccult_config.py itself is not changed); any
further arguments go to the script. The site is chosen as usual (default_site, or the environment variable
PYOCCULT_SITE). Used by pyoccult_gui.py, which starts every run as its own process (SPICE is not thread-safe).
"""
import json, os, runpy, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    script, overrides = sys.argv[1], json.loads(sys.argv[2])
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    import pyoccult_config as config
    for k, v in overrides.items():
        setattr(config, k, v)
    if "targets" in overrides and "targets_source" not in overrides:
        config.targets_source = "list"                     # an explicit list wins over saved picks
    sys.argv = [script] + sys.argv[3:]
    runpy.run_path(os.path.join(ROOT, script), run_name="__main__")
