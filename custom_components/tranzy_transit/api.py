"""Tranzy API client v3 — hybrid schedule + real-time.

Actual API (agency_id=8, Timișoara):
────────────────────────────────────
GET /agency          → [{"agency_id": 8, "agency_name": "STPT Timisoara", ...}]
GET /routes          → [{"route_id": 1, "route_short_name": "1", "route_type": 0, ...}]
GET /trips           → [{"trip_id": "1_0", "route_id": 1, "trip_headsign": "...", ...}]
GET /stops           → [{"stop_id": 70, "stop_name": "...", "stop_lat": ..., ...}]
GET /stop_times      → [{"trip_id": "1_0", "stop_id": 74, "stop_sequence": 0,
                          "arrival_time": "05:30:00", "departure_time": "05:30:00", ...}]
                        ⚠ arrival_time may be absent in some records or at certain hours
GET /vehicles        → [{"id": 2, "label": "TDH", "latitude": 45.73, "longitude": 21.19,
                          "timestamp": "2026-02-16T18:43:17.000Z", "speed": 0,
                          "route_id": null, "trip_id": null, "vehicle_type": 3, ...}]

Auth: X-API-KEY header
Agency: X-Agency-Id header (numeric string, e.g. "8")

ETA strategy (same as station displays):
────────────────────────────────────────
1. Schedule-based: If stop_times has arrival_time → compute minutes until arrival
2. GPS-based: If a vehicle is on a trip serving our stop → estimate stops away
3. Combine: prefer schedule ETA, enhance with real-time vehicle info when available
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_util

from .const import API_BASE_URL, API_HEADER_AGENCY, API_HEADER_KEY, VEHICLE_TYPES

_LOGGER = logging.getLogger(__name__)


class TranzyApiError(Exception):
    """Base error."""

class TranzyAuthError(TranzyApiError):
    """403."""

class TranzyRateLimitError(TranzyApiError):
    """429."""

class TranzyConnectionError(TranzyApiError):
    """Network error."""


class TranzyApiClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        agency_id: int | str = 0,
        base_url: str = API_BASE_URL,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._agency_id = str(agency_id)
        self._base_url = base_url.rstrip("/")

        # Static GTFS caches
        self._routes: dict[int, dict] | None = None
        self._stops: dict[int, dict] | None = None
        self._trips: dict[str, dict] | None = None
        # stop_times indexed by stop_id → list of {trip_id, arrival_time, stop_sequence, ...}
        self._stop_times_by_stop: dict[int, list[dict]] | None = None
        # trip stop order: trip_id → [(stop_sequence, stop_id), ...] sorted
        self._trip_stop_order: dict[str, list[int]] | None = None
        # Reverse: which trips serve a stop? stop_id → {trip_id: seq_index}
        self._trips_for_stop: dict[int, dict[str, int]] | None = None
        self._cache_ts: datetime | None = None
        self._cache_ttl = timedelta(hours=4)

    # ── HTTP ─────────────────────────────────────────────────

    def _hdrs(self, agency: bool = True) -> dict[str, str]:
        h = {API_HEADER_KEY: self._api_key, "Accept": "application/json"}
        if agency:
            h[API_HEADER_AGENCY] = self._agency_id
        return h

    async def _get(self, ep: str, agency: bool = True) -> list[dict]:
        url = f"{self._base_url}/{ep}"
        try:
            async with self._session.get(
                url, headers=self._hdrs(agency), timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                if r.status == 403:
                    raise TranzyAuthError(f"403 on /{ep} (agency={self._agency_id})")
                if r.status == 429:
                    raise TranzyRateLimitError("429 rate limit")
                if r.status != 200:
                    t = await r.text()
                    raise TranzyApiError(f"{r.status} on /{ep}: {t[:200]}")
                d = await r.json()
                return d if isinstance(d, list) else []
        except aiohttp.ClientError as e:
            raise TranzyConnectionError(str(e)) from e
        except asyncio.TimeoutError as e:
            raise TranzyConnectionError("timeout") from e

    # ── Agency / test ────────────────────────────────────────

    async def get_agencies(self) -> list[dict]:
        return await self._get("agency", agency=False)

    async def test_api_key(self) -> bool:
        try:
            return len(await self.get_agencies()) > 0
        except TranzyApiError:
            return False

    async def test_agency(self) -> bool:
        try:
            return isinstance(await self._get("routes"), list)
        except (TranzyAuthError, TranzyApiError):
            return False

    # ── Static data ──────────────────────────────────────────

    def _cache_ok(self) -> bool:
        return self._cache_ts is not None and (dt_util.utcnow() - self._cache_ts) < self._cache_ttl

    async def ensure_static(self) -> None:
        if self._cache_ok():
            return

        _LOGGER.info("Loading GTFS static data for agency %s...", self._agency_id)
        routes_r, stops_r, trips_r, st_r = await asyncio.gather(
            self._get("routes"), self._get("stops"),
            self._get("trips"), self._get("stop_times"),
        )

        self._routes = {int(r["route_id"]): r for r in routes_r if "route_id" in r}
        self._stops = {int(s["stop_id"]): s for s in stops_r if "stop_id" in s}
        self._trips = {str(t["trip_id"]): t for t in trips_r if "trip_id" in t}

        # Index stop_times by stop_id
        self._stop_times_by_stop = {}
        trip_stops_raw: dict[str, list[tuple[int, int]]] = {}

        for st in st_r:
            tid = str(st.get("trip_id", ""))
            sid = st.get("stop_id")
            seq = st.get("stop_sequence", 0)
            if not tid or sid is None:
                continue
            sid = int(sid)

            if sid not in self._stop_times_by_stop:
                self._stop_times_by_stop[sid] = []
            self._stop_times_by_stop[sid].append(st)

            if tid not in trip_stops_raw:
                trip_stops_raw[tid] = []
            trip_stops_raw[tid].append((int(seq), sid))

        # Build ordered stop lists per trip
        self._trip_stop_order = {}
        for tid, pairs in trip_stops_raw.items():
            pairs.sort()
            self._trip_stop_order[tid] = [sid for _, sid in pairs]

        # Reverse index: stop_id → {trip_id: index_in_sequence}
        self._trips_for_stop = {}
        for tid, stop_list in self._trip_stop_order.items():
            for idx, sid in enumerate(stop_list):
                if sid not in self._trips_for_stop:
                    self._trips_for_stop[sid] = {}
                self._trips_for_stop[sid][tid] = idx

        _LOGGER.info(
            "Loaded: %d routes, %d stops, %d trips, %d stop_times records",
            len(self._routes), len(self._stops), len(self._trips),
            sum(len(v) for v in self._stop_times_by_stop.values()),
        )
        self._cache_ts = dt_util.utcnow()

    async def validate_stop(self, stop_id: int) -> dict | None:
        await self.ensure_static()
        return (self._stops or {}).get(stop_id)

    # ── Vehicles ─────────────────────────────────────────────

    async def get_vehicles(self) -> list[dict]:
        return await self._get("vehicles")

    # ── Arrivals ─────────────────────────────────────────────

    async def get_arrivals(
        self,
        stop_id: int,
        vehicle_type_filter: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Compute arrivals for a stop using both schedule and real-time data.

        Returns a list of dicts sorted by ETA (or stops_away if no ETA).
        """
        await self.ensure_static()

        # All stop_times records for our stop
        our_stop_times = (self._stop_times_by_stop or {}).get(stop_id, [])
        if not our_stop_times:
            return []

        # Which trips serve this stop?
        serving_trips = (self._trips_for_stop or {}).get(stop_id, {})

        # Which route_ids serve this stop?
        serving_route_ids: set[int] = set()
        for tid in serving_trips:
            trip = (self._trips or {}).get(tid, {})
            rid = trip.get("route_id")
            if rid is not None:
                serving_route_ids.add(int(rid))

        # ── Schedule-based arrivals ──────────────────────────
        now = dt_util.now()  # timezone-aware in HA’s configured timezone
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        schedule_arrivals: dict[str, dict] = {}  # keyed by trip_id

        for st in our_stop_times:
            tid = str(st.get("trip_id", ""))
            if not tid or tid not in (self._trips or {}):
                continue

            trip = self._trips[tid]
            rid = trip.get("route_id")
            route = (self._routes or {}).get(int(rid) if rid is not None else -1, {})

            route_type = route.get("route_type", 3)
            if vehicle_type_filter is not None and int(route_type) not in vehicle_type_filter:
                continue

            # Try to compute ETA from arrival_time
            arr_time_str = st.get("arrival_time") or st.get("departure_time")
            eta_minutes: int | None = None

            if arr_time_str and isinstance(arr_time_str, str) and ":" in arr_time_str:
                try:
                    parts = arr_time_str.split(":")
                    h = int(parts[0])
                    m = int(parts[1])
                    s = int(parts[2]) if len(parts) > 2 else 0

                    # GTFS can use 24+ hours for after-midnight service
                    days, h = divmod(h, 24)

                    sched = midnight + timedelta(days=days, hours=h, minutes=m, seconds=s)

                    diff = (sched - now).total_seconds() / 60.0

                    # Keep “next” arrivals; widen slightly so you don’t drop edge cases
                    if -5 <= diff <= 1440:   # DEBUG: this should be 240 for usual use
                        eta_minutes = max(0, int(round(diff)))
                    else:
                        continue
                except (ValueError, IndexError):
                    pass

            # Stops away as fallback
            our_seq_idx = serving_trips.get(tid)

            schedule_arrivals[tid] = {
                "trip_id": tid,
                "route_short_name": str(route.get("route_short_name", "?")),
                "route_long_name": route.get("route_long_name", ""),
                "route_id": route.get("route_id"),
                "route_type": int(route_type) if route_type is not None else 3,
                "route_type_name": VEHICLE_TYPES.get(int(route_type) if route_type is not None else 3, "Unknown"),
                "trip_headsign": trip.get("trip_headsign", ""),
                "eta_minutes": eta_minutes,
                "scheduled_time": arr_time_str or "",
                "our_seq_idx": our_seq_idx,
                # Will be enriched with vehicle data below
                "vehicle_label": "",
                "vehicle_id": None,
                "latitude": None,
                "longitude": None,
                "speed": None,
                "stops_away": None,
                "is_realtime": False,
                "timestamp": "",
                "wheelchair": "",
                "bike": "",
            }

        # ── Real-time vehicle enrichment ─────────────────────
        try:
            vehicles = await self.get_vehicles()
        except TranzyApiError as err:
            _LOGGER.warning("Vehicle fetch failed: %s", err)
            vehicles = []

        now_utc = dt_util.utcnow()

        for v in vehicles:
            v_type = v.get("vehicle_type")
            if vehicle_type_filter is not None and v_type not in vehicle_type_filter:
                continue

            v_trip_id = v.get("trip_id")
            v_route_id = v.get("route_id")

            # Check freshness (ISO: 2026-02-16T18:43:17.000Z)
            v_ts_str = v.get("timestamp", "")
            is_fresh = False
            if v_ts_str:
                try:
                    vt = datetime.fromisoformat(v_ts_str.replace("Z", "+00:00"))
                    is_fresh = (now_utc - vt).total_seconds() < 600
                except (ValueError, TypeError):
                    pass
            if not is_fresh:
                continue

            # Case 1: Vehicle has trip_id matching a serving trip
            if v_trip_id and str(v_trip_id) in schedule_arrivals:
                tid = str(v_trip_id)
                a = schedule_arrivals[tid]
                trip_stops = (self._trip_stop_order or {}).get(tid, [])
                v_seq = self._estimate_seq(v.get("latitude"), v.get("longitude"), trip_stops)

                our_idx = a["our_seq_idx"]
                stops_away = (our_idx - v_seq) if our_idx is not None and v_seq is not None else None
                if stops_away is not None and stops_away < -1:
                    # Already well past our stop — but keep schedule entry if ETA is valid
                    if a["eta_minutes"] is None:
                        continue
                    stops_away = None  # don't show negative stops_away

                a["vehicle_label"] = v.get("label", "")
                a["vehicle_id"] = v.get("id")
                a["latitude"] = v.get("latitude")
                a["longitude"] = v.get("longitude")
                a["speed"] = v.get("speed", 0)
                a["stops_away"] = max(0, stops_away) if stops_away is not None else None
                a["is_realtime"] = True
                a["timestamp"] = v_ts_str
                a["wheelchair"] = v.get("wheelchair_accessible", "")
                a["bike"] = v.get("bike_accessible", "")

            # Case 2: Vehicle on a serving route but no trip_id — add as extra
            elif (v_route_id is not None and int(v_route_id) in serving_route_ids
                  and not v_trip_id):
                rid = int(v_route_id)
                route = (self._routes or {}).get(rid, {})
                rt = route.get("route_type", v_type or 3)

                extra_key = f"_vehicle_{v.get('id', '')}"
                if extra_key not in schedule_arrivals:
                    schedule_arrivals[extra_key] = {
                        "trip_id": "",
                        "route_short_name": str(route.get("route_short_name", "?")),
                        "route_long_name": route.get("route_long_name", ""),
                        "route_id": rid,
                        "route_type": int(rt),
                        "route_type_name": VEHICLE_TYPES.get(int(rt), "Unknown"),
                        "trip_headsign": "",
                        "eta_minutes": None,
                        "scheduled_time": "",
                        "our_seq_idx": None,
                        "vehicle_label": v.get("label", ""),
                        "vehicle_id": v.get("id"),
                        "latitude": v.get("latitude"),
                        "longitude": v.get("longitude"),
                        "speed": v.get("speed", 0),
                        "stops_away": None,
                        "is_realtime": True,
                        "timestamp": v_ts_str,
                        "wheelchair": v.get("wheelchair_accessible", ""),
                        "bike": v.get("bike_accessible", ""),
                    }

        # ── Sort and return ──────────────────────────────────
        result = list(schedule_arrivals.values())

        # Sort: ETA first (if available), then stops_away, then the rest
        def sort_key(a):
            eta = a.get("eta_minutes")
            sa = a.get("stops_away")
            rt = a.get("is_realtime", False)
            if eta is not None:
                return (0, eta, 0)            # Best: have schedule ETA
            if sa is not None:
                return (1, sa, 0)             # Next: have stops_away from GPS
            if rt:
                return (2, 0, 0)              # Then: on-route but unknown position
            return (3, 999, 0)                # Last: schedule-only, no time

        result.sort(key=sort_key)

        # Filter: only keep entries that have either an ETA, stops_away, or real-time data
        result = [a for a in result if a["eta_minutes"] is not None or a["stops_away"] is not None or a["is_realtime"]]

        return result

    def _estimate_seq(self, lat: float | None, lon: float | None, trip_stops: list[int]) -> int | None:
        """Estimate which stop index in the trip the vehicle is nearest to."""
        if not lat or not lon or not trip_stops or not self._stops:
            return None
        best_idx, best_d = 0, float("inf")
        for idx, sid in enumerate(trip_stops):
            s = self._stops.get(sid, {})
            slat = s.get("stop_lat")
            slon = s.get("stop_lon", s.get("stop_lng"))
            if slat is None or slon is None:
                continue
            d = (lat - float(slat)) ** 2 + (lon - float(slon)) ** 2
            if d < best_d:
                best_d = d
                best_idx = idx
        return best_idx

    def invalidate_cache(self) -> None:
        self._cache_ts = None
