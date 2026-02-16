"""DataUpdateCoordinator for Tranzy Transit."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TranzyApiClient, TranzyApiError, TranzyAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class TranzyTransitCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch transit arrivals from Tranzy API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: TranzyApiClient,
        stop_id: str,
        stop_name: str,
        vehicle_types: list[str],
        max_arrivals: int,
        update_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{stop_id}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self.stop_id = stop_id
        self.stop_name = stop_name
        self.vehicle_types = vehicle_types
        self.max_arrivals = max_arrivals

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Tranzy API."""
        try:
            arrivals = await self.client.get_arrivals_for_stop(
                stop_id=self.stop_id,
                vehicle_type_filter=self.vehicle_types if self.vehicle_types else None,
                max_arrivals=self.max_arrivals,
            )

            # Group arrivals by route for easy display
            by_route: dict[str, list[dict]] = {}
            for arrival in arrivals:
                key = arrival["route_short_name"]
                if key not in by_route:
                    by_route[key] = []
                by_route[key].append(arrival)

            # Limit per route
            for key in by_route:
                by_route[key] = by_route[key][: self.max_arrivals]

            return {
                "stop_id": self.stop_id,
                "stop_name": self.stop_name,
                "arrivals": arrivals,
                "arrivals_by_route": by_route,
                "route_names": sorted(by_route.keys(), key=lambda x: (not x.isdigit(), x.zfill(10) if x.isdigit() else x)),
                "total_arrivals": len(arrivals),
            }

        except TranzyAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except TranzyApiError as err:
            raise UpdateFailed(f"Error fetching transit data: {err}") from err
