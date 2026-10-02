#!.venv/bin/python3
"""pyoccult_setup.py - one-time setup of everything PyOccult needs locally. Safe to rerun: finished parts are skipped,
an interrupted Gaia build continues where it stopped.

    python pyoccult_setup.py              # kernels + local Gaia catalog + bright-star index
    python pyoccult_setup.py --no-gaia    # SPICE kernels only
    python pyoccult_setup.py --status     # show what is there

  1. SPICE kernels (naif0012.tls, de440.bsp, pck00010.tpc, earth_latest_high_prec.bpc; ~120 MB) into this folder.
  2. Local Gaia DR3 catalog, G <= gaia_local_gmax, into gaia_local_dir (pyoccult_config.py). Streams ESA's bulk files:
     753 GB download, ~11 GB kept for G <= 18, about 1.5-2 h at 1.4 Gbit/s. Needed by pyoccult.py (corridor mode).
  3. Bright-star index (G <= 15, ~1.3 GB) next to the catalog, for pyoccult_pick.py. ~30 s.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))                 # kernels live next to the scripts
import pyoccult_config as config
import pyoccult_gaia_local as gaia
from pyoccult_kernels import KERNELS, download_kernels


def show_status():
    for k in KERNELS:
        print(f"  {k:28s} {'ok' if os.path.isfile(k) else 'missing'}")
    d = getattr(config, "gaia_local_dir", None)
    if not d:
        print("  local Gaia catalog            gaia_local_dir not set in pyoccult_config.py")
        return
    st = gaia.status(d)
    print(f"  local Gaia catalog {d:12s}  {st['done']}/{st['total'] or '?'} files, {st['gb']:.1f} GB"
          + (" (complete)" if st["complete"] else ""))
    gmax = getattr(config, "pick_cam_limit", 15.0)
    have = os.path.isfile(os.path.join(d, f"bright_G{float(gmax):.1f}.v2.npy"))
    print(f"  bright-star index G <= {gmax:<5g}  {'ok' if have else 'missing'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-gaia", action="store_true", help="kernels only")
    ap.add_argument("--status", action="store_true", help="only show what is installed")
    ap.add_argument("--workers", type=int, default=6, help="parallel Gaia downloads")
    a = ap.parse_args()
    if a.status:
        show_status()
        sys.exit(0)
    print("1. SPICE kernels")
    if not download_kernels(config.earth_pck_max_age):
        sys.exit("kernel download failed")
    if not a.no_gaia:
        d, gmax = getattr(config, "gaia_local_dir", None) or "gaia_dr3_g18", getattr(config, "gaia_local_gmax", 18.0)
        print(f"2. local Gaia catalog G <= {gmax} in {d}")
        if gaia.status(d)["complete"]:
            print("   complete")
        else:
            gaia.build(d, gmax, a.workers)
        print("3. bright-star index")
        gaia.BrightIndex(d, getattr(config, "pick_cam_limit", 15.0))
        print("   ok")
    print()
    show_status()
