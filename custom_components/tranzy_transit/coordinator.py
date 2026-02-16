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
    def __init__(
        self, hass: HomeAssistant, client: TranzyApiClient,
        stop_id: int, stop_name: str, vehicle_types: list[int],
        update_interval: int,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_{stop_id}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self.stop_id = stop_id
        self.stop_name = stop_name
        self.vehicle_types = vehicle_types

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            arrivals = await self.client.get_arrivals(
                stop_id=self.stop_id,
                vehicle_type_filter=self.vehicle_types if self.vehicle_types else None,
            )

            by_route: dict[str, list[dict]] = {}
            for a in arrivals:
                key = a["route_short_name"]
                by_route.setdefault(key, []).append(a)

            return {
                "stop_id": self.stop_id,
                "stop_name": self.stop_name,
                "arrivals": arrivals,
                "arrivals_by_route": by_route,
                "route_names": sorted(
                    by_route.keys(),
                    key=lambda x: (not x.isdigit(), x.zfill(10) if x.isdigit() else x),
                ),
                "total_vehicles": len(arrivals),
            }
        except TranzyAuthError as err:
            raise UpdateFailed(f"Auth: {err}") from err
        except TranzyApiError as err:
            raise UpdateFailed(f"API: {err}") from err
