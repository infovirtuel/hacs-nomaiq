"""Config flow for the nomaiq integration."""

from __future__ import annotations

import logging
from typing import Any

import ayla_iot_unofficial
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    client_id = data[CONF_CLIENT_ID]
    client_secret = data[CONF_CLIENT_SECRET]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    session = async_get_clientsession(hass)
    hub = ayla_iot_unofficial.new_ayla_api(
        username, password, client_id, client_secret, session
    )
    await hub.async_sign_in()
    return data


class NomaIQConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for nomaiq."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # If this is a reauth flow, get the existing entry
        if self._reauth_entry:
            if user_input is not None:
                # Update the existing entry
                try:
                    await validate_input(self.hass, user_input)
                except ayla_iot_unofficial.AylaApiError:
                    errors["base"] = "cannot_connect"
                except ayla_iot_unofficial.AylaAuthError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    # Update the existing entry with new data
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry, data=user_input
                    )
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")

            # Show form with current values for reauth
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(
                    CONFIG_SCHEMA, self._reauth_entry.data
                ),
                errors=errors,
                description_placeholders={
                    "username": self._reauth_entry.data[CONF_USERNAME]
                },
            )

        # Handle new configuration
        if user_input is not None:
            self._async_abort_entries_match({CONF_USERNAME: user_input[CONF_USERNAME]})
            try:
                await validate_input(self.hass, user_input)
            except ayla_iot_unofficial.AylaApiError:
                errors["base"] = "cannot_connect"
            except ayla_iot_unofficial.AylaAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=DOMAIN, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=CONFIG_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_user(user_input)
