#!/usr/bin/env python3
"""Describe what is actually inside the snapshots in data/raw/ (Phase 1 verification).

    python -I scripts/inspect_sources.py                 # newest snapshot of every source
    python -I scripts/inspect_sources.py parks rainfall  # only these sources

Prints, per source: record count, geometry types, coordinate system evidence, bounding
box, every field with how often it is filled, one example record, and any dates found.
Read-only: it never changes a snapshot. Standard library only.
"""

import gzip
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xlsx_reader import xlsx_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SGT = timezone(timedelta(hours=8))


def newest(key, pattern):
    files = sorted((RAW / key).glob(pattern))
    return files[-1] if files else None


def short(v, n=160):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    s = s.replace("\n", " ").replace("\r", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def walk_coords(geom):
    """Yield every [x, y] position of a GeoJSON geometry."""
    if not geom:
        return
    if geom["type"] == "GeometryCollection":
        for g in geom.get("geometries", []):
            yield from walk_coords(g)
        return
    stack = [geom.get("coordinates")]
    while stack:
        c = stack.pop()
        if not c:
            continue
        if isinstance(c[0], (int, float)):
            yield c
        else:
            stack.extend(c)


def fmel_date(v):
    """FMEL_UPD_D looks like 20251107134512 (YYYYMMDDhhmmss) in these files."""
    s = str(v)
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", s)
    if not m:
        return None
    try:
        return datetime(int(m[1]), int(m[2]), int(m[3])).date().isoformat()
    except ValueError:
        return None


def inspect_geojson(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    feats = doc.get("features", [])
    print(f"file: {path.relative_to(ROOT).as_posix()}  ({path.stat().st_size:,} bytes)")
    print(f"top-level keys: {list(doc.keys())}")
    print(f"crs member: {short(doc.get('crs'))}")
    print(f"feature count: {len(feats)}")
    gtypes = Counter((f.get("geometry") or {}).get("type") for f in feats)
    print(f"geometry types: {dict(gtypes)}")
    xs, ys, zs, npos = [], [], 0, 0
    for f in feats:
        for c in walk_coords(f.get("geometry")):
            xs.append(c[0])
            ys.append(c[1])
            npos += 1
            if len(c) > 2:
                zs += 1
    if xs:
        print(f"positions: {npos:,}  with a Z value: {zs:,}")
        print(f"x range: {min(xs):.6f} .. {max(xs):.6f}   y range: {min(ys):.6f} .. {max(ys):.6f}")
        lonlat = 103.5 < min(xs) and max(xs) < 104.2 and 1.1 < min(ys) and max(ys) < 1.6
        print("coordinate system evidence: " + ("values are longitude/latitude degrees inside Singapore (WGS84)" if lonlat else "NOT plain lon/lat for Singapore - check"))
    keys = Counter()
    filled = Counter()
    for f in feats:
        for k, v in (f.get("properties") or {}).items():
            keys[k] += 1
            if v not in (None, "", " "):
                filled[k] += 1
    print("fields (present / non-empty):")
    for k in keys:
        vals = [(f.get("properties") or {}).get(k) for f in feats]
        distinct = len({json.dumps(v, sort_keys=True) for v in vals})
        print(f"  - {k}: {keys[k]} / {filled[k]}  distinct={distinct}  e.g. {short(next((v for v in vals if v not in (None, '')), None), 110)}")
    for k in keys:
        if k.upper() in ("FMEL_UPD_D",):
            ds = sorted(d for d in (fmel_date((f.get("properties") or {}).get(k)) for f in feats) if d)
            if ds:
                c = Counter(ds)
                print(f"  {k} as dates: {ds[0]} .. {ds[-1]}  (most common: {c.most_common(3)})")
    if feats:
        ex = dict(feats[0])
        g = ex.get("geometry") or {}
        ex["geometry"] = {"type": g.get("type"), "coordinates": short(g.get("coordinates"), 120)}
        print("example record: " + short(ex, 1500))
    return doc


def inspect_xlsx(path):
    print(f"file: {path.relative_to(ROOT).as_posix()}  ({path.stat().st_size:,} bytes)")
    names, sheets = xlsx_rows(path)
    print(f"zip members: {names}")
    for sh, rows in sheets.items():
        print(f"sheet {sh}: {len(rows)} rows (including header)")
        for r in rows[:4]:
            print("   " + short(r, 400))
        if rows:
            cols = list(rows[0].keys())
            for col in cols:
                vals = [r.get(col) for r in rows[1:] if r.get(col) not in (None, "")]
                print(f"   column {col} ({rows[0].get(col)!r}): {len(vals)} filled, {len(set(vals))} distinct")
    return sheets


def inspect_realtime_latest(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    data = doc.get("data", {})
    print(f"file: {path.relative_to(ROOT).as_posix()}  ({path.stat().st_size:,} bytes)")
    print(f"data keys: {list(data.keys())}")
    if "stations" in data:
        st = data["stations"]
        print(f"stations: {len(st)}   e.g. {short(st[0], 200)}")
        lats = [s["location"]["latitude"] for s in st]
        lons = [s["location"]["longitude"] for s in st]
        print(f"station lon range {min(lons)} .. {max(lons)}  lat range {min(lats)} .. {max(lats)}")
    for r in data.get("readings", [])[:1]:
        print(f"reading timestamp: {r.get('timestamp')}  values: {len(r.get('data', []))}  e.g. {short(r.get('data', [])[:3], 200)}")
    for k in ("readingType", "readingUnit"):
        if k in data:
            print(f"{k}: {data[k]}")
    if "records" in data:
        recs = data["records"]
        print(f"records: {len(recs)}")
        with_alerts = [r for r in recs if (r.get("item") or {}).get("readings")]
        print(f"records that contain at least one alert: {len(with_alerts)}")
        if recs:
            print(f"first record: {short(recs[0], 600)}")
            print(f"record datetimes: {recs[-1].get('datetime')} .. {recs[0].get('datetime')}")
        if with_alerts:
            print(f"example alert record: {short(with_alerts[0], 1200)}")
    return doc


def inspect_rain_days():
    files = sorted((RAW / "rainfall").glob("day_*.json.gz"))
    if not files:
        print("no cached rainfall days")
        return
    print(f"cached rainfall days: {len(files)}  ({files[0].name[4:14]} .. {files[-1].name[4:14]})")
    total_bytes = sum(f.stat().st_size for f in files)
    print(f"total size on disk: {total_bytes:,} bytes (gzip)")
    per_day = []
    stations = {}
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
        for s in d["stations"]:
            stations[s["id"]] = s
        tot = Counter()
        n = Counter()
        for r in d["readings"]:
            for v in r["data"]:
                tot[v["stationId"]] += v["value"]
                n[v["stationId"]] += 1
        per_day.append((d["date"], len(d["readings"]), d.get("complete_day"), len(d["stations"]), tot, n))
    print(f"distinct stations across the period: {len(stations)}")
    print("day         readings complete stations  island mean mm  max station mm")
    for date, nr, comp, ns, tot, n in per_day:
        vals = list(tot.values())
        mean = sum(vals) / len(vals) if vals else 0
        mx = max(tot.items(), key=lambda kv: kv[1]) if tot else ("-", 0)
        print(f"{date}  {nr:>7d} {str(comp):>8s} {ns:>8d}  {mean:>14.1f}  {mx[1]:>8.1f} ({mx[0]} {stations.get(mx[0], {}).get('name', '')})")


def section(title):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main(argv):
    want = set(argv)
    keys = sorted(p.name for p in RAW.iterdir() if p.is_dir())
    for key in keys:
        if want and key not in want:
            continue
        section(key)
        meta = newest(key, "*.metadata.json")
        if meta:
            m = json.loads(meta.read_text(encoding="utf-8"))
            print(f"dataset: {m.get('name')}  [{m.get('datasetId')}]  format {m.get('format')}")
            print(f"managed by: {m.get('managedBy')}   createdAt {m.get('createdAt')}   lastUpdatedAt {m.get('lastUpdatedAt')}")
            print(f"coverageStart {m.get('coverageStart')}   coverageEnd {m.get('coverageEnd')}   collections {m.get('collectionIds')}")
            print(f"description: {short(m.get('description') or '', 500)}")
        for pattern, fn in (("*.geojson", inspect_geojson), ("*.xlsx", inspect_xlsx), ("*_latest.json", inspect_realtime_latest)):
            f = newest(key, pattern)
            if f:
                fn(f)
        if key == "rainfall":
            inspect_rain_days()


if __name__ == "__main__":
    main(sys.argv[1:])
