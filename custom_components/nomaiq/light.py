"""Platform for light integration with debug logging."""

from __future__ import annotations

from typing import Any
import logging

import ayla_iot_unofficial
import ayla_iot_unofficial.device

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NomaIQConfigEntry
from .const import DOMAIN
from .coordinator import NomaIQDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: NomaIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Noma IQ Light platform."""
    coordinator: NomaIQDataUpdateCoordinator = entry.runtime_data

    for device in coordinator.data:
        # Use the actual properties from your debug logs
        if "power" in device.properties_full and "voice_data" in device.properties_full:
            async_add_entities(
                [NomaIQLightEntity(coordinator, device)], update_before_add=False
            )


class NomaIQLightEntity(LightEntity):
    """Representation of a NomaIQ Light."""

    def __init__(
        self,
        coordinator: NomaIQDataUpdateCoordinator,
        device: ayla_iot_unofficial.device.Device,
    ) -> None:
        """Initialize a NomaIQ light."""
        self.coordinator = coordinator
        self._device = device
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_name = device.get_property_value("voice_data") or device.name
        self._attr_unique_id = f"nomaiq_light_{device.serial_number}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.serial_number)},
            name=device.name,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        data: list[ayla_iot_unofficial.device.Device] = self.coordinator.data
        device: ayla_iot_unofficial.device.Device | None = next(
            (d for d in data if d.serial_number == self._device.serial_number),
            None,
        )
        state = device and device.get_property_value("power")
        _LOGGER.debug("Light %s is_on read as: %s", self._device.serial_number, state)
        return state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn device on."""
        _LOGGER.debug("Turning ON light %s", self._device.serial_number)
        try:
            await self._device.async_set_property_value("power", 1)
            _LOGGER.debug("Write command sent: power=1")
        except Exception as e:
            _LOGGER.error("Failed to send power=1 to %s: %s", self._device.serial_number, e)
        await self.coordinator.async_request_refresh()
        _LOGGER.debug("Requested coordinator refresh after turning ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn device off."""
        _LOGGER.debug("Turning OFF light %s", self._device.serial_number)
        try:
            await self._device.async_set_property_value("power", 0)
            _LOGGER.debug("Write command sent: power=0")
        except Exception as e:
            _LOGGER.error("Failed to send power=0 to %s: %s", self._device.serial_number, e)
        await self.coordinator.async_request_refresh()
        _LOGGER.debug("Requested coordinator refresh after turning OFF")

    async def async_update(self) -> None:
        """Update the light state."""
        _LOGGER.debug("Requesting coordinator refresh for light %s", self._device.serial_number)
        await self.coordinator.async_request_refresh()
