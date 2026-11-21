#!/usr/bin/env python3
"""Fetch the open datasets Canopy Care relies on and keep dated snapshots in data/raw/.

Standard library only. Run from anywhere:

    python scripts/fetch_sources.py                     # every source, last 30 days of rainfall
    python scripts/fetch_sources.py --only parks,rainfall
    python scripts/fetch_sources.py --rain-days 14

What it writes (all under data/raw/):

    <key>/<YYYY-MM-DD>.<ext>              dataset file exactly as served
    <key>/<YYYY-MM-DD>.metadata.json      the data.gov.sg metadata record for that file
    <key>/<YYYY-MM-DD>_latest.json        latest real-time reading
    rainfall/day_<YYYY-MM-DD>.json.gz     all 5-minute readings of one day, pages merged
    manifest.json                         what was fetched, when, from which URL, and what failed

Snapshot dates are Singapore dates (UTC+8), because that is the clock the sources use.

Nothing here invents data. When a source fails, the failure is recorded in the manifest
and the older snapshots are left untouched so later steps can fall back to them.

Rate limits without an API key (data.gov.sg developer guide, read Nov 2026): real-time
API 6 calls per 10 seconds; dataset downloads 2 per 10 seconds on one page and 5 per
minute on another. The gaps below stay under the stricter figure. An API key is optional;
if the environment variable DATA_GOV_SG_API_KEY is set it is sent as x-api-key.
"""

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import ALL_SOURCES as SOURCES  # noqa: E402
from sources import API_DOWNLOAD, API_META, API_REALTIME  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.json"
SGT = timezone(timedelta(hours=8))

# Minimum seconds between two calls of the same class.
GAPS = {"meta": 0.4, "download": 13.0, "realtime": 2.0, "blob": 0.2}
HEADERS = {"User-Agent": "open-data-fetch/1.0", "Accept": "*/*", "Accept-Encoding": "gzip"}
if os.environ.get("DATA_GOV_SG_API_KEY"):
    HEADERS["x-api-key"] = os.environ["DATA_GOV_SG_API_KEY"]

READINGS_PER_FULL_DAY = 288  # 5-minute rainfall totals


class FetchError(Exception):
    pass


# Running totals for this run: how many requests were made and how many bytes came over the wire.
STATS = {"requests": 0, "bytes": 0}


_last_call = {}


def _throttle(bucket):
    wait = _last_call.get(bucket, 0.0) + GAPS[bucket] - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call[bucket] = time.monotonic()


def http_get(url, bucket, timeout=90, tries=4):
    """GET with throttling and a few retries. Returns the body as bytes.

    A rate-limit answer is retried patiently. A network that is simply down is given up on
    after two quick attempts, so an offline run falls back to the cache in seconds, not minutes.
    """
    refused = 0
    last = "unknown error"
    for attempt in range(1, tries + 1):
        _throttle(bucket)
        headers = dict(HEADERS)
        if bucket == "blob":  # pre-signed storage link: never forward an API key to it
            headers.pop("x-api-key", None)
        try:
            req = urllib.request.Request(url, headers=headers)
            STATS["requests"] += 1
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                STATS["bytes"] += len(raw)
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode("utf-8", "replace")
            last = f"HTTP {e.code}: {detail}"
            if e.code == 429:
                time.sleep(15 * attempt)  # back off further each time: 15 s, 30 s, 45 s
            elif e.code >= 500:
                time.sleep(3 * attempt)
            else:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = f"{type(e).__name__}: {e}"
            refused += 1
            if refused >= 2:
                break
            time.sleep(2)
    raise FetchError(f"{last} [{url.split('?')[0]}]")


def get_json(url, bucket):
    body = http_get(url, bucket)
    try:
        doc = json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise FetchError(f"not JSON: {e} [{url.split('?')[0]}]") from e
    if isinstance(doc, dict) and doc.get("code") not in (0, None):
        raise FetchError(f"API error {doc.get('code')} {doc.get('name')}: {doc.get('errorMsg')} [{url.split('?')[0]}]")
    return doc


def now_sgt():
    return datetime.now(SGT)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- manifest


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"snapshots": [], "failures": []}


def save_manifest(man):
    man["updated_at"] = now_sgt().isoformat(timespec="seconds")
    man["snapshots"].sort(key=lambda r: (r["key"], r["file"]))
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(MANIFEST)  # atomic: a run that is interrupted cannot leave half a manifest


