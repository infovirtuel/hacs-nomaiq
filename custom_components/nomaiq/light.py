"""Platform for light integration with color, brightness, and temperature support."""

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
        self._attr_supported_color_modes = {
            ColorMode.ONOFF, ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP, ColorMode.HS
        }
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
        device = next(
            (d for d in self.coordinator.data if d.serial_number == self._device.serial_number),
            None,
        )
        state = device and device.get_property_value("power")
        _LOGGER.debug("Light %s is_on read as: %s", self._device.serial_number, state)
        return state

    @property
    def brightness(self) -> int | None:
        """Return brightness (0-255)."""
        device = next(
            (d for d in self.coordinator.data if d.serial_number == self._device.serial_number),
            None,
        )
        brightness = None
        if device:
            val = device.get_property_value("brightness")
            if val is not None:
                brightness = int(val * 255 / 100)
        _LOGGER.debug("Light %s brightness read as: %s", self._device.serial_number, brightness)
        return brightness

    @property
    def color_temp(self) -> int | None:
        """Return color temperature in mireds."""
        device = next(
            (d for d in self.coordinator.data if d.serial_number == self._device.serial_number),
            None,
        )
        ct = None
        if device:
            val = device.get_property_value("color_temp")
            if val is not None:
                # Assuming device uses 0-100 scale for temperature, convert to mireds 153-500
                ct = int(153 + (100 - val) * (500 - 153) / 100)
        _LOGGER.debug("Light %s color_temp read as: %s", self._device.serial_number, ct)
        return ct

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return HS color."""
        device = next(
            (d for d in self.coordinator.data if d.serial_number == self._device.serial_number),
            None,
        )
        hs = None
        if device:
            hue = device.get_property_value("color_select")
            sat = device.get_property_value("color_saturation")
            if hue is not None and sat is not None:
                hs = (hue % 360, sat)
        _LOGGER.debug("Light %s HS color read as: %s", self._device.serial_number, hs)
        return hs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn device on with optional color/brightness/temperature."""
        _LOGGER.debug("Turning ON light %s with kwargs: %s", self._device.serial_number, kwargs)
        try:
            await self._device.async_set_property_value("power", 1)

            if brightness := kwargs.get("brightness"):
                val = int(brightness * 100 / 255)
                await self._device.async_set_property_value("brightness", val)
                _LOGGER.debug("Set brightness=%s", val)

            if color_temp := kwargs.get("color_temp"):
                # Convert mireds to 0-100 scale
                val = int(100 - (color_temp - 153) * 100 / (500 - 153))
                await self._device.async_set_property_value("color_temp", val)
                _LOGGER.debug("Set color_temp=%s", val)

            if hs_color := kwargs.get("hs_color"):
                hue, sat = hs_color
                await self._device.async_set_property_value("color_select", int(hue))
                await self._device.async_set_property_value("color_saturation", int(sat))
                _LOGGER.debug("Set HS color=%s", hs_color)

            _LOGGER.debug("Write commands sent to %s", self._device.serial_number)
        except Exception as e:
            _LOGGER.error("Failed to turn on light %s: %s", self._device.serial_number, e)

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
