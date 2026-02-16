"""Constants for the Tranzy Transit integration."""

DOMAIN = "tranzy_transit"

# Configuration
CONF_API_KEY = "api_key"
CONF_AGENCY_ID = "agency_id"        # Numeric, e.g. 8 for STPT Timișoara
CONF_AGENCY_NAME = "agency_name"
CONF_STOP_ID = "stop_id"            # Numeric, e.g. 70
CONF_STOP_NAME = "stop_name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_VEHICLE_TYPES = "vehicle_types"
CONF_MAX_ARRIVALS = "max_arrivals"

# Defaults
DEFAULT_SCAN_INTERVAL = 30  # seconds
DEFAULT_MAX_ARRIVALS = 10
DEFAULT_VEHICLE_TYPES = [0]  # 0 = Tram by default

# API - confirmed from actual docs
API_BASE_URL = "https://api.tranzy.ai/v1/opendata"
API_HEADER_KEY = "X-API-KEY"
API_HEADER_AGENCY = "X-Agency-Id"

# GTFS vehicle_type values (from the Vehicles endpoint schema)
VEHICLE_TYPES = {
    0: "Tram",
    1: "Metro",
    2: "Rail",
    3: "Bus",
    4: "Ferry",
    5: "Cable Tram",
    6: "Aerial Lift",
    7: "Funicular",
    11: "Trolleybus",
    12: "Monorail",
}

VEHICLE_TYPE_ICONS = {
    0: "mdi:tram",
    1: "mdi:subway",
    2: "mdi:train",
    3: "mdi:bus",
    4: "mdi:ferry",
    5: "mdi:gondola",
    6: "mdi:gondola",
    7: "mdi:elevator",
    11: "mdi:bus-electric",
    12: "mdi:train",
}
