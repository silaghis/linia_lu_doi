# Tranzy Transit - Home Assistant Integration

Real-time public transit arrivals for your Home Assistant dashboard, powered by the [Tranzy OpenData API](https://api.tranzy.ai/v1/opendata/docs#/).

![Transit Card Example](docs/card-example.png)

## Features

- **Real-time arrivals** — polls the Tranzy API at configurable intervals (default 30s)
- **Multiple vehicle types** — trams, buses, trolleybuses, metro, and more
- **Route filtering** — clickable route chips to show/hide specific lines
- **Multi-stop support** — add as many stops as you want, each as a separate integration instance
- **Multi-city support** — works with any Tranzy-supported agency (Cluj, Iași, Timișoara, Botoșani, Chișinău, etc.)
- **Custom Lovelace card** — dark-theme-friendly card with color-coded route badges, ETA countdown, and real-time indicators
- **HACS compatible** — install directly from HACS as a custom repository
- **Config flow UI** — set up everything from the Home Assistant UI, no YAML required

## Supported Agencies

| Agency ID | City | Country |
|-----------|------|---------|
| CTP Cluj | Cluj-Napoca | Romania |
| SCTP Iasi | Iași | Romania |
| STPT Timisoara | Timișoara | Romania |
| Eltrans Botosani | Botoșani | Romania |
| RTEC Chisinau | Chișinău | Moldova |
| Tursib Sibiu | Sibiu | Romania |
| OTL Oradea | Oradea | Romania |
| CTP Arad | Arad | Romania |

> Note: Agency availability depends on Tranzy's partnerships. Check [tranzy.ai/opendata](https://tranzy.ai/opendata/) for the latest list.

## Prerequisites

1. **Tranzy API Key** — Create a free account and app at [tranzy.dev/accounts/my-apps](https://tranzy.dev/accounts/my-apps)
2. **Stop ID** — Find the stop ID for the station you want to monitor. You can:
   - Use the Tranzy mobile app to find stop IDs
   - Query the API: `GET /stops` with your API key and agency header
   - Use the helper script included in `tools/find_stops.py`

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add this repository URL: `https://github.com/ovi/ha-tranzy-transit`
4. Category: **Integration**
5. Click **Add** → Find "Tranzy Transit" → **Install**
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/tranzy_transit` folder to your HA `config/custom_components/` directory
2. Copy `custom_components/tranzy_transit/www/tranzy-transit-card.js` to `config/www/`
3. Restart Home Assistant

## Configuration

### 1. Add the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Tranzy Transit"
3. Enter your API key, select your agency, and provide the stop ID
4. Configure update interval and vehicle types
5. Click **Submit**

### 2. Register the Lovelace Card

Add to your `configuration.yaml` (or via the UI):

```yaml
lovelace:
  resources:
    - url: /local/community/tranzy_transit/tranzy-transit-card.js
      type: module
```

Or if installed manually:

```yaml
lovelace:
  resources:
    - url: /local/tranzy-transit-card.js
      type: module
```

### 3. Add the Card to Your Dashboard

Add a **Manual Card** with this YAML:

```yaml
type: custom:tranzy-transit-card
entity: sensor.tranzy_stpt_timisoara_YOUR_STOP_ID_next_arrival
title: Tram Arrivals
show_header: true
show_route_filter: true
max_rows: 10
compact: false
show_realtime_indicator: true
```

## Card Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `entity` | string | *required* | The "Next Arrival" sensor entity ID |
| `title` | string | "Transit Arrivals" | Card title |
| `show_header` | boolean | true | Show the card header |
| `show_route_filter` | boolean | true | Show clickable route filter chips |
| `routes_filter` | list | [] | Pre-select specific routes (empty = all) |
| `max_rows` | integer | 10 | Maximum arrival rows to display |
| `compact` | boolean | false | Compact display mode |
| `show_realtime_indicator` | boolean | true | Show green dot for real-time data |

## Sensors Created

For each configured stop, two sensors are created:

### `sensor.<agency>_<stop_id>_next_arrival`
- **State**: ETA in minutes of the next arrival
- **Attributes**:
  - `arrivals`: Full list of upcoming arrivals with route, destination, ETA, type, schedule
  - `routes`: Per-route summary with next ETA and count
  - `route_names`: List of route names serving this stop
  - `stop_name`: Human-readable stop name
  - `agency`: Agency identifier

### `sensor.<agency>_<stop_id>_arrival_count`
- **State**: Total number of upcoming arrivals

## Finding Your Stop ID

### Using the included helper script

```bash
# Set your API key
export TRANZY_API_KEY=your_key_here

# Run the helper
python tools/find_stops.py --agency "STPT Timisoara" --search "Piata"
```

### Using the API directly

```bash
curl -H "X-API-KEY: your_key" \
     -H "X-Agency-Id: STPT Timisoara" \
     https://api.tranzy.ai/v1/opendata/stops
```

## Architecture

```
custom_components/tranzy_transit/
├── __init__.py          # Integration setup & entry point
├── api.py               # Tranzy API client (GTFS endpoints)
├── config_flow.py       # UI configuration flow
├── const.py             # Constants, GTFS route types, known agencies
├── coordinator.py       # DataUpdateCoordinator for polling
├── manifest.json        # HA integration metadata
├── sensor.py            # Sensor entities
├── strings.json         # UI strings
├── translations/
│   └── en.json          # English translations
└── www/
    └── tranzy-transit-card.js  # Custom Lovelace card
```

## API Reference

This integration uses the Tranzy OpenData API which partially implements the [GTFS specification](https://gtfs.org/):

| Endpoint | Purpose | Caching |
|----------|---------|---------|
| `GET /routes` | All routes for the agency | 6 hours |
| `GET /stops` | All stops with names and coordinates | 6 hours |
| `GET /trips` | All trips (route instances) | 6 hours |
| `GET /stop_times` | Scheduled arrival times at stops | 6 hours |
| `GET /vehicles` | Real-time vehicle positions | Every poll |

## Troubleshooting

### No arrivals showing
- Verify your stop ID exists (check the API `/stops` endpoint)
- Check that your API key is valid and has the correct agency
- Look at Home Assistant logs: **Settings** → **System** → **Logs**, filter for `tranzy`

### Stale data
- The integration caches static GTFS data for 6 hours. Vehicle positions are fetched fresh each poll.
- Increase or decrease the poll interval in the integration options.

### Card not rendering
- Make sure the Lovelace resource is registered correctly
- Clear browser cache (Ctrl+Shift+R)
- Check browser console for JavaScript errors

## License

MIT License — see [LICENSE](LICENSE) file.

## Acknowledgments

- [Tranzy.ai](https://tranzy.ai/) for providing the Open Data API
- [GTFS](https://gtfs.org/) specification
- Inspired by [tranzy-stats](https://github.com/horace42/tranzy-stats) by horace42
