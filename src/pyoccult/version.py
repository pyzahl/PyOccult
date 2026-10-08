"""version.py - the PyOccult version and project facts, kept in this one place. Every module and tool takes
them from here (GUI header and About box, --version of the tools, run summaries, CITATION.cff by hand).

Semantic versioning: MAJOR.MINOR.PATCH. Raise PATCH for fixes, MINOR for new features, MAJOR for changes that break
existing files or results (and update CITATION.cff's version with it). The code name changes at major milestones.
Every version increase gets its entry in CHANGELOG.md.
"""
__version__ = "0.13.0"
__codename__ = "New Horizons"      # JPL Horizons orbits; and New Horizons' target Arrokoth was first shaped by occultations
__author__ = "Percy Zahl (pyzahl)"
__copyright__ = "(C) 2026 Percy Zahl"
__license__ = "GPL-3.0-or-later"
__url__ = "https://github.com/pyzahl/PyOccult"
