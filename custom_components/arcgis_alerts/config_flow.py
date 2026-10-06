"""Config and options flows for ArcGIS Alerts."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ArcGISClient, ArcGISConnectionError, ArcGISError
from .const import (
    CONF_FIELDS,
    CONF_LAYER_URL,
    CONF_LOCATION,
    CONF_PRESET,
    CONF_QUERY_MODE,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TITLE_FIELD,
    CONF_WHERE,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_WHERE,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
    PRESET_CUSTOM,
    PRESETS,
    QUERY_MODE_LOCAL,
    QUERY_MODES,
)
from .coordinator import ArcGISAlertsConfigEntry, entry_option

_LOGGER = logging.getLogger(__name__)

LOCATION_SELECTOR = LocationSelector(LocationSelectorConfig(radius=False))


def _unique_id(layer_url: str, where: str, location: dict[str, float]) -> str:
    """Build the unique ID from the layer, the filter, and the rounded location."""
    return (
        f"{layer_url.rstrip('/').lower()}|{where.strip()}|"
        f"{location[CONF_LATITUDE]:.4f},{location[CONF_LONGITUDE]:.4f}"
    )


def _location(value: dict[str, Any]) -> dict[str, float]:
    """Keep only the coordinates from a location selector value."""
    return {
        CONF_LATITUDE: float(value[CONF_LATITUDE]),
        CONF_LONGITUDE: float(value[CONF_LONGITUDE]),
    }


class ArcGISAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an ArcGIS layer as a binary sensor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._preset: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ArcGISAlertsConfigEntry) -> ArcGISAlertsOptionsFlow:
        """Return the options flow."""
        return ArcGISAlertsOptionsFlow()

    def _home(self) -> dict[str, float]:
        """Return Home Assistant's home location, the default for zone.home."""
        return {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a preset or a custom layer."""
        if user_input is not None:
            self._preset = user_input[CONF_PRESET]
            if self._preset == PRESET_CUSTOM:
                return await self.async_step_custom()
            return await self.async_step_preset()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRESET): SelectSelector(
                        SelectSelectorConfig(
                            options=[*PRESETS, PRESET_CUSTOM],
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_PRESET,
                        )
                    )
                }
            ),
        )

    async def async_step_preset(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Name a preset and give it a location."""
        assert self._preset is not None
        preset = PRESETS[self._preset]
        if user_input is not None:
            location = _location(user_input[CONF_LOCATION])
            await self.async_set_unique_id(
                _unique_id(preset["layer_url"], preset["where"], location)
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_PRESET: self._preset,
                    CONF_LAYER_URL: preset["layer_url"],
                    CONF_WHERE: preset["where"],
                    CONF_TITLE_FIELD: preset["title_field"],
                    CONF_FIELDS: list(preset["fields"]),
                    CONF_DEVICE_CLASS: preset["device_class"],
                    CONF_LOCATION: location,
                },
            )

        return self.async_show_form(
            step_id="preset",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=preset["name"]): str,
                    vol.Required(CONF_LOCATION, default=self._home()): LOCATION_SELECTOR,
                }
            ),
            description_placeholders={"layer_url": preset["layer_url"]},
        )

    async def async_step_custom(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure any ArcGIS polygon feature layer."""
        errors: dict[str, str] = {}
        if user_input is not None:
            layer_url = user_input[CONF_LAYER_URL].strip().rstrip("/")
            where = user_input[CONF_WHERE].strip() or DEFAULT_WHERE
            location = _location(user_input[CONF_LOCATION])
            client = ArcGISClient(async_get_clientsession(self.hass), layer_url)
            try:
                info = await client.async_get_layer_info()
            except ArcGISConnectionError:
                errors["base"] = "cannot_connect"
            except ArcGISError:
                errors["base"] = "invalid_layer"
            except Exception:
                _LOGGER.exception("Unexpected error reading %s", layer_url)
                errors["base"] = "unknown"
            else:
                capabilities = {
                    item.strip()
                    for item in str(info.get("capabilities", "")).split(",")
                }
                if info.get("geometryType") != "esriGeometryPolygon":
                    errors["base"] = "not_polygon"
                elif "Query" not in capabilities:
                    errors["base"] = "no_query"
            if not errors:
                await self.async_set_unique_id(_unique_id(layer_url, where, location))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_PRESET: PRESET_CUSTOM,
                        CONF_LAYER_URL: layer_url,
                        CONF_WHERE: where,
                        CONF_TITLE_FIELD: user_input.get(CONF_TITLE_FIELD, "").strip(),
                        CONF_FIELDS: [],
                        CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS),
                        CONF_LOCATION: location,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_LAYER_URL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                vol.Required(CONF_WHERE, default=DEFAULT_WHERE): str,
                vol.Optional(CONF_TITLE_FIELD, default=""): str,
                vol.Optional(CONF_DEVICE_CLASS): SelectSelector(
                    SelectSelectorConfig(
                        options=[cls.value for cls in BinarySensorDeviceClass],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_LOCATION, default=self._home()): LOCATION_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="custom",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )


class ArcGISAlertsOptionsFlow(OptionsFlowWithReload):
    """Change the poll interval, filter, location, and query mode."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_MINUTES: int(user_input[CONF_SCAN_INTERVAL_MINUTES]),
                    CONF_WHERE: user_input[CONF_WHERE].strip() or DEFAULT_WHERE,
                    CONF_LOCATION: _location(user_input[CONF_LOCATION]),
                    CONF_QUERY_MODE: user_input[CONF_QUERY_MODE],
                }
            )

        entry = self.config_entry
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_MINUTES,
                        default=entry_option(
                            entry, CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_MINUTES,
                            max=1440,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Required(
                        CONF_WHERE, default=entry_option(entry, CONF_WHERE, DEFAULT_WHERE)
                    ): str,
                    vol.Required(
                        CONF_LOCATION, default=entry_option(entry, CONF_LOCATION)
                    ): LOCATION_SELECTOR,
                    vol.Required(
                        CONF_QUERY_MODE,
                        default=entry_option(entry, CONF_QUERY_MODE, QUERY_MODE_LOCAL),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=QUERY_MODES,
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_QUERY_MODE,
                        )
                    ),
                }
            ),
        )
