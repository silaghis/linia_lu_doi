# Tranzy Transit — Home Assistant Integration & CLI Tools

Real-time public transit arrivals (trams, buses, trolleybuses) for Romanian and Moldovan cities, powered by the [Tranzy OpenData API](https://api.tranzy.ai/v1/opendata/docs#/).

Works as both a **standalone CLI tool** (query from terminal) and a **Home Assistant custom integration** with a Lovelace dashboard card.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start — Terminal Usage](#quick-start--terminal-usage)
- [Home Assistant Integration](#home-assistant-integration)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Lovelace Card Setup](#lovelace-card-setup)
  - [Card Configuration Options](#card-configuration-options)
- [API Reference](#api-reference)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### 1. Get a Tranzy API Key

1. Go to [apps.tranzy.ai/accounts](https://apps.tranzy.ai/accounts)
2. Create an account
3. Create a new application — **you must select the specific agency** (city) you want data for
4. Copy the API key (this is your `X-API-KEY`)

**Important:** Each API key is tied to one agency. If you want data for both Timișoara and Cluj, you need two separate apps/keys.

### 2. Find Your Agency ID

The agency ID is a **number** (not a name). Use the `/agency` endpoint to discover it — see the terminal examples below. Known agencies:

| agency_id | agency_name       | City          | Country  |
|-----------|-------------------|---------------|----------|
| 8         | STPT Timisoara    | Timișoara     | Romania  |
| *varies*  | CTP Cluj          | Cluj-Napoca   | Romania  |
| *varies*  | SCTP Iasi         | Iași          | Romania  |
| *varies*  | Eltrans Botosani  | Botoșani      | Romania  |
| *varies*  | RTEC Chisinau     | Chișinău      | Moldova  |

Run `--agencies` (see below) to get the current list for your API key.

### 3. Find Your Stop ID

The stop ID is also a **number**. Use the helper script or curl to find it — see below.

---

## Quick Start — Terminal Usage

The `tools/find_stops.py` script lets you explore the API from your terminal without Home Assistant. It requires only Python 3 (no extra packages).

### Setup

```bash
# Set your API key as an environment variable
export TRANZY_API_KEY=your_api_key_here

# Or pass it inline with --api-key
python tools/find_stops.py --api-key YOUR_KEY ...
```

### Show upcoming arrivals at a stop (the main command)

This is likely what you want — it shows what's coming to your stop, just like the station display:

```bash
# All vehicle types at stop 70
python tools/find_stops.py --agency 8 --arrivals 70

# Only trams (vehicle_type 0)
python tools/find_stops.py --agency 8 --arrivals 70 --type 0

# Auto-refresh every 30 seconds (like a live display)
python tools/find_stops.py --agency 8 --arrivals 70 --type 0 --watch
```

Output:
```
  ╔══════════════════════════════════════════════════════════╗
  ║  🚏  Piata Libertății                                   ║
  ║  Stop 70 · Tram                                         ║
  ╠══════════════════════════════════════════════════════════╣
  ║  🚋    1  → Calea Aradului                       3 min  ║
  ║         veh:V42 · sched:08:45 · 22km/h · 🟢 LIVE       ║
  ║  🚋    4  → Gara de Nord                         7 min  ║
  ║         veh:V18 · sched:08:49 · 🟢 LIVE                ║
  ║  🚋    8  → Calea Torontalului                  12 min  ║
  ║         sched:08:54                                      ║
  ╚══════════════════════════════════════════════════════════╝
  Updated: 08:42:15
```

Each arrival shows:
- **ETA in minutes** (from scheduled `arrival_time`, when available)
- **Stops away** (from live GPS, when no schedule time)
- **Vehicle label**, **speed**, and **🟢 LIVE** indicator when GPS-tracked
- **Scheduled time** if present in the data

The `--watch` flag clears the screen and refreshes every 30 seconds — leave it running in a terminal for a live departure board.

Vehicle type codes: `0`=Tram, `3`=Bus, `11`=Trolleybus, `1`=Metro, `2`=Rail.

### Discovery commands

```bash
# List agencies available for your key
python tools/find_stops.py --agencies
#   ID=  8  STPT Timisoara       https://www.ratt.ro/

# List all routes for an agency
python tools/find_stops.py --agency 8 --routes
#   ID       Name     Type         Long Name
#   1        1        Tram         Calea Aradului - ...
#   154      E1       Bus          ...

# Search stops by name
python tools/find_stops.py --agency 8 --search "Piata"
#   ID       Name                            Lat          Lon
#   70       Piata Libertății (Centru)        45.7553      21.2289

# List all stops
python tools/find_stops.py --agency 8 --list-all

# Full details for a stop (info + which routes serve it)
python tools/find_stops.py --agency 8 --stop-id 70
#   🚋    1 (Tram) — Calea Aradului - ...
#   🚋    2 (Tram) — ...
#   🚋    8 (Tram) — ...
```

### Using curl directly

If you prefer raw API calls:

```bash
# List agencies (only needs X-API-KEY)
curl -s -H "X-API-KEY: $TRANZY_API_KEY" \
  https://api.tranzy.ai/v1/opendata/agency | python3 -m json.tool

# List stops (needs X-API-KEY + X-Agency-Id)
curl -s -H "X-API-KEY: $TRANZY_API_KEY" -H "X-Agency-Id: 8" \
  https://api.tranzy.ai/v1/opendata/stops | python3 -m json.tool

# Get real-time vehicle positions
curl -s -H "X-API-KEY: $TRANZY_API_KEY" -H "X-Agency-Id: 8" \
  https://api.tranzy.ai/v1/opendata/vehicles | python3 -m json.tool

# Get scheduled stop times
curl -s -H "X-API-KEY: $TRANZY_API_KEY" -H "X-Agency-Id: 8" \
  https://api.tranzy.ai/v1/opendata/stop_times | python3 -m json.tool
```

---

## Home Assistant Integration

### Installation

#### Via HACS (Recommended)

1. In Home Assistant, go to **HACS** → three-dot menu → **Custom repositories**
2. Add the repository URL (e.g., `https://github.com/YOUR_USER/ha-tranzy-transit`)
3. Category: **Integration**
4. Click **Add**, then find "Tranzy Transit" and click **Install**
5. **Restart Home Assistant**

#### Manual Installation

1. Copy the entire `custom_components/tranzy_transit/` folder into your Home Assistant `config/custom_components/` directory:

```bash
# If your HA config is at /config (typical Docker setup)
cp -r custom_components/tranzy_transit /config/custom_components/

# Also copy the Lovelace card JS
mkdir -p /config/www
cp custom_components/tranzy_transit/www/tranzy-transit-card.js /config/www/
```

2. **Restart Home Assistant**

### Configuration

#### Via the UI (Config Flow)

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Tranzy Transit"**
3. Fill in:
   - **API Key** — your key from apps.tranzy.ai
   - **Agency ID** — numeric (e.g., `8` for Timișoara)
   - **Stop ID** — numeric (e.g., `70`)
   - **Stop Name** — optional friendly name (auto-detected if left empty)
   - **Update interval** — how often to poll, in seconds (default: 30, minimum: 10)
   - **Vehicle types** — which types to track: `0`=Tram, `3`=Bus, `11`=Trolleybus, etc.
4. Click **Submit**

You can add multiple stops — just repeat the process with a different stop ID.

#### Changing Options After Setup

Go to **Settings** → **Devices & Services** → **Tranzy Transit** → **Configure** to change:
- Poll interval
- Vehicle type filter
- Max arrivals shown

### Lovelace Card Setup

#### Step 1: Register the card resource

Go to **Settings** → **Dashboards** → three-dot menu → **Resources** → **Add Resource**:

- **URL**: `/local/tranzy-transit-card.js` (manual install) or `/local/community/tranzy_transit/tranzy-transit-card.js` (HACS)
- **Type**: JavaScript Module

Or add to `configuration.yaml`:

```yaml
lovelace:
  resources:
    - url: /local/tranzy-transit-card.js
      type: module
```

#### Step 2: Add the card to your dashboard

Edit your dashboard → **Add Card** → scroll to bottom → **Manual Card**, then paste:

```yaml
type: custom:tranzy-transit-card
entity: sensor.tranzy_8_70_next
title: Tram Arrivals
show_route_filter: true
max_rows: 10
compact: false
```

The entity name follows the pattern `sensor.tranzy_{agency_id}_{stop_id}_next`. Check **Developer Tools** → **States** to find the exact entity ID.

### Card Configuration Options

| Option             | Type    | Default            | Description                              |
|--------------------|---------|--------------------|------------------------------------------|
| `entity`           | string  | *(required)*       | Entity ID of the "Next Arrival" sensor   |
| `title`            | string  | "Transit Arrivals" | Card title                               |
| `show_route_filter`| boolean | `true`             | Show clickable route filter chips        |
| `routes_filter`    | list    | `[]`               | Pre-select specific routes (empty = all) |
| `max_rows`         | integer | `10`               | Maximum rows to display                  |
| `compact`          | boolean | `false`            | Compact display mode                     |

### Sensors Created

For each configured stop, two sensors are created:

**`sensor.tranzy_{agency}_{stop}_next`**
- **State**: ETA in minutes of the nearest vehicle (when schedule data is available), or number of stops away (GPS fallback)
- **Unit**: `min` or `stops` depending on data availability
- **Attributes**:
  - `arrivals` — full list of approaching vehicles, each with:
    - `route` — line number (e.g., "1", "8")
    - `destination` — trip headsign / direction
    - `type` — "Tram", "Bus", "Trolleybus", etc.
    - `eta_minutes` — minutes until arrival (from schedule, `null` if unavailable)
    - `scheduled_time` — raw scheduled time (e.g., "08:45:00")
    - `stops_away` — GPS-estimated stops until arrival (`null` if unavailable)
    - `vehicle_label` — vehicle identifier
    - `speed` — current speed in km/h
    - `realtime` — `true` if live GPS data is available for this vehicle
    - `latitude`, `longitude` — vehicle position
    - `timestamp` — last GPS update time
  - `routes` — per-route summary
  - `route_names` — list of route numbers serving this stop
  - `stop_name`, `stop_id`, `agency_id`

**`sensor.tranzy_{agency}_{stop}_count`**
- **State**: total number of approaching vehicles

---

## API Reference

Base URL: `https://api.tranzy.ai/v1/opendata`

All requests require the `X-API-KEY` header. Proxy endpoints (everything except `/agency`) also require `X-Agency-Id`.

| Endpoint         | Headers Needed              | Returns                          | Cached |
|------------------|-----------------------------|----------------------------------|--------|
| `GET /agency`    | `X-API-KEY`                 | List of agencies                 | 4 hrs  |
| `GET /routes`    | `X-API-KEY` + `X-Agency-Id` | Routes (id, name, type)          | 4 hrs  |
| `GET /stops`     | `X-API-KEY` + `X-Agency-Id` | Stops (id, name, lat, lon)       | 4 hrs  |
| `GET /trips`     | `X-API-KEY` + `X-Agency-Id` | Trips (id, route_id, headsign)   | 4 hrs  |
| `GET /stop_times`| `X-API-KEY` + `X-Agency-Id` | Stop times (trip, stop, sequence, arrival_time) | 4 hrs |
| `GET /vehicles`  | `X-API-KEY` + `X-Agency-Id` | Live vehicle positions           | Every poll |
| `GET /shapes`    | `X-API-KEY` + `X-Agency-Id` | Route geometry                   | Not used |

Response codes: `200` OK, `403` invalid key or wrong agency, `429` rate limit, `500` server error.

### Vehicle Types (GTFS `route_type` / `vehicle_type`)

| Code | Type          |
|------|---------------|
| 0    | Tram          |
| 1    | Metro         |
| 2    | Rail          |
| 3    | Bus           |
| 4    | Ferry         |
| 5    | Cable Tram    |
| 6    | Aerial Lift   |
| 7    | Funicular     |
| 11   | Trolleybus    |
| 12   | Monorail      |

---

## How It Works

The integration combines two data sources to estimate when a vehicle will arrive at your stop:

### 1. Schedule-based ETA (primary)

`stop_times` contains `arrival_time` for each trip at each stop (e.g., `"08:45:00"`). When present, the integration computes:

```
eta_minutes = scheduled_arrival_time - current_time
```

This is the same approach the station displays use.

### 2. GPS-based estimation (fallback / enrichment)

When a vehicle is actively tracked (`trip_id` is not null in `/vehicles`), we:

1. Look up the trip's stop sequence from `stop_times`
2. Find the vehicle's nearest stop using GPS coordinates
3. Calculate how many stops remain before our stop

This gives a `stops_away` value even when `arrival_time` is missing from the schedule.

### 3. Combined display

The card shows whichever is available, preferring minutes:

- **"5 min"** — schedule-based ETA (green/orange/red by urgency)
- **"3 stops"** — GPS-based distance (when no schedule time)
- **"on route"** — vehicle is active on a serving route but position is unclear
- Green pulse dot (🟢) — indicates live GPS data is available

### Data refresh

- Static data (routes, stops, trips, stop_times) is cached for **4 hours**
- Vehicle positions are fetched fresh on every poll cycle (default: every **30 seconds**)

---

## Project Structure

```
tranzy-ha-integration/
├── .env                        # Environment variables template
├── .gitignore
├── LICENSE
├── README.md
├── hacs.json                   # HACS metadata
│
├── tools/
│   └── find_stops.py           # Standalone CLI tool (no dependencies)
│
└── custom_components/
    └── tranzy_transit/
        ├── __init__.py         # HA integration entry point
        ├── api.py              # Tranzy API client (async, with caching)
        ├── config_flow.py      # UI setup wizard
        ├── const.py            # Constants, vehicle types, API config
        ├── coordinator.py      # DataUpdateCoordinator (polling loop)
        ├── manifest.json       # HA integration metadata
        ├── sensor.py           # Sensor entities (next arrival, count)
        ├── strings.json        # UI strings
        ├── translations/
        │   └── en.json         # English translations
        └── www/
            └── tranzy-transit-card.js  # Custom Lovelace card
```

---

## Troubleshooting

### "403 Forbidden" from the API

This is the most common issue. It means one of:

1. **Wrong API key** — double-check it at [apps.tranzy.ai/accounts](https://apps.tranzy.ai/accounts)
2. **Key created for a different agency** — each key is bound to one agency. If your key is for Cluj but you're querying with `X-Agency-Id: 8` (Timișoara), you get 403. Create a new app for the right agency.
3. **Misformatted Agency ID** — it must be a number (e.g., `8`), not a string like `"STPT Timisoara"` or `"stpt_tm_ro"`

Quick test:

```bash
# Test 1: Does the key work at all? (/agency doesn't need X-Agency-Id)
curl -s -H "X-API-KEY: $TRANZY_API_KEY" \
  https://api.tranzy.ai/v1/opendata/agency

# Test 2: Does the agency ID work?
curl -s -H "X-API-KEY: $TRANZY_API_KEY" \
  -H "X-Agency-Id: 8" \
  https://api.tranzy.ai/v1/opendata/routes
```

If test 1 works but test 2 gives 403 → your key is for a different agency.

### No arrivals showing in the card

- **Outside service hours** — trams/buses don't run 24/7. During late night hours, the API returns vehicles with `trip_id: null` (parked at depot), which the integration correctly ignores.
- **Wrong stop ID** — verify with `python tools/find_stops.py --agency 8 --stop-id 70`
- **Vehicle type filter too restrictive** — if you set it to trams only (`[0]`) but the stop only has buses, you'll see nothing. Check with `--routes` to see what types serve your stop.
- **Check logs** — in HA: **Settings** → **System** → **Logs**, filter for `tranzy_transit`

### Card not rendering

- Verify the Lovelace resource is registered (**Settings** → **Dashboards** → **Resources**)
- Hard-refresh the browser: `Ctrl+Shift+R`
- Check browser console (`F12`) for JavaScript errors
- Make sure the entity ID in the card config matches the actual sensor

### Stale data / not updating

- Static GTFS data is cached for 4 hours — this is by design to avoid hammering the API
- Vehicle positions are fetched every poll cycle (30s default)
- If you see consistently stale vehicle timestamps, the transit operator's GPS feed may be unreliable
- You can adjust the poll interval in the integration options (minimum 10 seconds, but 30s is recommended to avoid rate limits)

### "arrival_time" missing from stop_times

The `arrival_time` and `departure_time` fields in `stop_times` are optional in the GTFS spec. Some agencies don't populate them, or they may be absent for certain trips. When missing, the integration falls back to GPS-based "stops away" estimation. During normal service hours, most agencies provide arrival times.

---

## Extending to Other Cities

To add a different city:

1. Create a new app at [apps.tranzy.ai/accounts](https://apps.tranzy.ai/accounts) for that city's agency
2. Run `python tools/find_stops.py --agencies` with your new key to find the agency ID
3. Run `python tools/find_stops.py --agency <ID> --search "your stop name"` to find the stop ID
4. In HA, add another instance of the Tranzy Transit integration with the new key, agency ID, and stop ID

Each stop is a separate integration instance, so you can have multiple stops from multiple cities on the same dashboard.

---

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- [Tranzy.ai](https://tranzy.ai/) for the Open Data API
- [GTFS specification](https://gtfs.org/)
- Inspired by [tranzy-stats](https://github.com/horace42/tranzy-stats)
