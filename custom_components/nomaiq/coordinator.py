"""Coordinator for NomaIQ devices with responsive light updates."""

from datetime import timedelta
from typing import Set

import ayla_iot_unofficial
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, NORMAL_UPDATE_INTERVAL, TRANSITION_UPDATE_INTERVAL


class NomaIQDataUpdateCoordinator(
    DataUpdateCoordinator[list[ayla_iot_unofficial.device.Device]]
):
    """Devices state update handler with responsive light handling."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger,
        update_interval: timedelta,
        api: ayla_iot_unofficial.AylaApi,
    ) -> None:
        """Initialize global data updater."""
        self._api = api
        self._devices_in_transition: Set[str] = set()  # Track devices in transition
        self._last_full_update = 0

        # Track intended light states for optimistic transition
        self._intended_light_states: dict[str, int] = {}

        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=update_interval,
            update_method=self._async_update_data,
        )

    @property
    def api(self) -> ayla_iot_unofficial.AylaApi:
        """Return the API instance."""
        return self._api

    def set_device_transition_state(self, device_serial: str, in_transition: bool, intended_power: int | None = None) -> None:
        """Mark a device as in transition (faster polling)."""
        if in_transition:
            self._devices_in_transition.add(device_serial)
            if intended_power is not None:
                self._intended_light_states[device_serial] = intended_power
            if self.update_interval.total_seconds() != TRANSITION_UPDATE_INTERVAL:
                self.update_interval = timedelta(seconds=TRANSITION_UPDATE_INTERVAL)
                self.logger.debug(
                    "Switched to fast update interval for device %s", device_serial
                )
        else:
            self._devices_in_transition.discard(device_serial)
            self._intended_light_states.pop(device_serial, None)
            if not self._devices_in_transition and self.update_interval.total_seconds() != NORMAL_UPDATE_INTERVAL:
                self.update_interval = timedelta(seconds=NORMAL_UPDATE_INTERVAL)
                self.logger.debug("Switched back to normal update interval")

    def is_device_in_transition(self, device_serial: str) -> bool:
        """Check if a device is currently in transition state."""
        return device_serial in self._devices_in_transition

    async def _async_update_data(self) -> list[ayla_iot_unofficial.device.Device]:
        """Fetch data and handle transitions."""
        try:
            # Ensure API authentication
            try:
                self._api.check_auth()
            except ayla_iot_unofficial.AylaAuthExpiringError:
                await self._api.async_refresh_auth()
            except Exception as ex:
                self.logger.error("Failed to refresh auth: %s", ex)
                raise UpdateFailed("Failed to refresh auth") from ex

            devices = await self._api.async_get_devices()
            current_time = self.hass.loop.time()

            is_full_update = (
                self.update_interval.total_seconds() == NORMAL_UPDATE_INTERVAL
                or current_time - self._last_full_update >= NORMAL_UPDATE_INTERVAL
            )

            if is_full_update:
                # Full update: refresh all devices
                self.logger.debug("Performing full update of all devices")
                for device in devices:
                    await device.async_update()
                self._last_full_update = current_time
            else:
                # Transition update: only devices in transition
                self.logger.debug(
                    "Performing transition update for %d devices", len(self._devices_in_transition)
                )
                for device in devices:
                    if device.serial_number in self._devices_in_transition:
                        await device.async_update()

                        # Check light transitions
                        if device.serial_number in self._intended_light_states:
                            intended_power = self._intended_light_states[device.serial_number]
                            current_power = device.get_property_value("power")
                            if current_power == intended_power:
                                self.set_device_transition_state(device.serial_number, False)
                                self.logger.debug(
                                    "Light %s transition completed, power=%s",
                                    device.serial_number,
                                    current_power,
                                )

                        # Check doors/shades transitions
                        door_status = device.get_property_value("door_status")
                        if door_status in ["opened", "closed"]:
                            self.set_device_transition_state(device.serial_number, False)
                            self.logger.debug(
                                "Device %s transition completed, status: %s",
                                device.serial_number,
                                door_status,
                            )

        except Exception as ex:
            raise UpdateFailed(f"Exception on getting states: {ex}") from ex
        else:
            return devices
