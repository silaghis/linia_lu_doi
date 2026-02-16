#!/usr/bin/env python3
"""Tranzy Transit CLI — query stops, routes, and live arrivals from terminal.

Setup:
    export TRANZY_API_KEY=your_key_here

Usage:
    python find_stops.py --agencies                          # List agencies for your key
    python find_stops.py --agency 8 --routes                 # List all routes
    python find_stops.py --agency 8 --search "Piata"         # Search stops by name
    python find_stops.py --agency 8 --list-all               # List all stops
    python find_stops.py --agency 8 --stop-id 70             # Details + routes for a stop
    python find_stops.py --agency 8 --arrivals 70            # ⭐ Live arrivals at stop 70
    python find_stops.py --agency 8 --arrivals 70 --type 0   # Only trams (type 0)
    python find_stops.py --agency 8 --arrivals 70 --watch    # Auto-refresh every 30s
"""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "https://api.tranzy.ai/v1/opendata"


def api_get(endpoint, api_key, agency_id=None):
    """GET a Tranzy API endpoint, return parsed JSON list."""
    req = Request(f"{BASE}/{endpoint}")
    req.add_header("X-API-KEY", api_key)
    req.add_header("Accept", "application/json")
    if agency_id is not None:
        req.add_header("X-Agency-Id", str(agency_id))
    try:
        with urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except HTTPError as e:
        print(f"\n  ❌ HTTP {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 403:
            print("     403 = wrong API key or agency_id mismatch.", file=sys.stderr)
            print("     Each key is bound to one agency. Check apps.tranzy.ai/accounts", file=sys.stderr)
        sys.exit(1)


# ── Vehicle type labels ──────────────────────────────────────

VTYPES = {0: "Tram", 1: "Metro", 2: "Rail", 3: "Bus", 4: "Ferry",
           5: "Cable", 6: "Aerial", 7: "Funicular", 11: "Trolley", 12: "Mono"}

VTYPE_EMOJI = {0: "🚋", 1: "🚇", 2: "🚆", 3: "🚌", 4: "⛴️",
               5: "🚡", 6: "🚡", 7: "🚡", 11: "🚎", 12: "🚝"}


# ── Arrivals logic ───────────────────────────────────────────

def compute_arrivals(api_key, agency_id, stop_id, type_filter=None):
    """Compute upcoming arrivals at a stop. Returns a sorted list of dicts."""
    print("  Loading routes...", end="", flush=True)
    routes_raw = api_get("routes", api_key, agency_id)
    routes = {r["route_id"]: r for r in routes_raw if "route_id" in r}
    print(f" {len(routes)} routes", flush=True)

    print("  Loading trips...", end="", flush=True)
    trips_raw = api_get("trips", api_key, agency_id)
    trips = {str(t["trip_id"]): t for t in trips_raw if "trip_id" in t}
    print(f" {len(trips)} trips", flush=True)

    print("  Loading stops...", end="", flush=True)
    stops_raw = api_get("stops", api_key, agency_id)
    stops = {int(s["stop_id"]): s for s in stops_raw if "stop_id" in s}
    print(f" {len(stops)} stops", flush=True)

    print("  Loading stop_times...", end="", flush=True)
    st_raw = api_get("stop_times", api_key, agency_id)
    print(f" {len(st_raw)} records", flush=True)

    print("  Loading vehicles...", end="", flush=True)
    vehicles_raw = api_get("vehicles", api_key, agency_id)
    print(f" {len(vehicles_raw)} vehicles", flush=True)

    # ── Index stop_times for our stop ────────────────────────
    # Also build trip → ordered stop list for GPS estimation
    our_stop_times = []          # stop_time records at our stop
    trip_stop_order = {}         # trip_id → [stop_id, stop_id, ...]
    trips_for_stop = {}          # {trip_id: our_index_in_sequence}

    # First pass: build trip stop orders
    trip_stops_unsorted = {}
    for st in st_raw:
        tid = str(st.get("trip_id", ""))
        sid = st.get("stop_id")
        seq = st.get("stop_sequence", 0)
        if tid and sid is not None:
            trip_stops_unsorted.setdefault(tid, []).append((int(seq), int(sid)))
            if int(sid) == stop_id:
                our_stop_times.append(st)

    for tid, pairs in trip_stops_unsorted.items():
        pairs.sort()
        trip_stop_order[tid] = [s for _, s in pairs]

    # Build: which trips serve our stop + our index
    for tid, stop_list in trip_stop_order.items():
        for idx, sid in enumerate(stop_list):
            if sid == stop_id:
                trips_for_stop[tid] = idx
                break

    if not our_stop_times:
        return [], stops.get(stop_id, {})

    # ── Which route_ids serve our stop? ──────────────────────
    serving_route_ids = set()
    for tid in trips_for_stop:
        t = trips.get(tid, {})
        rid = t.get("route_id")
        if rid is not None:
            serving_route_ids.add(int(rid))

    # ── Index vehicles by trip_id ────────────────────────────
    now_utc = datetime.now(timezone.utc)
    vehicle_by_trip = {}
    vehicles_by_route = {}  # route_id → [vehicle, ...]

    for v in vehicles_raw:
        # Check freshness
        ts = v.get("timestamp", "")
        try:
            vt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age = (now_utc - vt).total_seconds()
            if age > 600:
                continue  # stale (>10 min)
        except (ValueError, TypeError):
            continue

        vtid = v.get("trip_id")
        vrid = v.get("route_id")
        if vtid:
            vehicle_by_trip[str(vtid)] = v
        if vrid is not None:
            vehicles_by_route.setdefault(int(vrid), []).append(v)

    # ── Compute arrivals ─────────────────────────────────────
    now = datetime.now()
    arrivals = []
    seen_trips = set()

    for st in our_stop_times:
        tid = str(st.get("trip_id", ""))
        if not tid or tid in seen_trips or tid not in trips:
            continue
        seen_trips.add(tid)

        trip = trips[tid]
        rid = trip.get("route_id")
        route = routes.get(int(rid) if rid is not None else -1, {})
        route_type = int(route.get("route_type", 3))

        # Apply type filter
        if type_filter is not None and route_type != type_filter:
            continue

        route_name = str(route.get("route_short_name", "?"))
        headsign = trip.get("trip_headsign", route.get("route_long_name", ""))
        type_name = VTYPES.get(route_type, "?")
        emoji = VTYPE_EMOJI.get(route_type, "🚍")

        # Schedule ETA
        eta_minutes = None
        arr_time_str = st.get("arrival_time") or st.get("departure_time")
        if arr_time_str and isinstance(arr_time_str, str) and ":" in arr_time_str:
            try:
                parts = arr_time_str.split(":")
                h, m = int(parts[0]), int(parts[1])
                sched = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=h, minutes=m)
                diff = (sched - now).total_seconds() / 60.0
                if -2 <= diff <= 180:
                    eta_minutes = max(0, round(diff))
            except (ValueError, IndexError):
                pass

        # GPS: vehicle on this trip?
        vehicle = vehicle_by_trip.get(tid)
        stops_away = None
        v_label = ""
        v_speed = None
        v_lat = None
        v_lon = None
        is_realtime = False

        if vehicle:
            v_label = vehicle.get("label", "")
            v_speed = vehicle.get("speed", 0)
            v_lat = vehicle.get("latitude")
            v_lon = vehicle.get("longitude")
            is_realtime = True

            # Estimate stops away
            our_idx = trips_for_stop.get(tid)
            t_stops = trip_stop_order.get(tid, [])
            if our_idx is not None and v_lat and v_lon and t_stops:
                v_idx = _nearest_stop_idx(v_lat, v_lon, t_stops, stops)
                sa = our_idx - v_idx
                if sa >= -1:  # allow 1 stop tolerance (just passed)
                    stops_away = max(0, sa)

        # Skip if no useful info
        if eta_minutes is None and stops_away is None and not is_realtime:
            continue

        arrivals.append({
            "route": route_name,
            "headsign": headsign,
            "type": type_name,
            "type_num": route_type,
            "emoji": emoji,
            "eta_minutes": eta_minutes,
            "scheduled": arr_time_str or "",
            "stops_away": stops_away,
            "vehicle_label": v_label,
            "speed": v_speed,
            "realtime": is_realtime,
            "lat": v_lat,
            "lon": v_lon,
        })

    # Also add vehicles on serving routes that have no trip (route_id only)
    for rid in serving_route_ids:
        route = routes.get(rid, {})
        route_type = int(route.get("route_type", 3))
        if type_filter is not None and route_type != type_filter:
            continue
        for v in vehicles_by_route.get(rid, []):
            if v.get("trip_id"):
                continue  # already handled above
            arrivals.append({
                "route": str(route.get("route_short_name", "?")),
                "headsign": "",
                "type": VTYPES.get(route_type, "?"),
                "type_num": route_type,
                "emoji": VTYPE_EMOJI.get(route_type, "🚍"),
                "eta_minutes": None,
                "scheduled": "",
                "stops_away": None,
                "vehicle_label": v.get("label", ""),
                "speed": v.get("speed", 0),
                "realtime": True,
                "lat": v.get("latitude"),
                "lon": v.get("longitude"),
            })

    # Sort: ETA first, then stops_away, then realtime-only
    arrivals.sort(key=lambda a: (
        0 if a["eta_minutes"] is not None else (1 if a["stops_away"] is not None else 2),
        a["eta_minutes"] if a["eta_minutes"] is not None else 999,
        a["stops_away"] if a["stops_away"] is not None else 999,
    ))

    return arrivals, stops.get(stop_id, {})


