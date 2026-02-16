"""Config flow for Tranzy Transit — numeric agency_id (e.g. 8)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TranzyApiClient, TranzyAuthError, TranzyConnectionError
from .const import (
    CONF_AGENCY_ID, CONF_AGENCY_NAME, CONF_API_KEY, CONF_MAX_ARRIVALS,
    CONF_SCAN_INTERVAL, CONF_STOP_ID, CONF_STOP_NAME, CONF_VEHICLE_TYPES,
    DEFAULT_MAX_ARRIVALS, DEFAULT_SCAN_INTERVAL, DEFAULT_VEHICLE_TYPES,
    DOMAIN, VEHICLE_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class TranzyTransitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            agency_id = int(user_input[CONF_AGENCY_ID])
            stop_id = int(user_input[CONF_STOP_ID])
            stop_name = user_input.get(CONF_STOP_NAME, "").strip()
            vt = user_input.get(CONF_VEHICLE_TYPES, DEFAULT_VEHICLE_TYPES)

            await self.async_set_unique_id(f"{agency_id}_{stop_id}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)

            # Test API key
            client = TranzyApiClient(session, api_key, agency_id)
            try:
                if not await client.test_api_key():
                    errors["base"] = "invalid_auth"
            except TranzyConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"

            # Test agency
            if not errors:
                try:
                    if not await client.test_agency():
                        errors["base"] = "invalid_agency"
                except TranzyConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error")
                    errors["base"] = "unknown"

            # Validate stop
            if not errors:
                try:
                    stop_data = await client.validate_stop(stop_id)
                    if stop_data is None:
                        errors["base"] = "invalid_stop"
                    else:
                        if not stop_name:
                            stop_name = stop_data.get("stop_name", f"Stop {stop_id}")

                        # Get agency display name
                        agency_name = f"Agency {agency_id}"
                        try:
                            agencies = await client.get_agencies()
                            for ag in agencies:
                                if int(ag.get("agency_id", -1)) == agency_id:
                                    agency_name = ag.get("agency_name", agency_name)
                                    break
                        except Exception:
                            pass

                        return self.async_create_entry(
                            title=f"{stop_name} ({agency_name})",
                            data={
                                CONF_API_KEY: api_key,
                                CONF_AGENCY_ID: agency_id,
                                CONF_AGENCY_NAME: agency_name,
                                CONF_STOP_ID: stop_id,
                                CONF_STOP_NAME: stop_name,
                            },
                            options={
                                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                                CONF_VEHICLE_TYPES: vt,
                                CONF_MAX_ARRIVALS: DEFAULT_MAX_ARRIVALS,
                            },
                        )
                except TranzyConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error")
                    errors["base"] = "unknown"

        # Vehicle type selector: {0: "Tram", 3: "Bus", ...}
        vt_options = {k: v for k, v in VEHICLE_TYPES.items()}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_AGENCY_ID, default=8): int,
                vol.Required(CONF_STOP_ID, default=70): int,
                vol.Optional(CONF_STOP_NAME, default=""): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    int, vol.Range(min=10, max=300)
                ),
                vol.Optional(CONF_VEHICLE_TYPES, default=DEFAULT_VEHICLE_TYPES): vol.All(
                    [vol.In(vt_options)]
                ),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TranzyOptionsFlow(config_entry)


class TranzyOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        vt_options = {k: v for k, v in VEHICLE_TYPES.items()}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=10, max=300)),
                vol.Optional(
                    CONF_VEHICLE_TYPES,
                    default=self._entry.options.get(CONF_VEHICLE_TYPES, DEFAULT_VEHICLE_TYPES),
                ): vol.All([vol.In(vt_options)]),
                vol.Optional(
                    CONF_MAX_ARRIVALS,
                    default=self._entry.options.get(CONF_MAX_ARRIVALS, DEFAULT_MAX_ARRIVALS),
                ): vol.All(int, vol.Range(min=1, max=30)),
            }),
        )
