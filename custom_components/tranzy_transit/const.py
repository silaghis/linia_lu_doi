"""Constants for the Tranzy Transit integration."""

DOMAIN = "tranzy_transit"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_AGENCY_ID = "agency_id"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_VEHICLE_TYPES = "vehicle_types"
CONF_MAX_ARRIVALS = "max_arrivals"

# Defaults
DEFAULT_SCAN_INTERVAL = 30  # seconds
DEFAULT_MAX_ARRIVALS = 5
DEFAULT_VEHICLE_TYPES = ["tram", "bus", "trolleybus"]

# API
API_BASE_URL = "https://api.tranzy.ai/v1/opendata"
API_HEADER_KEY = "X-API-KEY"
API_HEADER_AGENCY = "X-Agency-Id"

# GTFS route types (extended)
# https://gtfs.org/schedule/reference/#routestxt
GTFS_ROUTE_TYPES = {
    0: "tram",
    1: "metro",
    2: "rail",
    3: "bus",
    4: "ferry",
    5: "cable_tram",
    6: "gondola",
    7: "funicular",
    11: "trolleybus",
    12: "monorail",
    # Extended types
    100: "rail",
    200: "bus",
    400: "metro",
    700: "bus",
    800: "trolleybus",
    900: "tram",
}

VEHICLE_TYPE_NAMES = {
    "tram": "Tram",
    "bus": "Bus",
    "trolleybus": "Trolleybus",
    "metro": "Metro",
    "rail": "Rail",
    "ferry": "Ferry",
    "cable_tram": "Cable Tram",
    "gondola": "Gondola",
    "funicular": "Funicular",
    "monorail": "Monorail",
}

# Known agencies (can be extended)
KNOWN_AGENCIES = {
    "CTP Cluj": "CTP Cluj-Napoca",
    "SCTP Iasi": "SCTP Iași",
    "Eltrans Botosani": "Eltrans Botoșani",
    "RTEC Chisinau": "RTEC Chișinău",
    "STPT Timisoara": "STPT Timișoara",
    "Tursib Sibiu": "Tursib Sibiu",
    "OTL Oradea": "OTL Oradea",
    "CTP Arad": "CTP Arad",
}
