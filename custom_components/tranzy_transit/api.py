"""Tranzy API client for fetching transit data."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_HEADER_AGENCY,
    API_HEADER_KEY,
    GTFS_ROUTE_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class TranzyApiError(Exception):
    """Base exception for Tranzy API errors."""


class TranzyAuthError(TranzyApiError):
    """Authentication error."""


class TranzyConnectionError(TranzyApiError):
    """Connection error."""


class TranzyApiClient:
    """Client to interact with the Tranzy OpenData API.

    The Tranzy API partially implements the GTFS specification.
    Endpoints used:
        GET /routes       - All routes for the agency
        GET /stops        - All stops for the agency
        GET /stop_times   - Schedule stop times (stop_id, trip_id, arrival/departure)
        GET /trips        - All trips for the agency
        GET /vehicles     - Real-time vehicle positions
    
    Headers required:
        X-API-KEY: <your_api_key>
        X-Agency-Id: <agency_id>
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        agency_id: str,
        base_url: str = API_BASE_URL,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._api_key = api_key
        self._agency_id = agency_id
        self._base_url = base_url.rstrip("/")

        # Caches for relatively static data (routes, stops, trips, stop_times)
        self._routes_cache: dict[str, dict] | None = None
        self._stops_cache: dict[str, dict] | None = None
        self._trips_cache: dict[str, dict] | None = None
        self._stop_times_cache: dict[str, list[dict]] | None = None
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = timedelta(hours=6)  # Refresh static data every 6 hours

    @property
    def _headers(self) -> dict[str, str]:
        """Return API request headers."""
        return {
            API_HEADER_KEY: self._api_key,
            API_HEADER_AGENCY: self._agency_id,
            "Accept": "application/json",
        }

    async def _request(self, endpoint: str) -> list[dict[str, Any]]:
        """Make a GET request to the API."""
        url = f"{self._base_url}/{endpoint}"
        try:
            async with self._session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 401 or resp.status == 403:
                    raise TranzyAuthError(f"Authentication failed: {resp.status}")
                if resp.status != 200:
                    text = await resp.text()
                    raise TranzyApiError(f"API error {resp.status}: {text[:200]}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise TranzyConnectionError(f"Connection error: {err}") from err
        except asyncio.TimeoutError as err:
            raise TranzyConnectionError("Request timed out") from err

    def _is_cache_valid(self) -> bool:
        """Check if cached static data is still valid."""
        if self._cache_timestamp is None:
            return False
        return datetime.now() - self._cache_timestamp < self._cache_ttl

    async def _ensure_static_data(self) -> None:
        """Load and cache static GTFS data (routes, stops, trips, stop_times)."""
        if self._is_cache_valid():
            return

        _LOGGER.debug("Refreshing static GTFS data cache for agency %s", self._agency_id)

        # Fetch all static data in parallel
        routes_data, stops_data, trips_data, stop_times_data = await asyncio.gather(
            self._request("routes"),
            self._request("stops"),
            self._request("trips"),
            self._request("stop_times"),
        )

        # Index routes by route_id
        self._routes_cache = {}
        for route in routes_data:
            rid = str(route.get("route_id", ""))
            self._routes_cache[rid] = route

        # Index stops by stop_id
        self._stops_cache = {}
        for stop in stops_data:
            sid = str(stop.get("stop_id", ""))
            self._stops_cache[sid] = stop

        # Index trips by trip_id
        self._trips_cache = {}
        for trip in trips_data:
            tid = str(trip.get("trip_id", ""))
            self._trips_cache[tid] = trip

        # Index stop_times by stop_id (list of stop_times for each stop)
        self._stop_times_cache = {}
        for st in stop_times_data:
            sid = str(st.get("stop_id", ""))
            if sid not in self._stop_times_cache:
                self._stop_times_cache[sid] = []
            self._stop_times_cache[sid].append(st)

        self._cache_timestamp = datetime.now()
        _LOGGER.info(
            "Cached %d routes, %d stops, %d trips, %d stop_times for agency %s",
            len(self._routes_cache),
            len(self._stops_cache),
            len(self._trips_cache),
            sum(len(v) for v in self._stop_times_cache.values()),
            self._agency_id,
        )

    async def test_connection(self) -> bool:
        """Test if the API key and agency are valid."""
        try:
            routes = await self._request("routes")
            return isinstance(routes, list)
        except TranzyApiError:
            return False

    async def validate_stop(self, stop_id: str) -> dict | None:
        """Check if a stop_id exists and return its data."""
        await self._ensure_static_data()
        return self._stops_cache.get(str(stop_id))

    async def get_routes(self) -> dict[str, dict]:
        """Get all routes, indexed by route_id."""
        await self._ensure_static_data()
        return self._routes_cache or {}

    async def get_stops(self) -> dict[str, dict]:
        """Get all stops, indexed by stop_id."""
        await self._ensure_static_data()
        return self._stops_cache or {}

    async def get_vehicles(self) -> list[dict[str, Any]]:
        """Get real-time vehicle positions."""
        return await self._request("vehicles")

    def get_route_type_name(self, route_type: int | str) -> str:
        """Convert GTFS route_type to human-readable name."""
        try:
            rt = int(route_type)
        except (ValueError, TypeError):
            return "unknown"
        return GTFS_ROUTE_TYPES.get(rt, "unknown")

    async def get_arrivals_for_stop(
        self,
        stop_id: str,
        vehicle_type_filter: list[str] | None = None,
        max_arrivals: int = 5,
    ) -> list[dict[str, Any]]:
        """Get upcoming arrivals for a specific stop.

        This combines:
        1. Static schedule data (stop_times → trips → routes) to know which
           routes serve this stop
        2. Real-time vehicle positions to estimate actual arrival times

        Returns a list of arrival dicts:
        {
            "route_short_name": "1",
            "route_long_name": "Route 1 ...",
            "route_type": "tram",
            "trip_id": "...",
            "trip_headsign": "...",
            "vehicle_id": "...",
            "vehicle_label": "...",
            "eta_minutes": 5,
            "scheduled_arrival": "08:30:00",
            "is_realtime": True/False,
            "latitude": ...,
            "longitude": ...,
        }
        """
        await self._ensure_static_data()

        stop_id_str = str(stop_id)

        if not self._stop_times_cache or stop_id_str not in self._stop_times_cache:
            _LOGGER.warning("No stop_times data for stop %s", stop_id)
            return []

        # Build a set of (trip_id → route_id) for trips serving this stop
        # and their scheduled arrival times
        trip_route_map: dict[str, str] = {}
        trip_schedule: dict[str, str] = {}  # trip_id → scheduled arrival time
        trip_sequence: dict[str, int] = {}  # trip_id → stop_sequence at this stop

        for st in self._stop_times_cache.get(stop_id_str, []):
            tid = str(st.get("trip_id", ""))
            if tid and tid in (self._trips_cache or {}):
                trip = self._trips_cache[tid]
                route_id = str(trip.get("route_id", ""))
                trip_route_map[tid] = route_id
                trip_schedule[tid] = st.get("arrival_time", st.get("departure_time", ""))
                trip_sequence[tid] = int(st.get("stop_sequence", 0))

        # Get real-time vehicle data
        try:
            vehicles = await self.get_vehicles()
        except TranzyApiError as err:
            _LOGGER.warning("Failed to get real-time vehicles: %s", err)
            vehicles = []

        # Map vehicles by trip_id
        vehicle_by_trip: dict[str, dict] = {}
        for v in vehicles:
            vtid = str(v.get("trip_id", ""))
            if vtid in trip_route_map:
                vehicle_by_trip[vtid] = v

        now = datetime.now()
        arrivals: list[dict[str, Any]] = []

        # For each trip serving this stop, compute arrival info
        for trip_id, route_id in trip_route_map.items():
            route = (self._routes_cache or {}).get(route_id, {})
            trip = (self._trips_cache or {}).get(trip_id, {})

            route_type_num = route.get("route_type", 3)
            route_type_name = self.get_route_type_name(route_type_num)

            # Apply vehicle type filter
            if vehicle_type_filter and route_type_name not in vehicle_type_filter:
                continue

            route_short_name = route.get("route_short_name", "?")
            route_long_name = route.get("route_long_name", "")
            trip_headsign = trip.get("trip_headsign", route_long_name)

            scheduled_arrival = trip_schedule.get(trip_id, "")

            # Compute ETA
            eta_minutes: int | None = None
            is_realtime = False
            latitude = None
            longitude = None
            vehicle_id = None
            vehicle_label = None

            vehicle = vehicle_by_trip.get(trip_id)
            if vehicle:
                is_realtime = True
                latitude = vehicle.get("latitude") or vehicle.get("lat")
                longitude = vehicle.get("longitude") or vehicle.get("lng") or vehicle.get("lon")
                vehicle_id = vehicle.get("id") or vehicle.get("vehicle_id")
                vehicle_label = vehicle.get("label") or vehicle.get("vehicle_label", "")

                # Use vehicle timestamp to determine freshness
                v_timestamp = vehicle.get("timestamp")
                if v_timestamp:
                    try:
                        if isinstance(v_timestamp, (int, float)):
                            v_time = datetime.fromtimestamp(v_timestamp)
                        else:
                            v_time = datetime.fromisoformat(str(v_timestamp).replace("Z", "+00:00"))
                        # Only consider fresh data (< 5 min old)
                        if (now - v_time.replace(tzinfo=None)).total_seconds() > 300:
                            is_realtime = False
                    except (ValueError, TypeError, OSError):
                        pass

            # Compute ETA from scheduled arrival time
            if scheduled_arrival:
                try:
                    parts = scheduled_arrival.split(":")
                    h, m = int(parts[0]), int(parts[1])
                    # GTFS allows hours > 23 for next-day trips
                    sched_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=h, minutes=m)
                    diff = (sched_dt - now).total_seconds() / 60.0
                    if -5 <= diff <= 120:  # Show arrivals from 5 min ago to 2 hours ahead
                        eta_minutes = max(0, int(diff))
                    else:
                        continue  # Skip arrivals too far in the past/future
                except (ValueError, IndexError):
                    continue

            if eta_minutes is None:
                continue

            arrivals.append(
                {
                    "route_short_name": route_short_name,
                    "route_long_name": route_long_name,
                    "route_type": route_type_name,
                    "route_type_num": route_type_num,
                    "route_id": route_id,
                    "trip_id": trip_id,
                    "trip_headsign": trip_headsign,
                    "vehicle_id": vehicle_id,
                    "vehicle_label": vehicle_label,
                    "eta_minutes": eta_minutes,
                    "scheduled_arrival": scheduled_arrival,
                    "is_realtime": is_realtime,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

        # Sort by ETA and limit
        arrivals.sort(key=lambda a: a["eta_minutes"])
        return arrivals[:max_arrivals * 10]  # Return more for the card to group by route

    def invalidate_cache(self) -> None:
        """Force cache refresh on next request."""
        self._cache_timestamp = None
