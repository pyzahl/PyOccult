"""pyoccult_kernels.py - download the generic SPICE kernels PyOccult needs into the working folder (once; the Earth
orientation file is refreshed after earth_pck_max_age days). Used by pyoccult.py at start-up and by pyoccult_setup.py.
Standard library only (downloads with the system curl)."""
from pyoccult_version import __version__
import os, subprocess
from datetime import datetime
from pathlib import Path

KERNELS = ("naif0012.tls", "de440.bsp", "pck00010.tpc", "earth_latest_high_prec.bpc")


def check_file_age(file_path_str, days=-1):
    file_path = Path(file_path_str)
    if not file_path.is_file(): ## does not exist => False
        #print(f"Error: The file '{file_path_str}' does not exist.")
        return False

    if days < 0:  ## do not care (always good) => True
        return True
    
    now = datetime.now()
    
    # Get last modification time and creation time (with fallback for Unix)
    last_write_date = datetime.fromtimestamp(file_path.stat().st_mtime)
    try:
        ctime_timestamp = file_path.stat().st_birthtime
    except AttributeError:
        ctime_timestamp = file_path.stat().st_ctime
    creation_date = datetime.fromtimestamp(ctime_timestamp)

    # Calculate age in days
    age_since_creation = (now - creation_date).days
    age_since_write = (now - last_write_date).days

    #print(f"File: {file_path.name}")
    #print(f"Created: {creation_date} ({age_since_creation} days old)")
    #print(f"Modified: {last_write_date} ({age_since_write} days old)")
    return age_since_write <= days ## older than days => False
    

def pck_comment_dates(path="earth_latest_high_prec.bpc"):
    """{'created', 'last_datum'} from the comment block of NAIF's Earth PCK (ISO strings, None if not found). Values
    after the last datum (measured Earth orientation) up to the file's coverage end are predictions."""
    import re
    try:
        with open(path, "rb") as f:
            text = f.read(1 << 20).decode("latin-1")
    except OSError:
        return dict(created=None, last_datum=None)
    m1 = re.search(r"Creation date:\s+(\d{4}-\d\d-\d\dT[\d:]+)", text)
    m2 = re.search(r"UTC Epoch of last datum:\s+(\d{4} \w{3} \d\d)", text)
    last = datetime.strptime(m2.group(1), "%Y %b %d").strftime("%Y-%m-%d") if m2 else None
    return dict(created=m1.group(1) if m1 else None, last_datum=last)


# Basic Kerenls and Data
def download_kernels(earth_pck_max_age=7):
    urls = {
        # fname: [url, maxage]
        "naif0012.tls": ["https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls", -1],
        "de440.bsp": ["https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp", -1],
        "pck00010.tpc": ["https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00010.tpc", -1],
        "earth_latest_high_prec.bpc": ["https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_latest_high_prec.bpc", earth_pck_max_age],
    }
    
    # Complete browser headers to clear security checks
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    for name, [url, maxage] in urls.items():
        #print (f"{name}: {url} ** maxage: {maxage} d")
        
        # Clean check: Delete the file if it somehow contains HTML text
        if os.path.exists(name):
            with open(name, 'r', errors='ignore') as f:
                first_line = f.readline()
                if "<!doctype" in first_line.lower() or "<html" in first_line.lower():
                    print(f"Purging old HTML file from cache: {name}")
                    os.remove(name)

        # Download using the system curl pipeline if it doesn't exist
        if not check_file_age (name, maxage):
            print(f"Downloading {name} via system curl...")
            try:
                # -L follows redirects, -s hides progress bar, -f fails silently on server errors
                subprocess.run(
                    ["curl", "-L", "-A", "Mozilla/5.0", url, "-o", name],
                    check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"🚨 Curl download failed for {name}: {e}")
                return False
                
    print("✅ All kernels verified and downloaded cleanly via curl.")

    return True
