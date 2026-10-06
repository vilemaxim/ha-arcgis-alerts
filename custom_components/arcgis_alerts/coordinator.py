"""Poll an ArcGIS feature layer for the features covering one location."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ArcGISClient, ArcGISError
from .const import (
    CONF_FIELDS,
    CONF_LAYER_URL,
    CONF_LOCATION,
    CONF_QUERY_MODE,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TITLE_FIELD,
    CONF_WHERE,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_WHERE,
    DOMAIN,
    QUERY_MODE_LOCAL,
    QUERY_MODE_SERVER,
)
from .geometry import feature_contains

_LOGGER = logging.getLogger(__name__)

type ArcGISAlertsConfigEntry = ConfigEntry[ArcGISAlertsCoordinator]


def entry_option(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Return an option, falling back to the value set when the entry was created."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


@dataclass
class AlertData:
    """The features covering the configured location, newest poll."""

    features: list[dict[str, Any]]
    title: str | None


def _format_attributes(
    attributes: dict[str, Any], date_fields: set[str], fields: list[str] | None
) -> dict[str, Any]:
    """Pick the configured fields and turn epoch-millisecond dates into ISO 8601 UTC."""
    names = fields if fields else list(attributes)
    formatted: dict[str, Any] = {}
    for name in names:
        value = attributes.get(name)
        if name in date_fields and isinstance(value, (int, float)):
            value = datetime.fromtimestamp(value / 1000, UTC).isoformat()
        formatted[name] = value
    return formatted


class ArcGISAlertsCoordinator(DataUpdateCoordinator[AlertData]):
    """Fetch the features of one layer that cover one location."""

    config_entry: ArcGISAlertsConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ArcGISAlertsConfigEntry) -> None:
        """Initialize the coordinator from a config entry."""
        minutes = entry_option(entry, CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=minutes),
        )
        self.layer_url: str = entry.data[CONF_LAYER_URL]
        self.client = ArcGISClient(async_get_clientsession(hass), self.layer_url)
        self.where: str = entry_option(entry, CONF_WHERE, DEFAULT_WHERE)
        location = entry_option(entry, CONF_LOCATION)
        self.latitude: float = location[CONF_LATITUDE]
        self.longitude: float = location[CONF_LONGITUDE]
        self.query_mode: str = entry_option(entry, CONF_QUERY_MODE, QUERY_MODE_LOCAL)
        self.title_field: str | None = entry.data.get(CONF_TITLE_FIELD) or None
        self.fields: list[str] | None = entry.data.get(CONF_FIELDS) or None

    def _out_fields(self) -> str:
        """Return the outFields parameter: the preset's fields, or every field."""
        if not self.fields:
            return "*"
        names = list(self.fields)
        if self.title_field and self.title_field not in names:
            names.append(self.title_field)
        return ",".join(names)

    async def _async_update_data(self) -> AlertData:
        """Query the layer. An error raises UpdateFailed, never an empty result."""
        point = (self.longitude, self.latitude)
        try:
            if self.query_mode == QUERY_MODE_SERVER:
                result = await self.client.async_query(
                    self.where, self._out_fields(), point=point
                )
                raw = result["features"]
            else:
                result = await self.client.async_query(
                    self.where, self._out_fields(), return_geometry=True
                )
                raw = [
                    feature
                    for feature in result["features"]
                    if feature_contains(feature.get("geometry"), *point)
                ]
        except ArcGISError as err:
            raise UpdateFailed(str(err)) from err

        date_fields = {
            field["name"]
            for field in result.get("fields") or []
            if field.get("type") == "esriFieldTypeDate"
        }
        features = [
            _format_attributes(feature.get("attributes") or {}, date_fields, self.fields)
            for feature in raw
        ]
        title = None
        if raw and self.title_field:
            title = (raw[0].get("attributes") or {}).get(self.title_field)
        return AlertData(features=features, title=title)
