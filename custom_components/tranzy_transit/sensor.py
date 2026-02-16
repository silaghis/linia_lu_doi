"""Sensor platform for Tranzy Transit."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AGENCY_ID,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
    VEHICLE_TYPE_NAMES,
)
from .coordinator import TranzyTransitCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tranzy Transit sensors from a config entry."""
    coordinator: TranzyTransitCoordinator = hass.data[DOMAIN][entry.entry_id]

    stop_id = entry.data[CONF_STOP_ID]
    stop_name = entry.data.get(CONF_STOP_NAME, f"Stop {stop_id}")
    agency_id = entry.data[CONF_AGENCY_ID]

    entities: list[SensorEntity] = [
        TranzyNextArrivalSensor(coordinator, entry, stop_id, stop_name, agency_id),
        TranzyArrivalCountSensor(coordinator, entry, stop_id, stop_name, agency_id),
    ]

    async_add_entities(entities, update_before_add=True)


class TranzyBaseSensor(CoordinatorEntity[TranzyTransitCoordinator], SensorEntity):
    """Base class for Tranzy Transit sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TranzyTransitCoordinator,
        entry: ConfigEntry,
        stop_id: str,
        stop_name: str,
        agency_id: str,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._stop_id = stop_id
        self._stop_name = stop_name
        self._agency_id = agency_id
        self._attr_unique_id = f"{DOMAIN}_{agency_id}_{stop_id}_{sensor_type}"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._agency_id}_{self._stop_id}")},
            name=f"Tranzy {self._stop_name}",
            manufacturer="Tranzy.ai",
            model=f"Transit Stop ({self._agency_id})",
            sw_version="1.0.0",
        )


class TranzyNextArrivalSensor(TranzyBaseSensor):
    """Sensor showing the next arrival at the stop.

    The state is the ETA in minutes of the soonest vehicle.
    Attributes contain the full arrivals list for the Lovelace card.
    """

    _attr_icon = "mdi:bus-clock"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TranzyTransitCoordinator,
        entry: ConfigEntry,
        stop_id: str,
        stop_name: str,
        agency_id: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry, stop_id, stop_name, agency_id, "next_arrival")
        self._attr_name = "Next Arrival"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        """Return the ETA of the next arrival in minutes."""
        if not self.coordinator.data:
            return None
        arrivals = self.coordinator.data.get("arrivals", [])
        if arrivals:
            return arrivals[0].get("eta_minutes")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes with full arrival data."""
        if not self.coordinator.data:
            return {}

        data = self.coordinator.data
        arrivals = data.get("arrivals", [])
        by_route = data.get("arrivals_by_route", {})

        # Build a clean arrivals list for the Lovelace card
        arrivals_attr = []
        for a in arrivals:
            arrivals_attr.append(
                {
                    "route": a["route_short_name"],
                    "destination": a["trip_headsign"],
                    "eta_minutes": a["eta_minutes"],
                    "type": VEHICLE_TYPE_NAMES.get(a["route_type"], a["route_type"]),
                    "scheduled": a["scheduled_arrival"],
                    "realtime": a["is_realtime"],
                    "vehicle_label": a.get("vehicle_label", ""),
                }
            )

        # Build per-route summary
        routes_summary = {}
        for route_name, route_arrivals in by_route.items():
            if route_arrivals:
                routes_summary[route_name] = {
                    "next_eta": route_arrivals[0]["eta_minutes"],
                    "type": VEHICLE_TYPE_NAMES.get(
                        route_arrivals[0]["route_type"],
                        route_arrivals[0]["route_type"],
                    ),
                    "destination": route_arrivals[0]["trip_headsign"],
                    "count": len(route_arrivals),
                    "etas": [a["eta_minutes"] for a in route_arrivals],
                }

        return {
            "stop_id": self._stop_id,
            "stop_name": self._stop_name,
            "agency": self._agency_id,
            "arrivals": arrivals_attr,
            "routes": routes_summary,
            "route_names": data.get("route_names", []),
            "total_arrivals": data.get("total_arrivals", 0),
        }


class TranzyArrivalCountSensor(TranzyBaseSensor):
    """Sensor showing total number of upcoming arrivals."""

    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "arrivals"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TranzyTransitCoordinator,
        entry: ConfigEntry,
        stop_id: str,
        stop_name: str,
        agency_id: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry, stop_id, stop_name, agency_id, "arrival_count")
        self._attr_name = "Upcoming Arrivals"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        """Return the total number of upcoming arrivals."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("total_arrivals", 0)