def _nearest_stop_idx(lat, lon, stop_ids, stops_dict):
    """Find the index in stop_ids whose stop is closest to (lat, lon)."""
    best_i, best_d = 0, float("inf")
    for i, sid in enumerate(stop_ids):
        s = stops_dict.get(sid, {})
        slat = s.get("stop_lat")
        slon = s.get("stop_lon")
        if slat is None or slon is None:
            continue
        d = (lat - float(slat)) ** 2 + (lon - float(slon)) ** 2
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def print_arrivals(arrivals, stop_info, stop_id, type_filter):
    """Pretty-print arrivals to terminal."""
    stop_name = stop_info.get("stop_name", f"Stop {stop_id}")
    type_label = VTYPES.get(type_filter, "All") if type_filter is not None else "All types"

    print()
    print(f"  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║  🚏  {stop_name:<50} ║")
    print(f"  ║  Stop {stop_id} · {type_label:<44} ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")

    if not arrivals:
        print(f"  ║  No upcoming arrivals                                   ║")
        print(f"  ║  (service may be over, or no active vehicles)           ║")
        print(f"  ╚══════════════════════════════════════════════════════════╝")
        return

    for a in arrivals[:15]:
        emoji = a["emoji"]
        route = a["route"]
        headsign = a["headsign"]

        # Build ETA string
        if a["eta_minutes"] is not None:
            m = a["eta_minutes"]
            if m == 0:
                eta_str = " NOW"
            elif m == 1:
                eta_str = "1 min"
            else:
                eta_str = f"{m} min"
        elif a["stops_away"] is not None:
            s = a["stops_away"]
            if s == 0:
                eta_str = "HERE"
            elif s == 1:
                eta_str = "1 stop"
            else:
                eta_str = f"{s} stops"
        else:
            eta_str = "on route"

        # Build info line
        parts = []
        if a["vehicle_label"]:
            parts.append(f"veh:{a['vehicle_label']}")
        if a["scheduled"]:
            parts.append(f"sched:{a['scheduled'][:5]}")
        if a["speed"] and a["speed"] > 0:
            parts.append(f"{a['speed']}km/h")
        if a["realtime"]:
            parts.append("🟢 LIVE")
        info = " · ".join(parts)

        # Truncate headsign
        dest = headsign[:30] if headsign else a["type"]

        print(f"  ║  {emoji} {route:>4}  → {dest:<30}  {eta_str:>8}  ║")
        if info:
            print(f"  ║         {info:<49} ║")

    print(f"  ╚══════════════════════════════════════════════════════════╝")
    print(f"  Updated: {datetime.now().strftime('%H:%M:%S')}")


