#!/usr/bin/env python3
"""Helper script to find stop IDs from the Tranzy API.

Usage:
    export TRANZY_API_KEY=your_key_here
    python find_stops.py --agency "STPT Timisoara" --search "Piata"
    python find_stops.py --agency "CTP Cluj" --list-all
    python find_stops.py --agency "STPT Timisoara" --routes
"""

import argparse
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_BASE = "https://api.tranzy.ai/v1/opendata"


def api_get(endpoint: str, api_key: str, agency_id: str) -> list:
    """Make a GET request to the Tranzy API."""
    url = f"{API_BASE}/{endpoint}"
    req = Request(url)
    req.add_header("X-API-KEY", api_key)
    req.add_header("X-Agency-Id", agency_id)
    req.add_header("Accept", "application/json")

    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Invalid API key. Get one at https://tranzy.dev/accounts/my-apps", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Find Tranzy stop IDs")
    parser.add_argument("--agency", required=True, help="Agency ID (e.g., 'STPT Timisoara')")
    parser.add_argument("--search", help="Search stops by name (partial match)")
    parser.add_argument("--list-all", action="store_true", help="List all stops")
    parser.add_argument("--routes", action="store_true", help="List all routes")
    parser.add_argument("--stop-id", help="Show details for a specific stop ID")
    parser.add_argument("--api-key", help="API key (or set TRANZY_API_KEY env var)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("TRANZY_API_KEY")
    if not api_key:
        print("Error: Set TRANZY_API_KEY environment variable or use --api-key", file=sys.stderr)
        sys.exit(1)

    if args.routes:
        print(f"Fetching routes for {args.agency}...")
        routes = api_get("routes", api_key, args.agency)
        print(f"\nFound {len(routes)} routes:\n")
        print(f"{'Route ID':<15} {'Short Name':<12} {'Type':<8} {'Long Name'}")
        print("-" * 80)
        for r in sorted(routes, key=lambda x: str(x.get("route_short_name", ""))):
            print(
                f"{r.get('route_id', ''):<15} "
                f"{r.get('route_short_name', ''):<12} "
                f"{r.get('route_type', ''):<8} "
                f"{r.get('route_long_name', '')}"
            )
        return

    if args.stop_id:
        print(f"Fetching stop details for {args.stop_id}...")
        stops = api_get("stops", api_key, args.agency)
        stop = next((s for s in stops if str(s.get("stop_id")) == args.stop_id), None)
        if stop:
            print(json.dumps(stop, indent=2))

            # Also find which routes serve this stop
            print("\nFetching routes serving this stop...")
            stop_times = api_get("stop_times", api_key, args.agency)
            trips = api_get("trips", api_key, args.agency)
            routes = api_get("routes", api_key, args.agency)

            trip_map = {str(t["trip_id"]): t for t in trips}
            route_map = {str(r["route_id"]): r for r in routes}

            route_ids = set()
            for st in stop_times:
                if str(st.get("stop_id")) == args.stop_id:
                    tid = str(st.get("trip_id", ""))
                    trip = trip_map.get(tid, {})
                    rid = str(trip.get("route_id", ""))
                    if rid:
                        route_ids.add(rid)

            print(f"\nRoutes serving stop {args.stop_id}:")
            for rid in sorted(route_ids):
                r = route_map.get(rid, {})
                print(f"  {r.get('route_short_name', '?')} - {r.get('route_long_name', '')}")
        else:
            print(f"Stop {args.stop_id} not found")
        return

    # Fetch stops
    print(f"Fetching stops for {args.agency}...")
    stops = api_get("stops", api_key, args.agency)

    if args.search:
        query = args.search.lower()
        stops = [s for s in stops if query in s.get("stop_name", "").lower()]

    print(f"\nFound {len(stops)} stops:\n")
    print(f"{'Stop ID':<15} {'Name':<40} {'Lat':<12} {'Lon':<12}")
    print("-" * 80)
    for s in sorted(stops, key=lambda x: x.get("stop_name", "")):
        print(
            f"{s.get('stop_id', ''):<15} "
            f"{s.get('stop_name', ''):<40} "
            f"{s.get('stop_lat', ''):<12} "
            f"{s.get('stop_lon', ''):<12}"
        )


if __name__ == "__main__":
    main()
