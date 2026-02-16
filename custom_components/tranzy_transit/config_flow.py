"""Config flow for Tranzy Transit integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TranzyApiClient, TranzyAuthError, TranzyConnectionError
from .const import (
    CONF_AGENCY_ID,
    CONF_API_KEY,
    CONF_MAX_ARRIVALS,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_VEHICLE_TYPES,
    DEFAULT_MAX_ARRIVALS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VEHICLE_TYPES,
    DOMAIN,
    KNOWN_AGENCIES,
    VEHICLE_TYPE_NAMES,
)

_LOGGER = logging.getLogger(__name__)


class TranzyTransitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tranzy Transit."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            agency_id = user_input[CONF_AGENCY_ID]
            stop_id = str(user_input[CONF_STOP_ID])
            stop_name = user_input.get(CONF_STOP_NAME, f"Stop {stop_id}")

            # Check for duplicates
            await self.async_set_unique_id(f"{agency_id}_{stop_id}")
            self._abort_if_unique_id_configured()

            # Validate the API connection
            session = async_get_clientsession(self.hass)
            client = TranzyApiClient(session, api_key, agency_id)

            try:
                valid = await client.test_connection()
                if not valid:
                    errors["base"] = "cannot_connect"
                else:
                    # Validate the stop exists
                    stop_data = await client.validate_stop(stop_id)
                    if stop_data is None:
                        errors["base"] = "invalid_stop"
                    else:
                        # Use the official stop name if user didn't provide one
                        if stop_name == f"Stop {stop_id}":
                            stop_name = stop_data.get("stop_name", stop_name)

                        return self.async_create_entry(
                            title=f"{stop_name} ({agency_id})",
                            data={
                                CONF_API_KEY: api_key,
                                CONF_AGENCY_ID: agency_id,
                                CONF_STOP_ID: stop_id,
                                CONF_STOP_NAME: stop_name,
                            },
                            options={
                                CONF_SCAN_INTERVAL: user_input.get(
                                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                                ),
                                CONF_VEHICLE_TYPES: user_input.get(
                                    CONF_VEHICLE_TYPES, DEFAULT_VEHICLE_TYPES
                                ),
                                CONF_MAX_ARRIVALS: DEFAULT_MAX_ARRIVALS,
                            },
                        )
            except TranzyAuthError:
                errors["base"] = "invalid_auth"
            except TranzyConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"

        # Build the schema
        agency_options = list(KNOWN_AGENCIES.keys())
        vehicle_type_options = list(VEHICLE_TYPE_NAMES.keys())

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_AGENCY_ID): vol.In(agency_options) if agency_options else str,
                    vol.Required(CONF_STOP_ID): str,
                    vol.Optional(CONF_STOP_NAME, default=""): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(int, vol.Range(min=10, max=300)),
                    vol.Optional(
                        CONF_VEHICLE_TYPES, default=DEFAULT_VEHICLE_TYPES
                    ): vol.All(
                        [vol.In(vehicle_type_options)],
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TranzyTransitOptionsFlow:
        """Get the options flow for this handler."""
        return TranzyTransitOptionsFlow(config_entry)


class TranzyTransitOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Tranzy Transit."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        vehicle_type_options = list(VEHICLE_TYPE_NAMES.keys())

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(int, vol.Range(min=10, max=300)),
                    vol.Optional(
                        CONF_VEHICLE_TYPES,
                        default=self._config_entry.options.get(
                            CONF_VEHICLE_TYPES, DEFAULT_VEHICLE_TYPES
                        ),
                    ): vol.All(
                        [vol.In(vehicle_type_options)],
                    ),
                    vol.Optional(
                        CONF_MAX_ARRIVALS,
                        default=self._config_entry.options.get(
                            CONF_MAX_ARRIVALS, DEFAULT_MAX_ARRIVALS
                        ),
                    ): vol.All(int, vol.Range(min=1, max=20)),
                }
            ),
        )
