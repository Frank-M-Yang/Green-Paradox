#!/usr/bin/env python3
"""Build the snapshot the site reads, from the cached sources in data/raw/. No network.

    python scripts/build_snapshot.py                    # newest cached data
    python scripts/build_snapshot.py --as-of 2026-11-21 # rebuild a past day exactly

Normally you do not run this directly: scripts/refresh.py fetches first and then calls it.

Writes:
    site/data/snapshot.js     the one snapshot file the site reads (JSON wrapped as a script,
                              so the site also opens straight from a folder)
    site/task-sheet.html      printable daily task sheet with the inspection route

What is real and what is simulated is decided here and nowhere else:
  - locations of parks, park facilities, community gardens and drain sensor sites: real
  - dengue clusters, high-Aedes areas, rainfall, temperature: real
  - "holds water" and "drain time": assumptions per asset type (config/risk_config.toml)
  - assets listed in data/demo/simulated_assets.json: simulated, and marked so
  - every inspection record: simulated. Real places only ever get simulated visit DATES,
    each recorded as "no standing water"; made-up problems (standing water, larvae) are
    attached to simulated assets only.
"""

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Canopy Care needs Python 3.11 or newer (it reads its settings with the built-in tomllib).")
import tomllib  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mapdata  # noqa: E402
import rainfall as rf  # noqa: E402
import risk  # noqa: E402
from geo import (  # noqa: E402
    area_m2,
    bbox_of,
    centroid_of,
    dist_m,
    dist_point_to_geometry_m,
    point_in_geometry,
    svy21_to_wgs84,
)
from sources import BY_KEY, LICENCE, LICENCE_URL  # noqa: E402
from xlsx_reader import xlsx_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DEMO = ROOT / "data" / "demo"
SITE = ROOT / "site"
CONFIG = ROOT / "config"
SGT = timezone(timedelta(hours=8))

# NParks facility classes that are registered as assets, and the asset type each becomes.
FACILITY_TYPES = {
    "ALLOTMENT GARDEN": "allotment_garden",
    "THERAPEUTIC GARDEN": "therapeutic_garden",
    "TOILET": "toilet",
    "DRINKING FOUNTAIN": "drinking_fountain",
    "SHELTER": "shelter",
    "BBQ PIT": "bbq_pit",
    "CAMPSITE": "campsite",
    "DOG-AREA": "dog_area",
}

# What each source is used for, in the order shown on the site.
USES = [
    ("dengue_clusters", "Active dengue clusters: map layer and location part of the score"),
    ("high_aedes_areas", "Areas with higher Aedes aegypti population: map layer and location part of the score"),
    ("rainfall", "Rain part of the score, nearest station per asset"),
    ("parks", "Real assets: parks"),
    ("park_facilities", "Real assets: park toilets, drinking fountains, BBQ pits, allotment gardens"),
    ("community_gardens", "Real assets: community gardens"),
    ("pub_water_level_sensors", "Real locations for storm drain assets"),
    ("park_polygons", "Map: park outlines"),
    ("subzone_boundaries", "Map: neighbourhood boundary"),
    ("waterbodies", "Map: canals and water bodies"),
    ("road_lines", "Map: major roads"),
    ("air_temperature", "Context only, not in the score"),
    ("relative_humidity", "Context only, not in the score"),
    ("flood_alerts", "Context only, not in the score"),
]
ESSENTIAL = {"dengue_clusters", "high_aedes_areas", "parks", "park_facilities", "community_gardens", "subzone_boundaries"}


class BuildError(Exception):
    pass


# --------------------------------------------------------------------------- reading the cache


def pick(key, as_of, suffix):
    """Newest cached file for a source dated on or before as_of. Returns (path, date) or (None, None)."""
    best = None
    for f in (RAW / key).glob(f"*{suffix}"):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", f.name)
        if m and f.name == m.group(1) + suffix and m.group(1) <= as_of and (best is None or m.group(1) > best[1]):
            best = (f, m.group(1))
    return best or (None, None)


