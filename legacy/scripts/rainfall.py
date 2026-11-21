"""Daily rainfall per station, read from the cached 5-minute day files. Standard library only."""

import gzip
import json
from datetime import date, timedelta
from pathlib import Path

READINGS_PER_DAY = 288  # 5-minute totals


def day_file(raw_dir, day):
    return Path(raw_dir) / "rainfall" / f"day_{day}.json.gz"


def window_dates(end_day, n):
    """The n calendar days ending on end_day (inclusive), oldest first, as ISO strings."""
    end = date.fromisoformat(end_day)
    return [(end - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]


def read_day(raw_dir, day):
    f = day_file(raw_dir, day)
    if not f.exists():
        return None
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def summarise_day(doc):
    """Per station: total mm, heaviest 60 minutes, and share of the day's readings present."""
    series = {}
    for r in doc["readings"]:
        for v in r["data"]:
            if v.get("value") is None:
                continue
            series.setdefault(v["stationId"], []).append(float(v["value"]))
    out = {}
    for sid, vals in series.items():
        best = 0.0
        run = sum(vals[:12])
        best = run
        for i in range(12, len(vals)):
            run += vals[i] - vals[i - 12]
            if run > best:
                best = run
        out[sid] = {"mm": round(sum(vals), 1), "max60": round(best, 1), "cov": round(len(vals) / READINGS_PER_DAY, 3)}
    return out


def station_table(raw_dir, days, min_coverage):
    """Read a window of days.

    Returns (stations, table, missing_days):
      stations      {id: {"id", "name", "lon", "lat"}} for every station seen in the window
      table         {id: [{"date", "mm", "max60", "cov"} for each day]}; mm and max60 are None
                    when the station reported too few readings that day to trust a total
      missing_days  days with no cached file at all
    """
    stations, per_day, missing = {}, [], []
    for day in days:
        doc = read_day(raw_dir, day)
        if doc is None:
            missing.append(day)
            per_day.append({})
            continue
        for s in doc["stations"]:
            stations[s["id"]] = {"id": s["id"], "name": s["name"], "lon": s["location"]["longitude"], "lat": s["location"]["latitude"]}
        per_day.append(summarise_day(doc))
    table = {}
    for sid in stations:
        rows = []
        for day, summ in zip(days, per_day):
            s = summ.get(sid)
            if s is None or s["cov"] < min_coverage:
                rows.append({"date": day, "mm": None, "max60": None, "cov": s["cov"] if s else 0.0})
            else:
                rows.append({"date": day, **s})
        table[sid] = rows
    return stations, table, missing


def usable(rows, min_days_share=0.7):
    """A station is usable for a window when most of its days have a trusted total."""
    good = sum(1 for r in rows if r["mm"] is not None)
    return good >= len(rows) * min_days_share