# ── Other commands (unchanged) ───────────────────────────────

def cmd_agencies(api_key):
    agencies = api_get("agency", api_key)
    print(f"\n  Agencies available for your API key:\n")
    for a in agencies:
        print(f"    ID={a['agency_id']:<5} {a.get('agency_name','?'):<30} {a.get('agency_url','')}")
    print()


def cmd_routes(api_key, agency_id):
    routes = api_get("routes", api_key, agency_id)
    print(f"\n  {len(routes)} routes for agency {agency_id}:\n")
    print(f"  {'ID':<8} {'Name':<8} {'Type':<12} {'Long Name'}")
    print(f"  {'-'*60}")
    for r in sorted(routes, key=lambda x: (
        int(x.get("route_short_name", "999")) if str(x.get("route_short_name", "")).isdigit() else 999,
        str(x.get("route_short_name", ""))
    )):
        rt = int(r.get("route_type", 3))
        tn = VTYPES.get(rt, "?")
        print(f"  {r.get('route_id',''):<8} {r.get('route_short_name',''):<8} {tn:<12} {r.get('route_long_name','')}")
    print()


def cmd_stop_detail(api_key, agency_id, stop_id):
    stops = api_get("stops", api_key, agency_id)
    s = next((x for x in stops if x.get("stop_id") == stop_id), None)
    if not s:
        print(f"\n  Stop {stop_id} not found for agency {agency_id}\n")
        return
    print(f"\n  Stop details:")
    print(json.dumps(s, indent=4))

    # Find routes serving this stop
    st = api_get("stop_times", api_key, agency_id)
    trips = {str(t["trip_id"]): t for t in api_get("trips", api_key, agency_id)}
    routes = {r["route_id"]: r for r in api_get("routes", api_key, agency_id)}
    rids = set()
    for x in st:
        if x.get("stop_id") == stop_id:
            t = trips.get(str(x.get("trip_id")), {})
            rid = t.get("route_id")
            if rid is not None:
                rids.add(rid)
    print(f"\n  Routes through stop {stop_id}:")
    for rid in sorted(rids):
        r = routes.get(rid, {})
        rt = int(r.get("route_type", 3))
        tn = VTYPES.get(rt, "?")
        print(f"    {VTYPE_EMOJI.get(rt, '?')} {r.get('route_short_name','?'):>4} ({tn}) — {r.get('route_long_name','')}")
    print()


