"""Sensor platform for Tranzy Transit v3."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_AGENCY_ID, CONF_STOP_ID, CONF_STOP_NAME, DOMAIN, VEHICLE_TYPES
from .coordinator import TranzyTransitCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TranzyTransitCoordinator = hass.data[DOMAIN][entry.entry_id]
    sid = entry.data[CONF_STOP_ID]
    sname = entry.data.get(CONF_STOP_NAME, f"Stop {sid}")
    aid = entry.data[CONF_AGENCY_ID]
    async_add_entities([
        TranzyNextSensor(coordinator, entry, sid, sname, aid),
        TranzyCountSensor(coordinator, entry, sid, sname, aid),
    ], update_before_add=True)


class _Base(CoordinatorEntity[TranzyTransitCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, stop_id, stop_name, agency_id, suffix):
        super().__init__(coordinator)
        self._stop_id = stop_id
        self._stop_name = stop_name
        self._agency_id = agency_id
        self._attr_unique_id = f"{DOMAIN}_{agency_id}_{stop_id}_{suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._agency_id}_{self._stop_id}")},
            name=f"Tranzy {self._stop_name}",
            manufacturer="Tranzy.ai",
            model=f"Transit Stop (Agency {self._agency_id})",
        )


class TranzyNextSensor(_Base):
    """Next arrival — state is ETA in minutes (or stops away as fallback).

    The full arrivals list is in attributes for the Lovelace card.
    """
    _attr_icon = "mdi:tram"
    _attr_name = "Next Arrival"

    def __init__(self, coordinator, entry, sid, sname, aid):
        super().__init__(coordinator, entry, sid, sname, aid, "next")

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | str | None:
        if not self.coordinator.data:
            return None
        arr = self.coordinator.data.get("arrivals", [])
        if not arr:
            return None
        first = arr[0]
        eta = first.get("eta_minutes")
        if eta is not None:
            return eta
        sa = first.get("stops_away")
        if sa is not None:
            return sa
        return "approaching"

    @property
    def native_unit_of_measurement(self) -> str | None:
        if not self.coordinator.data:
            return None
        arr = self.coordinator.data.get("arrivals", [])
        if not arr:
            return None
        first = arr[0]
        if first.get("eta_minutes") is not None:
            return "min"
        if first.get("stops_away") is not None:
            return "stops"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        data = self.coordinator.data

        arrivals_attr = []
        for a in data.get("arrivals", []):
            arrivals_attr.append({
                "route": a["route_short_name"],
                "destination": a.get("trip_headsign", ""),
                "type": a.get("route_type_name", ""),
                "eta_minutes": a.get("eta_minutes"),
                "scheduled_time": a.get("scheduled_time", ""),
                "stops_away": a.get("stops_away"),
                "vehicle_label": a.get("vehicle_label", ""),
                "speed": a.get("speed"),
                "realtime": a.get("is_realtime", False),
                "latitude": a.get("latitude"),
                "longitude": a.get("longitude"),
                "timestamp": a.get("timestamp", ""),
            })

        routes_summary = {}
        for rn, ra in data.get("arrivals_by_route", {}).items():
            if ra:
                first = ra[0]
                routes_summary[rn] = {
                    "next_eta": first.get("eta_minutes"),
                    "next_stops_away": first.get("stops_away"),
                    "type": first.get("route_type_name", ""),
                    "destination": first.get("trip_headsign", ""),
                    "vehicle_count": len(ra),
                }

        return {
            "stop_id": self._stop_id,
            "stop_name": self._stop_name,
            "agency_id": self._agency_id,
            "arrivals": arrivals_attr,
            "routes": routes_summary,
            "route_names": data.get("route_names", []),
            "total_vehicles": data.get("total_vehicles", 0),
        }


class TranzyCountSensor(_Base):
    _attr_icon = "mdi:counter"
    _attr_name = "Approaching Vehicles"
    _attr_native_unit_of_measurement = "vehicles"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, sid, sname, aid):
        super().__init__(coordinator, entry, sid, sname, aid, "count")

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("total_vehicles", 0)
