#!/usr/bin/env python3
"""Find Tranzy stop IDs, routes, and trip details.

Usage:
    export TRANZY_API_KEY=your_key
    python find_stops.py --agency 8 --search "Piata"
    python find_stops.py --agency 8 --list-all
    python find_stops.py --agency 8 --routes
    python find_stops.py --agency 8 --stop-id 70
    python find_stops.py --agencies   # list all agencies for your key
"""
import argparse, json, os, sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "https://api.tranzy.ai/v1/opendata"

def get(endpoint, api_key, agency_id=None):
    req = Request(f"{BASE}/{endpoint}")
    req.add_header("X-API-KEY", api_key)
    req.add_header("Accept", "application/json")
    if agency_id is not None:
        req.add_header("X-Agency-Id", str(agency_id))
    try:
        with urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except HTTPError as e:
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 403:
            print("403 = wrong API key or agency_id mismatch", file=sys.stderr)
        sys.exit(1)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agency", type=int, help="Agency ID (number)")
    p.add_argument("--search", help="Search stops by name")
    p.add_argument("--list-all", action="store_true", help="List all stops")
    p.add_argument("--routes", action="store_true", help="List routes")
    p.add_argument("--stop-id", type=int, help="Details for a stop")
    p.add_argument("--agencies", action="store_true", help="List agencies")
    p.add_argument("--api-key", help="API key (or TRANZY_API_KEY env)")
    args = p.parse_args()

    key = args.api_key or os.environ.get("TRANZY_API_KEY")
    if not key:
        print("Set TRANZY_API_KEY or use --api-key", file=sys.stderr); sys.exit(1)

    if args.agencies:
        for a in get("agency", key):
            print(f"  ID={a['agency_id']:>3}  {a.get('agency_name','?'):<30} {a.get('agency_url','')}")
        return

    if not args.agency:
        print("--agency required (or use --agencies to list)", file=sys.stderr); sys.exit(1)
    aid = args.agency

    if args.routes:
        routes = get("routes", key, aid)
        print(f"\n{len(routes)} routes:\n{'ID':<8} {'Name':<10} {'Type':<6} {'Long Name'}")
        print("-"*60)
        for r in sorted(routes, key=lambda x: str(x.get("route_short_name",""))):
            print(f"{r.get('route_id',''):<8} {r.get('route_short_name',''):<10} {r.get('route_type',''):<6} {r.get('route_long_name','')}")
        return

    if args.stop_id:
        stops = get("stops", key, aid)
        s = next((x for x in stops if x.get("stop_id") == args.stop_id), None)
        if s:
            print(json.dumps(s, indent=2))
            # Show routes through this stop
            st = get("stop_times", key, aid)
            trips = {t["trip_id"]: t for t in get("trips", key, aid)}
            routes = {r["route_id"]: r for r in get("routes", key, aid)}
            rids = set()
            for x in st:
                if x.get("stop_id") == args.stop_id:
                    t = trips.get(x.get("trip_id"), {})
                    rid = t.get("route_id")
                    if rid is not None: rids.add(rid)
            print(f"\nRoutes through stop {args.stop_id}:")
            for rid in sorted(rids):
                r = routes.get(rid, {})
                print(f"  {r.get('route_short_name','?'):>4} ({r.get('route_type','?')}) - {r.get('route_long_name','')}")
        else:
            print(f"Stop {args.stop_id} not found")
        return

    stops = get("stops", key, aid)
    if args.search:
        q = args.search.lower()
        stops = [s for s in stops if q in s.get("stop_name","").lower()]
    print(f"\n{len(stops)} stops:\n{'ID':<8} {'Name':<40} {'Lat':<12} {'Lon'}")
    print("-"*70)
    for s in sorted(stops, key=lambda x: x.get("stop_name","")):
        print(f"{s.get('stop_id',''):<8} {s.get('stop_name',''):<40} {s.get('stop_lat',''):<12} {s.get('stop_lon','')}")

if __name__ == "__main__":
    main()
