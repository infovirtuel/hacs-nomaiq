"""Platform for light integration."""

from __future__ import annotations

import time
from typing import Any

import ayla_iot_unofficial
import ayla_iot_unofficial.device

from homeassistant.components.cover import (
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NomaIQConfigEntry
from .const import DOMAIN
from .coordinator import NomaIQDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NomaIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Noma IQ Cover platform."""
    coordinator: NomaIQDataUpdateCoordinator = entry.runtime_data

    for device in coordinator.data:
        if device.oem_model_number == "gdo":
            # Garage Door Opener
            async_add_entities(
                [NomaIQGarageDoorOpenerEntity(coordinator, device)],
                update_before_add=False,
            )


class NomaIQGarageDoorOpenerEntity(CoverEntity):
    """Representation of a NomaIQ Garage Door Opener."""

    def __init__(
        self,
        coordinator: NomaIQDataUpdateCoordinator,
        device: ayla_iot_unofficial.device.Device,
    ) -> None:
        """Initialize a NomaIQ Garage Door Opener."""
        self.coordinator = coordinator
        self._device = device
        self.device_class = CoverDeviceClass.GARAGE
        self.supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        self._attr_name = device.name
        self._attr_unique_id = f"nomaiq_cover_{device.serial_number}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.serial_number)},
            name=device.name,
        )

    def _get_current_device(self) -> ayla_iot_unofficial.device.Device | None:
        """Get the current device from coordinator data."""
        data: list[ayla_iot_unofficial.device.Device] = self.coordinator.data
        return next(
            (d for d in data if d.serial_number == self._device.serial_number),
            None,
        )

    def _get_door_status(self) -> str | None:
        """Get the current door status."""
        device = self._get_current_device()
        return device.get_property_value("door_status") if device else None

    def _update_transition_state(self) -> None:
        """Update the transition state based on current door status."""
        door_status = self._get_door_status()
        if door_status in ["opening", "closing"]:
            self.coordinator.set_device_transition_state(
                self._device.serial_number, True
            )
        else:
            self.coordinator.set_device_transition_state(
                self._device.serial_number, False
            )

    @property
    def is_closed(self) -> bool | None:
        """Return True if door is closed."""
        door_status = self._get_door_status()
        return door_status == "closed"

    @property
    def is_closing(self) -> bool | None:
        """Return True if door is closing."""
        door_status = self._get_door_status()
        return door_status == "closing"

    @property
    def is_opening(self) -> bool | None:
        """Return True if door is opening."""
        door_status = self._get_door_status()
        return door_status == "opening"

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the door."""
        await self._device.async_set_property_value(
            "door_toggle", str(int(time.time()))
        )
        # Notify coordinator that device is entering transition state
        self.coordinator.set_device_transition_state(self._device.serial_number, True)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the door."""
        await self._device.async_set_property_value(
            "door_toggle", str(int(time.time()))
        )
        # Notify coordinator that device is entering transition state
        self.coordinator.set_device_transition_state(self._device.serial_number, True)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the door."""
        await self._device.async_set_property_value(
            "door_toggle", str(int(time.time()))
        )
        # Notify coordinator that device is entering transition state
        self.coordinator.set_device_transition_state(self._device.serial_number, True)

    async def async_update(self) -> None:
        """Update the door state."""
        await self.coordinator.async_request_refresh()
        # Update transition state after refresh
        self._update_transition_state()
