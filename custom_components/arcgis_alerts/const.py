"""Constants for the ArcGIS Alerts integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final, TypedDict

DOMAIN: Final = "arcgis_alerts"

CONF_PRESET: Final = "preset"
CONF_LAYER_URL: Final = "layer_url"
CONF_WHERE: Final = "where"
CONF_TITLE_FIELD: Final = "title_field"
CONF_FIELDS: Final = "fields"
CONF_LOCATION: Final = "location"
CONF_QUERY_MODE: Final = "query_mode"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

PRESET_CUSTOM: Final = "custom"

QUERY_MODE_LOCAL: Final = "local"
QUERY_MODE_SERVER: Final = "server"
QUERY_MODES: Final = [QUERY_MODE_LOCAL, QUERY_MODE_SERVER]

DEFAULT_WHERE: Final = "1=1"
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 5
MIN_SCAN_INTERVAL_MINUTES: Final = 1
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

# How many features the binary sensor exposes in its `features` attribute.
MAX_FEATURES_IN_ATTRIBUTES: Final = 10


class Preset(TypedDict):
    """A known layer, configured with a name and a location only."""

    name: str
    layer_url: str
    where: str
    title_field: str
    fields: list[str]
    device_class: str


# Adding a preset is a data-only change: add an entry here and a matching
# `selector.preset.options` label in strings.json and translations/en.json.
PRESETS: Final[dict[str, Preset]] = {
    "swbno_boil_water": {
        "name": "SWBNO boil water advisory",
        "layer_url": (
            "https://services1.arcgis.com/cYAR0YQ3Tr6M4FbT/arcgis/rest/services/"
            "SWB_Advisory_Area_VIEW/FeatureServer/0"
        ),
        "where": "Adv_Status IN ('active','testing')",
        "title_field": "Advisory_Title",
        "fields": [
            "Advisory_Title",
            "Advisory_Details",
            "Adv_Type",
            "Adv_Status",
            "Public_Begin_DT",
        ],
        "device_class": "problem",
    },
}