def load_geojson(key, as_of, used):
    path, snap = pick(key, as_of, ".geojson")
    if path is None:
        if key in ESSENTIAL:
            raise BuildError(f"No cached copy of '{key}' on or before {as_of}. Run scripts/refresh.py while online first.")
        used[key] = None
        return []
    meta_path = path.with_name(snap + ".metadata.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    used[key] = {"snapshot_date": snap, "source_updated": (meta.get("lastUpdatedAt") or "")[:10]}
    return json.loads(path.read_text(encoding="utf-8")).get("features", [])


def load_sensors(as_of, used):
    path, snap = pick("pub_water_level_sensors", as_of, ".xlsx")
    if path is None:
        used["pub_water_level_sensors"] = None
        return []
    meta_path = path.with_name(snap + ".metadata.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    used["pub_water_level_sensors"] = {"snapshot_date": snap, "source_updated": (meta.get("lastUpdatedAt") or "")[:10]}
    _, sheets = xlsx_rows(path)
    out = []
    for r in next(iter(sheets.values()))[1:]:
        try:
            lon, lat = svy21_to_wgs84(float(r["C"]), float(r["D"]))  # SVY21 easting, northing
        except (TypeError, ValueError, KeyError):
            continue
        out.append({"id": (r.get("A") or "").strip(), "name": (r.get("B") or "").strip(), "lon": lon, "lat": lat})
    return out


def load_latest(key, as_of, used):
    path, snap = pick(key, as_of, "_latest.json")
    if path is None:
        used[key] = None
        return None
    used[key] = {"snapshot_date": snap, "source_updated": ""}
    return json.loads(path.read_text(encoding="utf-8")).get("data", {})


# --------------------------------------------------------------------------- names


def tidy_name(name):
    """Source names are upper case with abbreviations: 'SERENADE WALK PG' -> 'Serenade Walk Playground'."""
    t = (name or "").replace("`", "'").strip().title()
    t = re.sub(r"'S\b", "'s", t)
    t = re.sub(r"\bPg\b", "Playground", t)
    t = re.sub(r"\bPk\b", "Park", t)
    return t


def pt(feature):
    c = feature["geometry"]["coordinates"]
    return c[0], c[1]


def task_sheet_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {risk.MONTHS[d.month - 1]} {d.year}"


# --------------------------------------------------------------------------- assets


def real_assets(src, frame, types, show_garden_names):
    def inside(lon, lat):
        return any(point_in_geometry(lon, lat, g) for g in frame)

    park_polys = {f["properties"]["NAME"]: f for f in src["park_polygons"]}
    assets = []

    for f in src["parks"]:
        lon, lat = pt(f)
        if not inside(lon, lat):
            continue
        raw = f["properties"]["NAME"]
        poly = park_polys.get(raw)
        code = poly["properties"].get("L_CODE") if poly else None
        aid = "pk-" + (code.lower() if code else re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-"))
        assets.append({"id": aid, "name": tidy_name(raw), "type": "park", "source": "parks", "lon": lon, "lat": lat})

    for f in src["park_facilities"]:
        typ = FACILITY_TYPES.get(f["properties"]["CLASS"])
        lon, lat = pt(f)
        if not typ or not inside(lon, lat):
            continue
        park = next((tidy_name(n) for n, p in park_polys.items() if point_in_geometry(lon, lat, p["geometry"])), None)
        label = types[typ]["label"]
        assets.append({
            "id": "pf-" + f["properties"]["UNIQUEID"][:8].lower(),
            "name": f"{label}, {park}" if park else label,
            "type": typ, "source": "park_facilities", "lon": lon, "lat": lat,
        })

    for f in src["community_gardens"]:
        lon, lat = pt(f)
        if not inside(lon, lat):
            continue
        gid = f["properties"]["GARDENID"]
        name = re.sub(r"\s+", " ", f["properties"]["GARDEN_NAME"] or "").strip()
        assets.append({
            "id": f"cg-{gid}",
            "name": name if show_garden_names and name else f"Community garden {gid}",
            "type": "community_garden", "source": "community_gardens", "lon": lon, "lat": lat,
        })

    for s in src["sensors"]:
        if inside(s["lon"], s["lat"]):
            assets.append({
                "id": "dr-" + s["id"].lower(),
                "name": f"Storm drain at {s['name']}",
                "type": "storm_drain", "source": "pub_water_level_sensors", "lon": s["lon"], "lat": s["lat"],
                "location_note": f"Real location: PUB water level sensor site {s['id']}.",
            })
    for a in assets:
        a["simulated"] = False
    return assets


def simulated_assets():
    path = DEMO / "simulated_assets.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for a in doc["assets"]:
        b = dict(a)
        b["simulated"] = True
        b["source"] = "simulated"
        out.append(b)
    return out


def apply_type_assumptions(asset, types):
    t = types[asset["type"]]
    own = False
    for key in ("holds_water", "drain_time_h", "water_source", "flushable"):
        if key in asset:
            own = own or asset[key] != t[key]
        else:
            asset[key] = t[key]
    asset["own_properties"] = own


def locate(asset, src):
    """Attach the nearest dengue cluster (if close) and the high-Aedes area the asset sits in."""
    best = None
    for c in src["dengue_clusters"]:
        d = dist_point_to_geometry_m(asset["lon"], asset["lat"], c["geometry"])
        if best is None or d < best[0]:
            best = (d, c)
    asset["cluster"] = None
    if best and best[0] <= 400:
        p = best[1]["properties"]
        asset["cluster"] = {"locality": p["LOCALITY"].strip(), "cases": p["CASE_SIZE"], "inside": best[0] == 0, "dist_m": round(best[0])}
    asset["aedes"] = next(
        (a["properties"]["DESCRIPTION"].strip() for a in src["high_aedes_areas"] if point_in_geometry(asset["lon"], asset["lat"], a["geometry"])),
        None,
    )


def spread_overlapping(assets, min_gap_m=26):
    """Two assets at the same published point would hide each other on the map.

    Shift the later one sideways until it is clear. Only the drawing position moves:
    distances and the location part of the score use the published coordinates.
    """
    placed = []
    for a in sorted(assets, key=lambda a: a["id"]):
        x, y, step = a["x"], a["y"], 0
        while any(abs(x - px) < min_gap_m and abs(y - py) < min_gap_m for px, py in placed):
            step += 1
            x = a["x"] + min_gap_m * ((step + 1) // 2) * (1 if step % 2 else -1)
        a["x"], a["y"] = x, y
        placed.append((x, y))


# --------------------------------------------------------------------------- simulated inspection history

SIM_NOTES_CLEAR = ["Dry.", "No water seen.", "Drains freely.", "Checked, nothing found.", ""]
SIM_NOTES_WATER = {
    "pot_tray": ["Tray full after watering.", "Water in tray, emptied and wiped.", "Tray refilled since last visit."],
    "planter_box": ["Weep hole blocked with roots.", "Water pooling on soil surface."],
    "rain_barrel": ["Lid left off.", "Mesh torn at one corner.", "Overflow outlet dripping into a pail."],
    "storm_drain": ["Leaf litter holding water.", "Silt at the outlet.", "Pooled water in a low section."],
    "roof_garden": ["Outlet strainer blocked with leaves.", "Ponding near the roof outlet."],
}
SIM_ACTIONS = {
    "pot_tray": [["emptied"], ["emptied"], ["emptied", "reported"]],
    "planter_box": [["cleared"], ["cleared", "drained"], ["reported"]],
    "rain_barrel": [["covered"], ["covered", "repaired"], ["reported"]],
    "storm_drain": [["cleared"], ["cleared", "drained"], ["reported"]],
    "roof_garden": [["cleared"], ["cleared", "repaired"], ["reported"]],
}


def simulated_history(asset, seed, story):
    """A plausible, repeatable inspection history. Entirely fictional.

    Returns records with days_ago (0 = the snapshot day). A real place only gets visit dates,
    each recorded as "no standing water" with no note. Made-up problems (standing water,
    larvae) are given to simulated assets and to nothing else.
    """
    if asset["id"] in story:
        return [dict(r) for r in story[asset["id"]]]
    rng = random.Random(int(hashlib.sha256(f"{seed}:{asset['id']}".encode()).hexdigest()[:12], 16))
    profile = rng.choices(["on_time", "slipping", "neglected", "never"], weights=[55, 30, 10, 5])[0]
    if profile == "never":
        return []
    last = {"on_time": rng.randint(0, 6), "slipping": rng.randint(8, 13), "neglected": rng.randint(15, 30)}[profile]
    days = [last]
    for _ in range(rng.randint(1, 4)):
        days.append(days[-1] + rng.randint(5, 12))
    records = []
    for d in days:
        rec = {"days_ago": d, "standing_water": False, "larvae": False, "actions": [], "note": rng.choice(SIM_NOTES_CLEAR)}
        if not asset["simulated"]:
            rec["note"] = ""  # nothing is said about a real place beyond "visited on this date, no standing water"
        if asset["simulated"] and asset["holds_water"] and rng.random() < 0.45:
            rec["standing_water"] = True
            rec["larvae"] = rng.random() < 0.3
            rec["actions"] = list(rng.choice(SIM_ACTIONS.get(asset["type"], [["cleared"]])))
            rec["note"] = rng.choice(SIM_NOTES_WATER.get(asset["type"], ["Standing water found."]))
        records.append(rec)
    return records


# --------------------------------------------------------------------------- rain per scenario


def scenario_windows(demo_cfg, as_of, lookback):
    yesterday = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
    out = []
    for sc in demo_cfg["scenarios"]:
        end = sc.get("end_date") or yesterday
        # The day-by-day replay scores each day of the window with its own look-back, so it
        # reads rain from before the window too: `lookback - 1` earlier days.
        longer = rf.window_dates(end, 2 * lookback - 1)
        out.append({"id": sc["id"], "label": sc["label"], "summary": sc.get("summary", ""), "replayed": bool(sc.get("end_date")),
                    "days": longer[lookback - 1:], "earlier_days": longer[: lookback - 1]})
    return out


def daily_replay(asset, rows, station, lookback, risk_cfg):
    """The score as this script would have given it at the end of each day of the window.

    Same calculation as the snapshot itself, run once per day with that day's look-back:
    rain up to and including the day, and only the inspections made by then. The last entry
    is the snapshot day and must equal the asset's normal score. Clusters and high-Aedes
    areas are today's on every day, because NEA publishes no history of them.

    rows  the station's days, `lookback - 1` earlier days followed by the window.
    Returns one (total, inspection part, rain part) per day of the window.
    """
    n = lookback
    out = []
    for i in range(n):
        before = n - 1 - i                           # how many days before the snapshot day
        days = rows[i:i + n] if rows else []
        clears = {n - (r["days_ago"] - before) for r in asset["history"]
                  if 0 <= r["days_ago"] - before <= n and risk.removed_water(r)}
        rain = risk.rain_part(asset, days, clears, station, risk_cfg)
        past = [r for r in asset["history"] if r["days_ago"] >= before]
        last = past[0] if past else None
        insp = risk.inspection_part(last, last["days_ago"] - before if last else None, risk_cfg)
        score, _ = risk.total([asset["parts"]["water"], insp, rain, asset["parts"]["location"]], risk_cfg)
        out.append((score, insp, rain))
    return out


def nearest_station(asset, stations, table):
    best = None
    for sid, st in stations.items():
        if not rf.usable(table[sid]):
            continue
        d = dist_m(asset["lon"], asset["lat"], st["lon"], st["lat"])
        if best is None or d < best[0]:
            best = (d, st)
    if best is None:
        return None
    return {"id": best[1]["id"], "name": best[1]["name"], "dist_m": round(best[0])}


# --------------------------------------------------------------------------- map layers


def label_point(geom, view):
    cx, cy = centroid_of(geom)
    x, y = view.xy(cx, cy)
    return round(x), round(y)


def build_map(src, frame_feats, view):
    def polys(features, tol):
        return "".join(mapdata.polygon_path(f["geometry"], view, tol) for f in features if mapdata.touches_view(bbox_of(f["geometry"]), view))

    frame_names = {f["properties"]["SUBZONE_N"] for f in frame_feats}
    context = [f for f in src["subzone_boundaries"] if f["properties"]["SUBZONE_N"] not in frame_names and mapdata.touches_view(bbox_of(f["geometry"]), view)]
    out = {"w": round(view.width), "h": round(view.height)}
    out["frame"] = []
    for f in frame_feats:
        x, y = label_point(f["geometry"], view)
        out["frame"].append({"name": tidy_name(f["properties"]["SUBZONE_N"]), "d": mapdata.polygon_path(f["geometry"], view, 1.5), "x": x, "y": y})
    out["context"] = polys(context, 2.5)
    out["context_labels"] = []
    for f in context:
        cx, cy = centroid_of(f["geometry"])
        if view.contains(cx, cy):
            x, y = view.xy(cx, cy)
            if 250 < x < view.width - 250 and 120 < y < view.height - 120:
                out["context_labels"].append({"t": tidy_name(f["properties"]["SUBZONE_N"]), "x": round(x), "y": round(y)})
    parks = [f for f in src["park_polygons"] if mapdata.touches_view(bbox_of(f["geometry"]), view)]
    out["parks"] = polys(parks, 1.5)
    out["park_labels"] = []
    for f in parks:
        if area_m2(f["geometry"]) >= 40_000:
            cx, cy = centroid_of(f["geometry"])
            if view.contains(cx, cy):
                x, y = view.xy(cx, cy)
                out["park_labels"].append({"t": tidy_name(f["properties"]["NAME"]), "x": round(x), "y": round(y)})
    out["water"] = polys(src["waterbodies"], 1.5)
    out["roads"] = "".join(
        mapdata.line_path(f["geometry"], view, 1.5)
        for f in src["road_lines"]
        if f["properties"].get("TYPE") != "UNDERGROUND" and mapdata.touches_view(bbox_of(f["geometry"]), view)
    )
    out["aedes"] = polys(src["high_aedes_areas"], 2.0)
    out["aedes_count"] = sum(1 for f in src["high_aedes_areas"] if mapdata.touches_view(bbox_of(f["geometry"]), view))
    out["clusters"] = []
    for f in src["dengue_clusters"]:
        if not mapdata.touches_view(bbox_of(f["geometry"]), view):
            continue
        p = f["properties"]
        x, y = label_point(f["geometry"], view)
        out["clusters"].append({
            "d": mapdata.polygon_path(f["geometry"], view, 1.5), "x": x, "y": y,
            "locality": p["LOCALITY"].strip(), "cases": p["CASE_SIZE"],
            "homes": (p.get("HOMES") or "").strip(), "public_places": (p.get("PUBLIC_PLACES") or "").strip(),
            "construction_sites": (p.get("CONSTRUCTION_SITES") or "").strip(),
        })
    return out


# --------------------------------------------------------------------------- main build


def load_config():
    risk_cfg = tomllib.loads((CONFIG / "risk_config.toml").read_text(encoding="utf-8"))
    demo_cfg = tomllib.loads((CONFIG / "demo_config.toml").read_text(encoding="utf-8"))
    return risk_cfg, demo_cfg


def newest_dengue_date(limit):
    _, snap = pick("dengue_clusters", limit, ".geojson")
    return snap


def build(as_of=None, refresh_status=None, quiet=False):
    risk_cfg, demo_cfg = load_config()
    types = risk_cfg["asset_types"]
    today = datetime.now(SGT).date().isoformat()
    if not as_of:
        as_of = newest_dengue_date(today)
        if not as_of:
            raise BuildError("Nothing cached yet. Run scripts/refresh.py while online first.")

    used = {}
    src = {k: load_geojson(k, as_of, used) for k in (
        "subzone_boundaries", "parks", "park_polygons", "park_facilities", "community_gardens",
        "dengue_clusters", "high_aedes_areas", "waterbodies", "road_lines")}
    src["sensors"] = load_sensors(as_of, used)
    temp = load_latest("air_temperature", as_of, used)
    hum = load_latest("relative_humidity", as_of, used)
    flood = load_latest("flood_alerts", as_of, used)

    # ---- the demo area and the map view around it
    nb = demo_cfg["neighbourhood"]
    by_name = {f["properties"]["SUBZONE_N"]: f for f in src["subzone_boundaries"]}
    missing = [n for n in nb["subzones"] if n not in by_name]
    if missing:
        raise BuildError(f"Subzone(s) not found in the boundary file: {', '.join(missing)}")
    frame_feats = [by_name[n] for n in nb["subzones"]]
    frame = [f["geometry"] for f in frame_feats]
    boxes = [bbox_of(g) for g in frame]
    lon0, lat0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    lon1, lat1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    probe = mapdata.View(lon0, lat0, lon1, lat1)
    m = nb["map_margin_m"]
    view = mapdata.View(lon0 - m / probe.kx, lat0 - m / probe.ky, lon1 + m / probe.kx, lat1 + m / probe.ky)

    # ---- assets
    assets = real_assets(src, frame, types, demo_cfg["display"]["show_garden_names"]) + simulated_assets()
    ids = [a["id"] for a in assets]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise BuildError(f"Duplicate asset id(s): {', '.join(sorted(dupes))}")
    story_path = DEMO / "story.json"
    story = json.loads(story_path.read_text(encoding="utf-8")).get("histories", {}) if story_path.exists() else {}
    seed = demo_cfg.get("history", {}).get("seed", "canopy")
    as_of_date = date.fromisoformat(as_of)
    for a in assets:
        if a["type"] not in types:
            raise BuildError(f"Asset {a['id']} has unknown type '{a['type']}'")
        apply_type_assumptions(a, types)
        locate(a, src)
        x, y = view.xy(a["lon"], a["lat"])
        a["x"], a["y"] = round(x), round(y)
        hist = sorted(simulated_history(a, seed, story), key=lambda r: r["days_ago"])
        a["history"] = hist
        a["parts"] = {"water": risk.water_part(a, risk_cfg), "location": risk.location_part(a, risk_cfg)}
        last = hist[0] if hist else None
        a["parts"]["inspection"] = risk.inspection_part(last, last["days_ago"] if last else None, risk_cfg)

    spread_overlapping(assets)

    # ---- rain, per scenario
    lookback = risk_cfg["rain"]["lookback_days"]
    scenarios = scenario_windows(demo_cfg, as_of, lookback)
    # Many assets share the same explanation (same type, same station), so each distinct
    # part is stored once and assets refer to it by position. This keeps the page small.
    pool, pool_index = [], {}

    def intern(part):
        key = json.dumps(part, sort_keys=True)
        if key not in pool_index:
            pool_index[key] = len(pool)
            pool.append(part)
        return pool_index[key]

    # The day-by-day replay repeats a small set of (points, reason) pairs many times over, so
    # each pair and each 14-day run of them is stored once as well.
    states, state_index, series, series_index = [], {}, [], {}

    def state_id(part):
        key = (part["points"], part["short"])
        if key not in state_index:
            state_index[key] = len(states)
            states.append([part["points"], part["short"]])
        return state_index[key]

    def series_id(parts):
        key = tuple(state_id(p) for p in parts)
        if key not in series_index:
            series_index[key] = len(series)
            series.append(list(key))
        return series_index[key]

    warnings = []
    current = {}  # station id -> name and position in the newest window
    for sc in scenarios:
        stations, table, missing_days = rf.station_table(RAW, sc["days"], risk_cfg["rain"]["min_day_coverage"])
        _, longer, missing_earlier = rf.station_table(RAW, sc["earlier_days"] + sc["days"], risk_cfg["rain"]["min_day_coverage"])
        missing_earlier = [d for d in missing_earlier if d in sc["earlier_days"]]
        # A gauge keeps its ID when NEA renames it (S08 was "Upper Thomson Road" in 2025).
        # Show today's name for the same gauge so one station does not look like two.
        for sid, st in stations.items():
            now = current.get(sid)
            if now is None:
                if not sc["replayed"]:
                    current[sid] = st
            elif dist_m(st["lon"], st["lat"], now["lon"], now["lat"]) < 500:
                st["name"] = now["name"]
        if missing_days:
            warnings.append(f"Scenario '{sc['id']}': no cached rainfall for {len(missing_days)} of {len(sc['days'])} days ({missing_days[0]} .. {missing_days[-1]}).")
        if missing_earlier:
            warnings.append(f"Scenario '{sc['id']}': the day-by-day replay has no cached rainfall for {len(missing_earlier)} of the "
                            f"{len(sc['earlier_days'])} days before the window ({missing_earlier[0]} .. {missing_earlier[-1]}), "
                            "so its first days count that rain as unknown.")
        sc["missing_days"] = len(missing_days)
        # For each day of the window: how many days of its own look-back have no cached rain at all.
        gone = set(missing_days) | set(missing_earlier)
        both = sc["earlier_days"] + sc["days"]
        sc["replay_gaps"] = [sum(1 for d in both[i:i + lookback] if d in gone) for i in range(lookback)]
        used_stations = {}
        for a in assets:
            st = nearest_station(a, stations, table)
            n = len(sc["days"])
            clears = {n - r["days_ago"] for r in a["history"] if r["days_ago"] <= n and risk.removed_water(r)}
            part = risk.rain_part(a, table[st["id"]] if st else [], clears, st, risk_cfg)
            part["station"] = st["id"] if st else None
            a.setdefault("rain", {})[sc["id"]] = intern(part)
            score, band = risk.total([a["parts"]["water"], a["parts"]["inspection"], part, a["parts"]["location"]], risk_cfg)
            a.setdefault("score", {})[sc["id"]] = score
            replay = daily_replay(a, longer[st["id"]] if st else [], st, lookback, risk_cfg)
            if replay[-1][0] != score:
                raise BuildError(f"Day-by-day replay of {a['id']} in '{sc['id']}' ends at {replay[-1][0]}, not at its score {score}.")
            a.setdefault("daily", {})[sc["id"]] = [r[0] for r in replay]
            a.setdefault("daily_rain", {})[sc["id"]] = series_id([r[2] for r in replay])
            a["daily_insp"] = series_id([r[1] for r in replay])       # the same in every scenario: it does not depend on rain
            if st:
                used_stations[st["id"]] = stations[st["id"]]
        sc["stations"] = []
        for sid, st in sorted(used_stations.items()):
            x, y = view.xy(st["lon"], st["lat"])
            rows = table[sid]
            sc["stations"].append({
                "id": sid, "name": st["name"], "x": round(x), "y": round(y),
                "assets": sum(1 for a in assets if pool[a["rain"][sc["id"]]].get("station") == sid),
                "mm": [r["mm"] for r in rows], "max60": [r["max60"] for r in rows],
                "flush": [bool(r["mm"] is not None and risk.is_flush_day(r, risk_cfg)) for r in rows],
            })

    # ---- map
    map_layers = build_map(src, frame_feats, view)
    # The neighbourhood itself inside the map view. The site opens zoomed to this box; the
    # margin around it is context that is reached by zooming out.
    fx0, fy0 = view.xy(lon0, lat1)
    fx1, fy1 = view.xy(lon1, lat0)
    map_layers["focus"] = [round(fx0), round(fy0), round(fx1), round(fy1)]
    # A small outline of Singapore with the neighbourhood marked, from the same subzone file.
    map_layers["locator"] = mapdata.island_outline([f["geometry"] for f in src["subzone_boundaries"]], (lon0, lat0, lon1, lat1))
    stations_now = {}
    for sc in scenarios[:1]:
        for s in sc["stations"]:
            stations_now[s["id"]] = {"id": s["id"], "name": s["name"], "x": s["x"], "y": s["y"]}
    map_layers["stations"] = list(stations_now.values())

    # ---- context readings (not in the score)
    context = {}
    cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    for label, doc in (("temperature", temp), ("humidity", hum)):
        if doc and doc.get("stations") and doc.get("readings"):
            st = min(doc["stations"], key=lambda s: dist_m(cx, cy, s["location"]["longitude"], s["location"]["latitude"]))
            val = next((v["value"] for v in doc["readings"][0]["data"] if v["stationId"] == st["id"]), None)
            if val is not None:
                context[label] = {"value": val, "unit": doc.get("readingUnit"), "station": f"{st['id']} {st['name']}",
                                  "at": doc["readings"][0]["timestamp"]}
    if flood is not None:
        context["flood_alerts"] = sum(len((r.get("item") or {}).get("readings") or []) for r in flood.get("records", [])[:1])

    # ---- sources shown on the site
    counts = {
        "dengue_clusters": f"{len(map_layers['clusters'])} clusters in the map view",
        "high_aedes_areas": f"{map_layers['aedes_count']} areas in the map view",
        "parks": f"{sum(1 for a in assets if a['source'] == 'parks')} in the demo area",
        "park_facilities": f"{sum(1 for a in assets if a['source'] == 'park_facilities')} in the demo area",
        "community_gardens": f"{sum(1 for a in assets if a['source'] == 'community_gardens')} in the demo area",
        "pub_water_level_sensors": f"{sum(1 for a in assets if a['source'] == 'pub_water_level_sensors')} sites in the demo area",
    }
    sources = []
    real = scenarios[0]
    for key, use in USES:
        info = used.get(key)
        meta = BY_KEY[key]
        row = {"key": key, "title": meta["title"], "agency": meta["agency"], "use": use,
               "url": f"https://data.gov.sg/datasets/{meta['dataset_id']}/view", "detail": counts.get(key, "")}
        if key == "rainfall":
            row["snapshot_date"] = real["days"][-1]
            row["source_updated"] = ""
            row["detail"] = (f"5-minute readings, {task_sheet_date(real['days'][0])} to {task_sheet_date(real['days'][-1])}, stations "
                             + ", ".join(s["id"] for s in real["stations"]))
            if real["missing_days"]:
                row["detail"] += f". {real['missing_days']} of the {len(real['days'])} days could not be fetched and count as unknown"
        elif info is None:
            row["snapshot_date"] = None
            row["detail"] = "not available in the cache"
        else:
            row.update(info)
        if refresh_status and key in refresh_status:
            row["refresh"] = refresh_status[key]
        sources.append(row)

    # ---- assemble
    out_assets = []
    for a in sorted(assets, key=lambda a: a["id"]):
        rec = {
            "id": a["id"], "name": a["name"], "type": a["type"], "simulated": a["simulated"], "source": a["source"],
            "lon": round(a["lon"], 5), "lat": round(a["lat"], 5), "x": a["x"], "y": a["y"],
            "holds_water": a["holds_water"], "drain_time_h": a["drain_time_h"], "water_source": a["water_source"],
            "flushable": a["flushable"], "own_properties": a["own_properties"],
            "cluster": a["cluster"], "aedes_area": a["aedes"],
            "water": intern(a["parts"]["water"]), "location": intern(a["parts"]["location"]),
            "rain": a["rain"], "baseline_score": a["score"],
            "daily": a["daily"], "daily_rain": a["daily_rain"], "daily_insp": a["daily_insp"],
            "last_inspection": (as_of_date - timedelta(days=a["history"][0]["days_ago"])).isoformat() if a["history"] else None,
            "inspection_check": [a["parts"]["inspection"]["points"], a["parts"]["inspection"]["state"]],
            "inspections": [
                {"date": (as_of_date - timedelta(days=r["days_ago"])).isoformat(), "standing_water": r["standing_water"],
                 "larvae": r["larvae"], "actions": r["actions"], "note": r.get("note", "")}
                for r in a["history"]
            ],
        }
        for extra in ("note", "location_note"):
            if a.get(extra):
                rec[extra] = a[extra]
        out_assets.append(rec)

    snapshot = {
        "meta": {
            "app": "Canopy Care",
            "as_of": as_of,
            "generated_at": datetime.now(SGT).isoformat(timespec="seconds"),
            "neighbourhood": nb["name"],
            "subzones": [tidy_name(n) for n in nb["subzones"]],
            "licence": LICENCE, "licence_url": LICENCE_URL,
            "public_url": demo_cfg.get("site", {}).get("public_url", ""),
            "daily_capacity": demo_cfg["tasks"]["daily_capacity"],
            "page_weight_bytes": 0,
            "warnings": warnings,
        },
        "config": {k: v for k, v in risk_cfg.items() if k != "asset_types"},
        "types": {k: {"label": v["label"], "look_for": v["look_for"]} for k, v in types.items()},
        "actions": risk.ACTIONS,
        "removing_actions": sorted(risk.REMOVING_ACTIONS),
        "scenarios": [
            {"id": s["id"], "label": s["label"], "summary": s["summary"], "replayed": s["replayed"],
             "from": s["days"][0], "to": s["days"][-1], "dates": s["days"], "missing_days": s["missing_days"],
             "replay_gaps": s["replay_gaps"], "stations": s["stations"]}
            for s in scenarios
        ],
        "parts": pool,
        # Day-by-day replay. "states" are [points, reason]; a "series" is one state per day of the
        # window. Assets point at a series for rain (per scenario) and one for inspection.
        "daily": {"states": states, "series": series},
        "assets": out_assets,
        "map": map_layers,
        "context": context,
        "sources": sources,
    }
    return snapshot, assets, scenarios, view, risk_cfg, demo_cfg


PAGE_FILES = ["index.html", "style.css", "app.js", "qr.js", "data/snapshot.js"]


def write_snapshot(snapshot):
    """Write the one snapshot file the site reads, with the measured page weight filled in.

    It is a script (window.CANOPY_SNAPSHOT = {...};) and not a .json file because a page opened
    from a folder is not allowed to fetch a file next to it, but it may load a script.
    Everything after the "=" up to the final ";" is plain JSON.
    """
    out_dir = SITE / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    js_path = out_dir / "snapshot.js"
    for _ in range(3):  # the weight is part of the file it measures, so settle it in a few passes
        body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
        js_path.write_text("window.CANOPY_SNAPSHOT=" + body + ";\n", encoding="utf-8")
        weight = sum((SITE / f).stat().st_size for f in PAGE_FILES if (SITE / f).exists())
        if snapshot["meta"]["page_weight_bytes"] == weight:
            break
        snapshot["meta"]["page_weight_bytes"] = weight
    return js_path.stat().st_size, snapshot["meta"]["page_weight_bytes"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the site snapshot from the cached sources.")
    ap.add_argument("--as-of", help="snapshot date YYYY-MM-DD (default: the newest cached dengue cluster file)")
    args = ap.parse_args(argv)
    try:
        snapshot, assets, scenarios, view, risk_cfg, demo_cfg = build(args.as_of)
    except BuildError as e:
        print(f"Cannot build: {e}")
        return 1
    import task_sheet

    js_bytes, weight = write_snapshot(snapshot)
    sheet = task_sheet.write(snapshot, SITE / "task-sheet.html")
    print(f"Snapshot for {snapshot['meta']['as_of']}: {len(snapshot['assets'])} assets "
          f"({sum(1 for a in snapshot['assets'] if a['simulated'])} simulated), {len(snapshot['scenarios'])} scenarios.")
    print(f"  site/data/snapshot.js  {js_bytes:,} bytes")
    print(f"  site/task-sheet.html   {sheet:,} bytes")
    print(f"  page weight (everything index.html loads): {weight:,} bytes")
    for w in snapshot["meta"]["warnings"]:
        print("  WARNING: " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
