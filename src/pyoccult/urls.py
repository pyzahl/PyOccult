"""urls.py - every download and web address PyOccult uses, in one place (change them here only).

Kept apart from pyoccult_config.py on purpose: that file reads sites.py and chooses the site when it is imported,
while some modules need these addresses before a sites.py exists (setup.py downloads the kernels and looks
up the site) or run without the configuration at all (report.py). This file has no side effects.

Not here: XML namespaces of the SVG and KML formats (fixed identifiers, not downloads) and the project's own GitHub
address (version.__url__).
"""

# --- NAIF SPICE kernels (kernels.py)
URL_NAIF_LSK = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls"                 # leap seconds
URL_NAIF_DE440 = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp"         # planets
URL_NAIF_PCK = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00010.tpc"                # body constants
URL_NAIF_EARTH_PCK = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_latest_high_prec.bpc"  # Earth orientation

# --- Gaia DR3 bulk files at ESA (gaia_local.py build)
URL_GAIA_DR3_FILES = "https://cdn.gea.esac.esa.int/Gaia/gdr3/gaia_source/"     # + file name
URL_GAIA_DR3_LISTING = "https://gaia.eu-1.cdn77-storage.com/"                   # S3-style listing of the same files
GAIA_DR3_LISTING_PREFIX = "Gaia/gdr3/gaia_source/"                               # its prefix parameter

# --- ready-made local catalogs on Zenodo (gaia_local.py, setup.py)
URL_ZENODO_CATALOG_RECORD = "https://zenodo.org/api/records/23113337"           # concept record: newest version

# --- JPL Solar System Dynamics
URL_JPL_HORIZONS_API = "https://ssd.jpl.nasa.gov/api/horizons.api"              # asteroid orbits as SPK (search.py)
URL_JPL_SBDB_API = "https://ssd-api.jpl.nasa.gov/sbdb.api"                      # one asteroid's data (search.py)
URL_JPL_SBDB_QUERY_API = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"          # all asteroids in bulk (pick tool)
URL_JPL_SBDB_PAGE = "https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr="   # web page, + asteroid number (report)

# --- Minor Planet Center (geo.py, GUI Site tab)
URL_MPC_OBSCODES = "https://minorplanetcenter.net/iau/lists/ObsCodes.html"      # observatory codes

# --- star pages (report)
URL_VIZIER_GAIA_DR3 = "https://vizier.cds.unistra.fr/viz-bin/VizieR-5?-source=I/355/gaiadr3&Source="  # + Gaia DR3 id

# --- places, elevation, time zones (geo.py)
URL_OPENMETEO_ELEVATION = "https://api.open-meteo.com/v1/elevation"
URL_OPENMETEO_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
URL_OPENMETEO_FORECAST = "https://api.open-meteo.com/v1/forecast"               # used for the time zone only
URL_IPINFO = "https://ipinfo.io/json"                                           # approximate position from the IP

# --- maps in the report and favorites pages
URL_OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"               # report --tile-url default
URL_LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
URL_LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"
URL_GOOGLE_MAPS_SEARCH = "https://www.google.com/maps/search/?api=1&query="    # + "lat,lon"
