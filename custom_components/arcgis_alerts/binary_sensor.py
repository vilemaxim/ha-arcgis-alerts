"""Binary sensor: on when a layer feature covers the configured location."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_DEVICE_CLASS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_FEATURES_IN_ATTRIBUTES
from .coordinator import ArcGISAlertsConfigEntry, ArcGISAlertsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcGISAlertsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor for a config entry."""
    async_add_entities([ArcGISAlertBinarySensor(entry.runtime_data, entry)])


class ArcGISAlertBinarySensor(
    CoordinatorEntity[ArcGISAlertsCoordinator], BinarySensorEntity
):
    """On while at least one feature of the layer covers the location."""

    _attr_has_entity_name = True
    _attr_name = None
    # The feature list can be long; keep it out of the recorder's history.
    _unrecorded_attributes = frozenset({"features", "layer_url"})

    def __init__(
        self, coordinator: ArcGISAlertsCoordinator, entry: ArcGISAlertsConfigEntry
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
        device_class = entry.data.get(CONF_DEVICE_CLASS)
        self._attr_device_class = (
            BinarySensorDeviceClass(device_class) if device_class else None
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ArcGIS feature layer",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.layer_url,
        )

    @property
    def is_on(self) -> bool:
        """Return True when a feature covers the location."""
        return bool(self.coordinator.data.features)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the matching features."""
        data = self.coordinator.data
        return {
            "count": len(data.features),
            "title": data.title,
            "features": data.features[:MAX_FEATURES_IN_ATTRIBUTES],
            "layer_url": self.coordinator.layer_url,
        }
