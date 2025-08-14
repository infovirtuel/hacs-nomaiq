"""Platform for NomaIQ light integration with full color, brightness, and temperature support."""

from __future__ import annotations
from typing import Any
import logging

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
    """Representation of a NomaIQ Light with optimistic updates."""

    def __init__(self, coordinator: NomaIQDataUpdateCoordinator, device: ayla_iot_unofficial.device.Device) -> None:
        self.coordinator = coordinator
        self._device = device

        # Device capabilities
        self._is_color = "color_select" in device.properties_full and "color_saturation" in device.properties_full
        self._is_white_only = "color_temp" in device.properties_full

        self._attr_supported_color_modes = {ColorMode.ONOFF, ColorMode.BRIGHTNESS}
        if self._is_white_only:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
        if self._is_color:
            self._attr_supported_color_modes.add(ColorMode.HS)

        if self._is_color:
            self._attr_color_mode = ColorMode.HS
        elif self._is_white_only:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        else:
            self._attr_color_mode = ColorMode.ONOFF

        self._attr_name = device.get_property_value("voice_data") or device.name
        self._attr_unique_id = f"nomaiq_light_{device.serial_number}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.serial_number)},
            name=device.name,
        )

        # Optimistic state
        self._optimistic_is_on: bool | None = None
        self._optimistic_brightness: int | None = None
        self._optimistic_color_temp: int | None = None
        self._optimistic_hs_color: tuple[float, float] | None = None

    def _get_device(self) -> ayla_iot_unofficial.device.Device | None:
        return next(
            (d for d in self.coordinator.data if d.serial_number == self._device.serial_number),
            None,
        )

    @property
    def is_on(self) -> bool | None:
        return self._optimistic_is_on if self._optimistic_is_on is not None else (
            self._get_device() and self._get_device().get_property_value("power")
        )

    @property
    def brightness(self) -> int | None:
        if self._optimistic_brightness is not None:
            return self._optimistic_brightness
        device = self._get_device()
        if device:
            val = device.get_property_value("brightness")
            if val is not None:
                return int(val * 255 / 100)
        return None

    @property
    def color_temp(self) -> int | None:
        if self._optimistic_color_temp is not None:
            return self._optimistic_color_temp
        device = self._get_device()
        if device and device.get_property_value("mode") == "white":
            val = device.get_property_value("color_temp")
            if val is not None:
                return int(153 + (100 - val) * (500 - 153) / 100)
        return None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        if self._optimistic_hs_color:
            return self._optimistic_hs_color
        device = self._get_device()
        if device and device.get_property_value("mode") == "colour":
            hue = device.get_property_value("color_select")
            sat = device.get_property_value("color_saturation")
            if hue is not None and sat is not None:
                return (hue % 360, sat)
        return None

    @property
    def color_mode(self) -> ColorMode:
        device = self._get_device()
        if not device or not device.get_property_value("power"):
            return ColorMode.ONOFF
        mode = device.get_property_value("mode") or "white"
        if mode == "colour" and self._is_color:
            return ColorMode.HS
        elif mode == "white" and self._is_white_only:
            return ColorMode.COLOR_TEMP
        elif mode == "white" and self._is_color:
            return ColorMode.COLOR_TEMP
        else:
            return ColorMode.ONOFF

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn device on with optional color/brightness/temperature."""
        _LOGGER.debug("Turning ON light %s with kwargs: %s", self._device.serial_number, kwargs)

        # Update optimistic state
        self._optimistic_is_on = True
        if "brightness" in kwargs:
            self._optimistic_brightness = kwargs["brightness"]
        if "color_temp" in kwargs:
            self._optimistic_color_temp = kwargs["color_temp"]
        if "hs_color" in kwargs:
            self._optimistic_hs_color = kwargs["hs_color"]
        self.async_write_ha_state()

        try:
            await self._device.async_set_property_value("power", 1)
            if "brightness" in kwargs:
                val = int(kwargs["brightness"] * 100 / 255)
                await self._device.async_set_property_value("brightness", val)
            if "hs_color" in kwargs:
                hue, sat = kwargs["hs_color"]
                await self._device.async_set_property_value("mode", "colour")
                await self._device.async_set_property_value("color_select", int(hue))
                await self._device.async_set_property_value("color_saturation", int(sat))
            elif "color_temp" in kwargs:
                await self._device.async_set_property_value("mode", "white")
                val = int(100 - (kwargs["color_temp"] - 153) * 100 / (500 - 153))
                await self._device.async_set_property_value("color_temp", val)
        except Exception as e:
            _LOGGER.error("Failed to turn on light %s: %s", self._device.serial_number, e)
            self._optimistic_is_on = None

        # Coordinator refresh optional; HA already shows the optimistic state
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn device off."""
        _LOGGER.debug("Turning OFF light %s", self._device.serial_number)
        self._optimistic_is_on = False
        self.async_write_ha_state()

        try:
            await self._device.async_set_property_value("power", 0)
        except Exception as e:
            _LOGGER.error("Failed to send power=0 to %s: %s", self._device.serial_number, e)
            self._optimistic_is_on = None

        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        """Update the light state and clear optimistic values."""
        self._optimistic_is_on = None
        self._optimistic_brightness = None
        self._optimistic_color_temp = None
        self._optimistic_hs_color = None
        await self.coordinator.async_request_refresh()
