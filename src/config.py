from __future__ import annotations

from datetime import datetime, timezone

APP_TITLE = "Diagnóstico de finca · Trebolares"
APP_ICON = "🌾"
APP_LAYOUT = "wide"

FARM_KML_PATH = "data/Trebolares.kml"

DEFAULT_LAT = -35.5598
DEFAULT_LON = -63.5924
DEFAULT_POINT_NAME = "Centroide Trebolares"

MIN_NASA_YEAR = 2001
MAX_COMPLETE_YEAR = max(MIN_NASA_YEAR, datetime.now(timezone.utc).year - 1)
DEFAULT_YEARS_BACK = 10
DEFAULT_START_YEAR = max(MIN_NASA_YEAR, MAX_COMPLETE_YEAR - DEFAULT_YEARS_BACK + 1)
DEFAULT_END_YEAR = MAX_COMPLETE_YEAR

REQUEST_TIMEOUT_SECONDS = 30
MAP_ZOOM = 14
MAP_CLICK_ZOOM = 13
LOCAL_RELIEF_OFFSET_DEGREES = 0.005
FROST_RISK_THRESHOLD_C = 3.0

MONTH_LABELS = [
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
]

NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
SOILGRIDS_BASE_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
OPENTOPOGRAPHY_BASE_URL = "https://api.opentopodata.org/v1/aster30m"
