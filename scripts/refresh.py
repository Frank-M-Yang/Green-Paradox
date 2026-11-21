#!/usr/bin/env python3
"""Canopy Care: the one command. Run it once a day.

    python scripts/refresh.py

It fetches what is new from data.gov.sg, computes the inspection priorities once, writes
the snapshot the site reads plus the printable task sheet, and stops. Nothing keeps running.

    python scripts/refresh.py --offline                      rebuild from data/raw/ only
    python scripts/refresh.py --as-of 2026-11-21 --offline   rebuild a past day exactly (the demo day)
    python scripts/refresh.py --force                        download everything again

How it copes when a source is down: every source is tried on its own. If one fails, the
newest copy already in data/raw/ is used, the site shows that source's older snapshot date,
and the run carries on. It only stops if a source it cannot do without has never been cached.

Needs Python 3.11 or newer. No packages to install.
"""

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Canopy Care needs Python 3.11 or newer.")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_snapshot as build  # noqa: E402
import fetch_sources as fs  # noqa: E402
import rainfall as rf  # noqa: E402
import task_sheet  # noqa: E402
from sources import SOURCES  # noqa: E402


def newest_cached(key, suffix):
    path, snap = build.pick(key, "9999-12-31", suffix)
    return path, snap


def refresh_file(src, today, force):
    """Download a dataset file if it is due. Returns (status, note)."""
    key = src["key"]
    cached = None
    for ext in (".geojson", ".xlsx", ".csv"):
        p, s = newest_cached(key, ext)
        if p and (cached is None or s > cached[1]):
            cached = (p, s)
    if cached and not force:
        age = (date.fromisoformat(today) - date.fromisoformat(cached[1])).days
        if age < src.get("every_days", 1):
            return "cached", f"snapshot of {cached[1]} is {age} day(s) old; next download after {src.get('every_days', 1)} days"
    meta = fs.dataset_metadata(src)
    if cached and not force and src.get("only_if_changed"):
        old_meta = cached[0].with_name(cached[1] + ".metadata.json")
        if old_meta.exists() and json.loads(old_meta.read_text(encoding="utf-8")).get("lastUpdatedAt") == meta.get("lastUpdatedAt"):
            return "unchanged", f"publisher has not updated it since the snapshot of {cached[1]}"
    rec = fs.fetch_file_dataset(src, today, meta)
    return "fetched", f"{rec['bytes']:,} bytes, publisher updated {str(rec['source_last_updated'])[:10]}"


def refresh_latest(src, today, force):
    path, snap = newest_cached(src["key"], "_latest.json")
    if path and snap == today and not force:
        return "cached", "already fetched today"
    rec = fs.fetch_realtime_latest(src, today)
    return "fetched", f"{rec['bytes']:,} bytes"


def rain_days_needed(as_of):
    """Every calendar day the scenarios in config/demo_config.toml read.

    The days each score needs come first. The days before each window, which only the
    day-by-day replay on the map uses, follow: if the network gives out part-way, the
    scores are still complete and the replay says which of its days are short of rain data.
    """
    risk_cfg, demo_cfg = build.load_config()
    days, earlier = set(), set()
    for sc in build.scenario_windows(demo_cfg, as_of, risk_cfg["rain"]["lookback_days"]):
        days.update(sc["days"])
        earlier.update(sc["earlier_days"])
    return sorted(days) + sorted(earlier - days)


def refresh_rain(src, as_of, force):
    need = rain_days_needed(as_of)
    missing = [d for d in need if force or not rf.day_file(build.RAW, d).exists()]
    if not missing:
        return "cached", f"all {len(need)} days already cached", []
    failed = []
    if len(missing) > 3:
        print(f"         rainfall: {len(missing)} days to fetch, about {len(missing) * 12 * 2 // 60 + 1} minutes at the public rate limit", flush=True)
    for i, day in enumerate(missing, 1):
        try:
            fs.fetch_realtime_day(src, day, force=force)
            if len(missing) > 3:
                print(f"         rainfall {day}  ({i} of {len(missing)})", flush=True)
        except Exception as e:  # noqa: BLE001 - keep going: one bad day must not lose the others
            fs.record_failure(src["key"], f"day {day}", e)
            failed.append(day)
    got = len(missing) - len(failed)
    note = f"{got} new day(s) fetched, {len(need) - len(missing)} already cached"
    if failed:
        return "failed", note + f"; {len(failed)} day(s) could not be fetched ({failed[0]} .. {failed[-1]})", failed
    return "fetched", note, []


