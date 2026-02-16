"""Coordinator for Tranzy Transit."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TranzyApiClient, TranzyApiError
from .const import (
    CONF_AGENCY_ID,
    CONF_API_KEY,
    CONF_MAX_ARRIVALS,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_VEHICLE_TYPES,
    DEFAULT_MAX_ARRIVALS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VEHICLE_TYPES,
    DOMAIN,
)


class TranzyTransitCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry

        self._api_key = entry.data[CONF_API_KEY]
        self._agency_id = entry.data[CONF_AGENCY_ID]
        self._stop_id = entry.data[CONF_STOP_ID]

        self._scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self._vehicle_types = entry.options.get(CONF_VEHICLE_TYPES, DEFAULT_VEHICLE_TYPES)
        self._max_arrivals = entry.options.get(CONF_MAX_ARRIVALS, DEFAULT_MAX_ARRIVALS)

        session = async_get_clientsession(hass)
        self.client = TranzyApiClient(session, self._api_key, self._agency_id)

        super().__init__(
            hass,
            logger=None,
            name=f"{DOMAIN}_{self._agency_id}_{self._stop_id}",
            update_interval=timedelta(seconds=self._scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            arrivals = await self.client.get_arrivals(
                stop_id=int(self._stop_id),
                vehicle_type_filter=list(self._vehicle_types) if self._vehicle_types else None,
                max_arrivals=int(self._max_arrivals),
            )

            arrivals_by_route: dict[str, list[dict[str, Any]]] = {}
            for a in arrivals:
                rn = a.get("route_short_name", "")
                arrivals_by_route.setdefault(rn, []).append(a)

            route_names = sorted([k for k in arrivals_by_route.keys() if k])

            return {
                "arrivals": arrivals,
                "arrivals_by_route": arrivals_by_route,
                "route_names": route_names,
                "total_vehicles": len(arrivals),
            }

        except TranzyApiError as e:
            raise UpdateFailed(str(e)) from e
        except Exception as e:
            raise UpdateFailed(f"Unexpected error: {e}") from e