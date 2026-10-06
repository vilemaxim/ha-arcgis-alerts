"""Tests for polling and the binary sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.arcgis_alerts.const import (
    CONF_FIELDS,
    CONF_LAYER_URL,
    CONF_LOCATION,
    CONF_PRESET,
    CONF_QUERY_MODE,
    CONF_TITLE_FIELD,
    CONF_WHERE,
    DOMAIN,
    PRESETS,
)

from .conftest import LAYER_URL, QUERY_URL, TEST_LATITUDE, TEST_LONGITUDE, load_fixture

ENTITY_ID = "binary_sensor.boil_water"


def _entry(
    latitude: float = TEST_LATITUDE,
    longitude: float = TEST_LONGITUDE,
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    preset = PRESETS["swbno_boil_water"]
    return MockConfigEntry(
        domain=DOMAIN,
        title="Boil water",
        data={
            CONF_PRESET: "swbno_boil_water",
            CONF_LAYER_URL: LAYER_URL,
            CONF_WHERE: preset["where"],
            CONF_TITLE_FIELD: preset["title_field"],
            CONF_FIELDS: preset["fields"],
            CONF_DEVICE_CLASS: preset["device_class"],
            CONF_LOCATION: {CONF_LATITUDE: latitude, CONF_LONGITUDE: longitude},
        },
        options=options or {},
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_nothing_in_effect(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """An empty in-effect set is off, with empty attributes."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_in_effect.json"))
    await _setup(hass, _entry())

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes["device_class"] == "problem"
    assert state.attributes["count"] == 0
    assert state.attributes["title"] is None
    assert state.attributes["features"] == []
    assert state.attributes["layer_url"] == LAYER_URL

    params = aioclient_mock.mock_calls[0][1].query
    assert params["where"] == PRESETS["swbno_boil_water"]["where"]
    assert params["returnGeometry"] == "true"
    assert params["outSR"] == "4326"
    assert "geometry" not in params


async def test_features_cover_location(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Local mode: the three recorded polygons cover the test point."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_at_point_all.json"))
    await _setup(hass, _entry())

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes["count"] == 3
    assert state.attributes["title"] == "Testing- Precautionary BWA - East Bank of NO"
    features = state.attributes["features"]
    assert len(features) == 3
    assert list(features[1]) == PRESETS["swbno_boil_water"]["fields"]
    assert features[1] == {
        "Advisory_Title": "Lifted BWA for East Bank",
        "Advisory_Details": (
            "Lifted/Canceled - Precautionary Boil Water Advisory for "
            "Significant Portion of East Bank"
        ),
        "Adv_Type": "BWA",
        "Adv_Status": "archived",
        "Public_Begin_DT": "2026-02-23T06:00:00+00:00",
    }


async def test_features_elsewhere(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Local mode: features that do not cover the location leave the sensor off."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_at_point_all.json"))
    await _setup(hass, _entry(latitude=31.0, longitude=-91.5))

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes["count"] == 0


async def test_server_mode(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Server mode sends the point and trusts the server's answer."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_at_point_all.json"))
    await _setup(hass, _entry(options={CONF_QUERY_MODE: "server"}))

    assert hass.states.get(ENTITY_ID).state == STATE_ON
    params = aioclient_mock.mock_calls[0][1].query
    assert params["geometry"] == f"{TEST_LONGITUDE},{TEST_LATITUDE}"
    assert params["geometryType"] == "esriGeometryPoint"
    assert params["inSR"] == "4326"
    assert params["spatialRel"] == "esriSpatialRelIntersects"
    assert params["returnGeometry"] == "false"


async def test_error_body_is_not_off(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An ArcGIS error with HTTP 200 fails setup instead of reporting off."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_error.json"))
    entry = _entry()
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.states.get(ENTITY_ID) is None


async def test_error_after_setup_is_unavailable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failed poll after setup makes the entity unavailable, not off."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_at_point_all.json"))
    entry = _entry()
    await _setup(hass, entry)
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    aioclient_mock.clear_requests()
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_error.json"))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(QUERY_URL, status=500)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE


async def test_unload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The entry unloads."""
    aioclient_mock.get(QUERY_URL, json=load_fixture("query_in_effect.json"))
    entry = _entry()
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
