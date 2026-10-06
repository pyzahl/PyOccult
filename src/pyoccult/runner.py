"""runner.py - run a search or pick with settings overridden for this run only.

    pyoccult run search '{"ct": "2026-10-01T00:00:00", "days": 8}'
    pyoccult run pick '{}' --days 8 --top 30

The JSON object sets attributes of the configuration (pyoccult.config) after it is loaded (pyoccult_config.py itself is
not changed); any further arguments go to the command. The site is chosen as usual (default_site, or the environment
variable PYOCCULT_SITE). Used by the GUI, which starts every run as its own process (SPICE is not thread-safe).
"""
from pyoccult.version import __version__
import json, sys


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    command, overrides = sys.argv[1], json.loads(sys.argv[2])
    from pyoccult import config
    from pyoccult.__main__ import run
    for k, v in overrides.items():
        setattr(config, k, v)
    if "targets" in overrides and "targets_source" not in overrides:
        config.targets_source = "list"                     # an explicit list wins over saved picks
    return run(command, sys.argv[3:])


if __name__ == "__main__":
    sys.exit(main())