def record_ok(rec):
    # Re-read before every write so two runs at the same time do not drop each other's records.
    man = load_manifest()
    man["snapshots"] = [r for r in man["snapshots"] if r["file"] != rec["file"]]
    man["snapshots"].append(rec)
    # A later success closes earlier failures of the same fetch, so the log reads correctly.
    what = f"day {rec['snapshot_date']}" if rec["kind"] == "realtime-day" else "snapshot"
    for f in man["failures"]:
        if f["key"] == rec["key"] and f["what"] == what and "resolved_at" not in f:
            f["resolved_at"] = rec["fetched_at"]
    save_manifest(man)


def record_failure(key, what, err):
    man = load_manifest()
    man["failures"].append(
        {"key": key, "what": what, "attempted_at": now_sgt().isoformat(timespec="seconds"), "error": str(err)}
    )
    man["failures"] = man["failures"][-200:]
    save_manifest(man)


# --------------------------------------------------------------------------- fetchers


def dataset_metadata(src):
    """The data.gov.sg metadata record for a dataset: name, format, last updated time."""
    meta = get_json(f"{API_META}/datasets/{src['dataset_id']}/metadata", "meta")["data"]
    # The metadata record names individual agency staff as contacts. The demo has no use
    # for them and must not display personal data, so they are not kept.
    meta.pop("contactEmails", None)
    return meta


