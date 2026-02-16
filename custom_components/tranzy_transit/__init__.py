"""The Tranzy Transit integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TranzyApiClient
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
)
from .coordinator import TranzyTransitCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tranzy Transit from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    client = TranzyApiClient(
        session=session,
        api_key=entry.data[CONF_API_KEY],
        agency_id=entry.data[CONF_AGENCY_ID],
    )

    coordinator = TranzyTransitCoordinator(
        hass=hass,
        client=client,
        stop_id=entry.data[CONF_STOP_ID],
        stop_name=entry.data.get(CONF_STOP_NAME, f"Stop {entry.data[CONF_STOP_ID]}"),
        vehicle_types=entry.options.get(CONF_VEHICLE_TYPES, DEFAULT_VEHICLE_TYPES),
        max_arrivals=entry.options.get(CONF_MAX_ARRIVALS, DEFAULT_MAX_ARRIVALS),
        update_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