def run_fetch(as_of, today, force):
    """Try every source. Returns {key: {"status", "note"}}."""
    status = {}
    for src in SOURCES:
        key = src["key"]
        try:
            if src["kind"] == "file":
                st, note = refresh_file(src, today, force)
            elif src.get("daily_history"):
                st, note, _ = refresh_rain(src, as_of, force)
            else:
                st, note = refresh_latest(src, today, force)
        except Exception as e:  # noqa: BLE001 - one failing source must not stop the others
            fs.record_failure(key, "snapshot", e)
            st, note = "failed", f"{type(e).__name__}: {str(e)[:160]}"
        status[key] = {"status": st, "note": note}
        mark = {"fetched": "new   ", "unchanged": "same  ", "cached": "cache ", "failed": "FAILED"}[st]
        print(f"  {mark} {key:26s} {note}", flush=True)
    return status


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch what is new, compute once, write the snapshot. Run once a day.")
    ap.add_argument("--offline", action="store_true", help="do not touch the network; build from data/raw/")
    ap.add_argument("--as-of", help="build the snapshot for this date, YYYY-MM-DD (default: today in Singapore)")
    ap.add_argument("--force", action="store_true", help="download every source again, due or not")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    today = fs.now_sgt().date().isoformat()
    as_of = args.as_of or today
    if args.as_of and args.as_of > today:
        ap.error("--as-of cannot be in the future")

    status = {}
    if args.offline:
        print("Offline: using data/raw/ only.")
    else:
        print(f"Fetching (Singapore date {today}) ...", flush=True)
        try:
            status = run_fetch(as_of, today, args.force)
        except KeyboardInterrupt:
            print("Interrupted. Whatever was fetched so far is kept in data/raw/.")
            return 130
        failed = [k for k, v in status.items() if v["status"] == "failed"]
        print(f"  {fs.STATS['requests']} requests, {fs.STATS['bytes'] / 1024:,.0f} KB received.")
        if failed:
            print(f"  Could not fetch: {', '.join(failed)}. The newest cached copy of each is used where there is one.")

    print("Computing ...", flush=True)
    try:
        # Offline with no date given: use the newest day that is actually in the cache.
        snapshot, *_ = build.build(args.as_of if (args.as_of or args.offline) else as_of, refresh_status=status)
    except build.BuildError as e:
        print(f"Cannot build: {e}")
        return 1
    if not args.offline:
        snapshot["meta"]["last_refresh"] = {"requests": fs.STATS["requests"], "kilobytes": round(fs.STATS["bytes"] / 1024)}
    js_bytes, weight = build.write_snapshot(snapshot)
    sheet_bytes = task_sheet.write(snapshot, build.SITE / "task-sheet.html")

    meta = snapshot["meta"]
    sim = sum(1 for a in snapshot["assets"] if a["simulated"])
    print(f"Done in {time.monotonic() - t0:.0f} s. Snapshot for {meta['as_of']}: {len(snapshot['assets'])} assets ({sim} simulated).")
    print(f"  site/data/snapshot.js   {js_bytes / 1024:6.1f} KB")
    print(f"  site/task-sheet.html    {sheet_bytes / 1024:6.1f} KB")
    print(f"  page weight (everything index.html loads): {weight / 1024:.1f} KB")
    if meta["as_of"] != today:
        print(f"  NOTE: the snapshot date is {meta['as_of']}, not today ({today}).")
    for w in meta["warnings"]:
        print("  WARNING: " + w)
    print("Open site/index.html in a browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