def fetch_file_dataset(src, snap_date, meta=None):
    """Download a dataset file through the documented poll-download endpoint."""
    key, ds = src["key"], src["dataset_id"]
    if meta is None:
        meta = dataset_metadata(src)
    poll_url = f"{API_DOWNLOAD}/datasets/{ds}/poll-download"
    poll = get_json(poll_url, "download").get("data") or {}
    if not poll.get("url"):
        # Tabular datasets need the download to be initiated first.
        get_json(f"{API_DOWNLOAD}/datasets/{ds}/initiate-download", "download")
        for _ in range(8):
            poll = get_json(poll_url, "download").get("data") or {}
            if poll.get("url"):
                break
        else:
            raise FetchError(f"poll-download never returned a link for {ds}")
    signed = poll["url"]
    blob_path = urllib.parse.urlparse(signed).path  # the signed query string is a short-lived credential: not stored
    ext = Path(blob_path).suffix.lstrip(".").lower() or "bin"
    body = http_get(signed, "blob", timeout=300)

    out_dir = RAW / key
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{snap_date}.{ext}"
    out.write_bytes(body)
    (out_dir / f"{snap_date}.metadata.json").write_text(
        json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    rec = {
        "key": key,
        "kind": "file",
        "snapshot_date": snap_date,
        "file": f"{key}/{out.name}",
        "bytes": len(body),
        "sha256": sha256(body),
        "fetched_at": now_sgt().isoformat(timespec="seconds"),
        "request_url": poll_url,
        "served_from": "https://s3.ap-southeast-1.amazonaws.com" + blob_path,
        "source_last_updated": meta.get("lastUpdatedAt"),
        "source_format": meta.get("format"),
    }
    record_ok(rec)
    return rec


def fetch_realtime_latest(src, snap_date):
    """Save the latest reading of a real-time endpoint exactly as served."""
    key = src["key"]
    url = API_REALTIME + src["path"]
    body = http_get(url, "realtime")
    doc = json.loads(body.decode("utf-8"))
    if doc.get("code") != 0:
        raise FetchError(f"API error {doc.get('code')}: {doc.get('errorMsg')}")
    out_dir = RAW / key
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{snap_date}_latest.json"
    out.write_bytes(body)
    rec = {
        "key": key,
        "kind": "realtime-latest",
        "snapshot_date": snap_date,
        "file": f"{key}/{out.name}",
        "bytes": len(body),
        "sha256": sha256(body),
        "fetched_at": now_sgt().isoformat(timespec="seconds"),
        "request_url": url,
    }
    record_ok(rec)
    return rec


def read_day_file(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def fetch_realtime_day(src, day, force=False):
    """Fetch every reading of one Singapore calendar day, following pagination.

    A day that is already cached in full is not fetched again: past days do not change
    in any way the demo depends on, and skipping them keeps the daily run small.
    """
    key = src["key"]
    out_dir = RAW / key
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"day_{day}.json.gz"
    today = now_sgt().date().isoformat()
    if out.exists() and not force:
        cached = read_day_file(out)
        if cached.get("complete_day"):
            return {"file": f"{key}/{out.name}", "cached": True, "readings": len(cached["readings"])}

    url0 = f"{API_REALTIME}{src['path']}?date={day}"
    stations, readings, pages, token, extra = {}, [], 0, None, {}
    while True:
        url = url0 + (f"&paginationToken={urllib.parse.quote(token, safe='')}" if token else "")
        data = get_json(url, "realtime")["data"]
        for s in data.get("stations", []):
            stations[s["id"]] = s
        readings.extend(data.get("readings", []))
        for k in ("readingType", "readingUnit"):
            if k in data:
                extra[k] = data[k]
        pages += 1
        token = data.get("paginationToken")
        if not token:
            break
        if pages > 400:
            raise FetchError(f"pagination did not end for {day}")
    readings.sort(key=lambda r: r["timestamp"])
    merged = {
        "date": day,
        "request_url": url0,
        "pages_merged": pages,
        "fetched_at": now_sgt().isoformat(timespec="seconds"),
        "complete_day": day < today,
        **extra,
        "stations": sorted(stations.values(), key=lambda s: s["id"]),
        "readings": readings,
    }
    body = gzip.compress(json.dumps(merged, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)
    out.write_bytes(body)
    rec = {
        "key": key,
        "kind": "realtime-day",
        "snapshot_date": day,
        "file": f"{key}/{out.name}",
        "bytes": len(body),
        "sha256": sha256(body),
        "fetched_at": merged["fetched_at"],
        "request_url": url0,
        "pages_merged": pages,
        "readings": len(readings),
        "stations": len(stations),
        "complete_day": merged["complete_day"],
    }
    record_ok(rec)
    return rec


# --------------------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", help="comma-separated source keys (default: all)")
    ap.add_argument("--rain-days", type=int, default=30, help="complete days of rainfall history to keep cached")
    ap.add_argument("--rain-until", help="last rainfall day to fetch, YYYY-MM-DD (default: yesterday, Singapore time)")
    ap.add_argument("--no-today", action="store_true", help="skip the partial rainfall file for today")
    ap.add_argument("--force", action="store_true", help="re-fetch rainfall days that are already cached")
    args = ap.parse_args(argv)

    wanted = set(args.only.split(",")) if args.only else None
    unknown = (wanted or set()) - {s["key"] for s in SOURCES}
    if unknown:
        ap.error(f"unknown source key(s): {', '.join(sorted(unknown))}")

    snap_date = now_sgt().date().isoformat()
    ok, failed = [], []

    for src in SOURCES:
        key = src["key"]
        if wanted and key not in wanted:
            continue
        try:
            if src["kind"] == "file":
                rec = fetch_file_dataset(src, snap_date)
                print(f"ok    {key:26s} {rec['bytes']:>10,d} B  updated {rec['source_last_updated']}", flush=True)
            else:
                rec = fetch_realtime_latest(src, snap_date)
                print(f"ok    {key:26s} {rec['bytes']:>10,d} B  latest reading", flush=True)
            ok.append(key)
        except Exception as e:  # noqa: BLE001 - one failing source must not stop the others
            record_failure(key, "snapshot", e)
            print(f"FAIL  {key:26s} {e}", flush=True)
            failed.append(key)

        if src.get("daily_history"):
            last = (
                datetime.strptime(args.rain_until, "%Y-%m-%d").date()
                if args.rain_until
                else now_sgt().date() - timedelta(days=1)
            )
            days = [(last - timedelta(days=i)).isoformat() for i in range(args.rain_days)]
            if not args.no_today and not args.rain_until:
                days.insert(0, snap_date)
            for day in days:
                try:
                    rec = fetch_realtime_day(src, day, force=args.force)
                    state = "cached" if rec.get("cached") else f"{rec['pages_merged']} pages"
                    print(f"ok    {key:26s} day {day}  {rec['readings']:>3d} readings  ({state})", flush=True)
                except Exception as e:  # noqa: BLE001
                    record_failure(key, f"day {day}", e)
                    print(f"FAIL  {key:26s} day {day}  {e}", flush=True)
                    failed.append(f"{key}:{day}")

    print(f"\n{len(ok)} source(s) fetched, {len(failed)} failure(s). Manifest: {MANIFEST}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