def cmd_search_stops(api_key, agency_id, query=None):
    stops = api_get("stops", api_key, agency_id)
    if query:
        q = query.lower()
        stops = [s for s in stops if q in s.get("stop_name", "").lower()]
    print(f"\n  {len(stops)} stops:\n")
    print(f"  {'ID':<8} {'Name':<40} {'Lat':<12} {'Lon'}")
    print(f"  {'-'*70}")
    for s in sorted(stops, key=lambda x: x.get("stop_name", "")):
        print(f"  {s.get('stop_id',''):<8} {s.get('stop_name',''):<40} {s.get('stop_lat',''):<12} {s.get('stop_lon','')}")
    print()


# ── Main ─────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Tranzy Transit CLI — explore stops, routes, and live arrivals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --agencies
  %(prog)s --agency 8 --routes
  %(prog)s --agency 8 --search "Piata"
  %(prog)s --agency 8 --stop-id 70
  %(prog)s --agency 8 --arrivals 70
  %(prog)s --agency 8 --arrivals 70 --type 0
  %(prog)s --agency 8 --arrivals 70 --type 0 --watch

Vehicle types: 0=Tram  3=Bus  11=Trolleybus  1=Metro  2=Rail
        """,
    )
    p.add_argument("--agency", type=int, help="Agency ID (number, e.g. 8)")
    p.add_argument("--agencies", action="store_true", help="List all agencies")
    p.add_argument("--routes", action="store_true", help="List routes")
    p.add_argument("--search", metavar="NAME", help="Search stops by name")
    p.add_argument("--list-all", action="store_true", help="List all stops")
    p.add_argument("--stop-id", type=int, help="Show details for a stop")
    p.add_argument("--arrivals", type=int, metavar="STOP_ID",
                   help="⭐ Show live arrivals at a stop")
    p.add_argument("--type", type=int, metavar="N",
                   help="Filter by vehicle type (0=Tram, 3=Bus, 11=Trolley)")
    p.add_argument("--watch", action="store_true",
                   help="Auto-refresh arrivals every 30 seconds")
    p.add_argument("--api-key", help="API key (or set TRANZY_API_KEY env var)")
    args = p.parse_args()

    key = args.api_key or os.environ.get("TRANZY_API_KEY")
    if not key:
        print("\n  ❌ No API key. Set TRANZY_API_KEY env var or use --api-key\n", file=sys.stderr)
        sys.exit(1)

    if args.agencies:
        cmd_agencies(key)
        return

    if not args.agency and not args.agencies:
        if args.arrivals or args.routes or args.search or args.list_all or args.stop_id:
            print("\n  ❌ --agency required (use --agencies to find yours)\n", file=sys.stderr)
            sys.exit(1)
        p.print_help()
        return

    aid = args.agency

    if args.arrivals is not None:
        if args.watch:
            print("\n  ⏱  Watch mode — refreshing every 30s. Press Ctrl+C to stop.\n")
            try:
                while True:
                    arrivals, stop_info = compute_arrivals(key, aid, args.arrivals, args.type)
                    # Clear screen
                    print("\033[2J\033[H", end="")
                    print_arrivals(arrivals, stop_info, args.arrivals, args.type)
                    print(f"\n  Refreshing in 30s... (Ctrl+C to stop)")
                    time.sleep(30)
            except KeyboardInterrupt:
                print("\n\n  Stopped.\n")
        else:
            arrivals, stop_info = compute_arrivals(key, aid, args.arrivals, args.type)
            print_arrivals(arrivals, stop_info, args.arrivals, args.type)
        return

    if args.routes:
        cmd_routes(key, aid)
    elif args.stop_id is not None:
        cmd_stop_detail(key, aid, args.stop_id)
    elif args.search or args.list_all:
        cmd_search_stops(key, aid, args.search)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
