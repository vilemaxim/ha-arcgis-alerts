"""Tests for the config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE_CLASS, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.arcgis_alerts.const import (
    CONF_FIELDS,
    CONF_LAYER_URL,
    CONF_LOCATION,
    CONF_PRESET,
    CONF_QUERY_MODE,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TITLE_FIELD,
    CONF_WHERE,
    DOMAIN,
    PRESETS,
)

from .conftest import LAYER_URL, QUERY_URL, TEST_LATITUDE, TEST_LONGITUDE, load_fixture

LOCATION = {CONF_LATITUDE: TEST_LATITUDE, CONF_LONGITUDE: TEST_LONGITUDE}
CUSTOM_URL = "https://example.com/arcgis/rest/services/Areas/FeatureServer/3"


async def _start(hass: HomeAssistant, preset: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PRESET: preset}
    )


async def test_preset_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The preset path asks only for a name and a location."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_in_effect.json"))
    result = await _start(hass, "swbno_boil_water")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "preset"
    assert set(result["data_schema"].schema) == {CONF_NAME, CONF_LOCATION}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Boil water", CONF_LOCATION: LOCATION}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Boil water"
    preset = PRESETS["swbno_boil_water"]
    assert result["data"] == {
        CONF_PRESET: "swbno_boil_water",
        CONF_LAYER_URL: LAYER_URL,
        CONF_WHERE: preset["where"],
        CONF_TITLE_FIELD: "Advisory_Title",
        CONF_FIELDS: preset["fields"],
        CONF_DEVICE_CLASS: "problem",
        CONF_LOCATION: LOCATION,
    }
    entry = result["result"]
    assert entry.unique_id == (
        f"{LAYER_URL.lower()}|{preset['where']}|{TEST_LATITUDE:.4f},{TEST_LONGITUDE:.4f}"
    )
    await hass.async_block_till_done()

    # The same layer, filter, and location again is a duplicate.
    result = await _start(hass, "swbno_boil_water")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Again", CONF_LOCATION: LOCATION}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_custom_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The custom path validates the layer and creates an entry."""
    aioclient_mock.get(CUSTOM_URL, json=load_fixture("layer_info.json"))
    aioclient_mock.get(f"{CUSTOM_URL}/query", json=load_fixture("query_in_effect.json"))
    result = await _start(hass, "custom")
    assert result["step_id"] == "custom"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Areas",
            CONF_LAYER_URL: f"{CUSTOM_URL}/",
            CONF_WHERE: "Status = 'open'",
            CONF_TITLE_FIELD: "Name",
            CONF_DEVICE_CLASS: "safety",
            CONF_LOCATION: LOCATION,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_PRESET: "custom",
        CONF_LAYER_URL: CUSTOM_URL,
        CONF_WHERE: "Status = 'open'",
        CONF_TITLE_FIELD: "Name",
        CONF_FIELDS: [],
        CONF_DEVICE_CLASS: "safety",
        CONF_LOCATION: LOCATION,
    }


async def _custom_error(hass: HomeAssistant) -> str:
    result = await _start(hass, "custom")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Areas",
            CONF_LAYER_URL: CUSTOM_URL,
            CONF_WHERE: "1=1",
            CONF_LOCATION: LOCATION,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "custom"
    return result["errors"]["base"]


async def test_custom_rejects_layer_without_query(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A layer whose capabilities lack Query is rejected."""
    info = load_fixture("layer_info.json")
    info["capabilities"] = "Map,Data"
    aioclient_mock.get(CUSTOM_URL, json=info)
    assert await _custom_error(hass) == "no_query"


async def test_custom_rejects_non_polygon_layer(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A layer of points is rejected."""
    info = load_fixture("layer_info.json")
    info["geometryType"] = "esriGeometryPoint"
    aioclient_mock.get(CUSTOM_URL, json=info)
    assert await _custom_error(hass) == "not_polygon"


async def test_custom_error_body(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """An ArcGIS error answered with HTTP 200 is an invalid layer."""
    aioclient_mock.get(CUSTOM_URL, json=load_fixture("query_error.json"))
    assert await _custom_error(hass) == "invalid_layer"


async def test_custom_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An HTTP failure is reported as cannot_connect."""
    aioclient_mock.get(CUSTOM_URL, status=503)
    assert await _custom_error(hass) == "cannot_connect"


async def test_options_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Options change the interval, filter, location, and query mode."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_in_effect.json"))
    result = await _start(hass, "swbno_boil_water")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Boil water", CONF_LOCATION: LOCATION}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL_MINUTES: 2,
            CONF_WHERE: "1=1",
            CONF_LOCATION: {CONF_LATITUDE: 29.95, CONF_LONGITUDE: -90.07},
            CONF_QUERY_MODE: "server",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {
        CONF_SCAN_INTERVAL_MINUTES: 2,
        CONF_WHERE: "1=1",
        CONF_LOCATION: {CONF_LATITUDE: 29.95, CONF_LONGITUDE: -90.07},
        CONF_QUERY_MODE: "server",
    }
    coordinator = entry.runtime_data
    assert coordinator.query_mode == "server"
    assert coordinator.update_interval.total_seconds() == 120
