#!/usr/bin/env python3
"""Phase 1: compare candidate demo neighbourhoods using only the downloaded snapshots.

    python -I scripts/phase1_neighbourhoods.py
        ranked table of URA subzones
    python -I scripts/phase1_neighbourhoods.py "YIO CHU KANG WEST" "KEBUN BAHRU"
        detail for named subzones
    python -I scripts/phase1_neighbourhoods.py --frame "KEBUN BAHRU,YIO CHU KANG WEST" "TAMAN JURONG"
        compare frames made of one or more subzones (the figures quoted in data/REPORT.md)

It counts the real assets inside each area and checks how close the area is to a current
dengue cluster, a high-Aedes area and a rainfall station. Nothing is simulated.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import (  # noqa: E402
    bbox_of,
    bbox_overlap,
    centroid_of,
    dist_m,
    dist_point_to_geometry_m,
    geometries_intersect,
    point_in_geometry,
    svy21_to_wgs84,
)
from inspect_sources import xlsx_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

# Park facility classes counted as inspection targets. This is a judgement, not something
# the dataset states: the file has no field for water. Included are facilities with a roof
# gutter, a trap, a tray, a basin or containers. Left out are car parks, notice boards, map
# boards, access points, fitness areas, foot-reflexology paths and courts. Playground
# equipment is left out too: every playground sits inside a park that is already counted.
WATER_RELEVANT_CLASSES = {
    "ALLOTMENT GARDEN",
    "THERAPEUTIC GARDEN",
    "TOILET",
    "DRINKING FOUNTAIN",
    "SHELTER",
    "BBQ PIT",
    "CAMPSITE",
    "DOG-AREA",
}

NEAR_CLUSTER_M = 150  # "close to a cluster", for counting in this report only


def newest(key, pattern="*.geojson"):
    files = sorted((RAW / key).glob(pattern))
    return files[-1] if files else None


def load_features(key):
    f = newest(key)
    if not f:
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("features", [])


def load_all():
    data = {
        k: load_features(k)
        for k in (
            "subzone_boundaries",
            "parks",
            "park_facilities",
            "park_polygons",
            "community_gardens",
            "dengue_clusters",
            "high_aedes_areas",
            "landscaped_rooftops",
            "abc_waters_completed",
        )
    }
    # PUB sensors: SVY21 easting/northing in a spreadsheet
    sensors = []
    x = newest("pub_water_level_sensors", "*.xlsx")
    if x:
        _, sheets = xlsx_rows(x)
        rows = next(iter(sheets.values()))
        for r in rows[1:]:
            try:
                lon, lat = svy21_to_wgs84(float(r["C"]), float(r["D"]))
            except (TypeError, ValueError, KeyError):
                continue
            sensors.append({"id": r.get("A"), "name": r.get("B"), "lon": lon, "lat": lat})
    data["sensors"] = sensors
    for key in ("rainfall", "air_temperature"):
        f = newest(key, "*_latest.json")
        st = json.loads(f.read_text(encoding="utf-8"))["data"]["stations"] if f else []
        data[key + "_stations"] = [
            {"id": s["id"], "name": s["name"], "lon": s["location"]["longitude"], "lat": s["location"]["latitude"]}
            for s in st
        ]
    return data


def pt(f):
    c = f["geometry"]["coordinates"]
    return c[0], c[1]


def touches(geoms, feature):
    """True when the feature's polygon overlaps or shares a boundary with any frame polygon."""
    fb = bbox_of(feature["geometry"])
    return any(bbox_overlap(bbox_of(g), fb) and geometries_intersect(g, feature["geometry"]) for g in geoms)


# --------------------------------------------------------------------------- per-subzone ranking


def subzone_stats(sz, data):
    g = sz["geometry"]
    bb = bbox_of(g)

    def inside(features):
        out = []
        for f in features:
            lon, lat = pt(f)
            if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and point_in_geometry(lon, lat, g):
                out.append(f)
        return out

    def overlapping(features):
        return [f for f in features if touches([g], f)]

    cx, cy = centroid_of(g)
    fac = inside(data["park_facilities"])
    clusters = overlapping(data["dengue_clusters"])
    rain = sorted(((dist_m(cx, cy, s["lon"], s["lat"]), s) for s in data["rainfall_stations"]), key=lambda t: t[0])
    temp = sorted(((dist_m(cx, cy, s["lon"], s["lat"]), s) for s in data["air_temperature_stations"]), key=lambda t: t[0])
    return {
        "name": sz["properties"]["SUBZONE_N"],
        "planning_area": sz["properties"]["PLN_AREA_N"],
        "area_km2": sz["properties"]["SHAPE.AREA"] / 1e6,
        "centroid": (cx, cy),
        "parks": inside(data["parks"]),
        "park_polygons": overlapping(data["park_polygons"]),
        "facilities_all": fac,
        "facilities_relevant": [f for f in fac if f["properties"]["CLASS"] in WATER_RELEVANT_CLASSES],
        "gardens": inside(data["community_gardens"]),
        "sensors": [s for s in data["sensors"] if point_in_geometry(s["lon"], s["lat"], g)],
        "clusters": clusters,
        "cluster_cases": sum(c["properties"]["CASE_SIZE"] for c in clusters),
        "aedes": overlapping(data["high_aedes_areas"]),
        "roofs": overlapping(data["landscaped_rooftops"]),
        "abc": overlapping(data["abc_waters_completed"]),
        "rain_station": rain[0] if rain else None,
        "rain_stations_3": rain[:3],
        "temp_station": temp[0] if temp else None,
    }


def real_asset_count(s):
    return len(s["parks"]) + len(s["facilities_relevant"]) + len(s["gardens"]) + len(s["sensors"])


def table(stats):
    print(
        f"{'subzone':28s} {'planning area':18s} {'km2':>5s} {'parks':>5s} {'fac*':>5s} {'gard':>5s} {'drain':>5s} {'real':>5s} | "
        f"{'clus':>4s} {'cases':>5s} {'aedes':>5s} | rain stn (m from centre)"
    )
    for s in stats:
        rs = s["rain_station"]
        print(
            f"{s['name'][:28]:28s} {s['planning_area'][:18]:18s} {s['area_km2']:5.2f} {len(s['parks']):5d} {len(s['facilities_relevant']):5d} "
            f"{len(s['gardens']):5d} {len(s['sensors']):5d} {real_asset_count(s):5d} | "
            f"{len(s['clusters']):4d} {s['cluster_cases']:5d} {len(s['aedes']):5d} | {rs[1]['id']} {rs[1]['name'][:24]} ({rs[0]:.0f})"
        )


def detail(s):
    print("\n" + "-" * 100)
    print(f"{s['name']}  (planning area {s['planning_area']}, {s['area_km2']:.2f} km2, centroid {s['centroid'][1]:.5f}, {s['centroid'][0]:.5f})")
    print(f"  parks ({len(s['parks'])}): " + "; ".join(f["properties"]["NAME"] for f in s["parks"]))
    print(f"  park polygons overlapping ({len(s['park_polygons'])}): " + "; ".join(f["properties"]["NAME"] for f in s["park_polygons"]))
    c_all = Counter(f["properties"]["CLASS"] for f in s["facilities_all"])
    print(f"  park facilities ({len(s['facilities_all'])}): " + ", ".join(f"{k} {v}" for k, v in c_all.most_common()))
    print(f"  community gardens ({len(s['gardens'])}): " + "; ".join(f["properties"]["GARDEN_NAME"] for f in s["gardens"][:40]))
    print(f"  PUB drain sensors ({len(s['sensors'])}): " + "; ".join(f"{x['id']} {x['name']}" for x in s["sensors"]))
    print(f"  landscaped rooftops (URA MP2025): {len(s['roofs'])}   ABC Waters projects: " + "; ".join(str(f["properties"].get("PROJECT_TITLE")) for f in s["abc"]))
    print(f"  dengue clusters touching ({len(s['clusters'])}, {s['cluster_cases']} cases): " + "; ".join(f"{c['properties']['LOCALITY'].strip()} [{c['properties']['CASE_SIZE']}]" for c in s["clusters"]))
    print(f"  high-Aedes areas overlapping ({len(s['aedes'])}): " + "; ".join(a["properties"]["DESCRIPTION"][:70] for a in s["aedes"]))
    print("  nearest rainfall stations: " + "; ".join(f"{st['id']} {st['name']} {d:.0f} m" for d, st in s["rain_stations_3"]))
    if s["temp_station"]:
        d, st = s["temp_station"]
        print(f"  nearest temperature/humidity station: {st['id']} {st['name']} {d:.0f} m")


# --------------------------------------------------------------------------- frames of several subzones


def frame_assets(names, data, subzones):
    """Real asset candidates inside a frame made of one or more subzones."""
    geoms = [subzones[n]["geometry"] for n in names]

    def inside(lon, lat):
        return any(point_in_geometry(lon, lat, g) for g in geoms)

    out = []
    for f in data["parks"]:
        if inside(*pt(f)):
            out.append({"kind": "park", "name": f["properties"]["NAME"], "lon": pt(f)[0], "lat": pt(f)[1]})
    for f in data["park_facilities"]:
        if f["properties"]["CLASS"] in WATER_RELEVANT_CLASSES and inside(*pt(f)):
            out.append({"kind": "facility", "cls": f["properties"]["CLASS"], "name": f["properties"]["NAME"] or "", "lon": pt(f)[0], "lat": pt(f)[1]})
    for f in data["community_gardens"]:
        if inside(*pt(f)):
            out.append({"kind": "garden", "name": f["properties"]["GARDEN_NAME"], "lon": pt(f)[0], "lat": pt(f)[1]})
    for s in data["sensors"]:
        if inside(s["lon"], s["lat"]):
            out.append({"kind": "drain sensor", "name": s["name"], "lon": s["lon"], "lat": s["lat"]})
    return geoms, out


def cluster_share_inside(cluster, geoms, n=120):
    """Share of a cluster's area that lies inside the frame, by sampling a grid."""
    bb = bbox_of(cluster["geometry"])
    tot = ins = 0
    for i in range(n):
        for j in range(n):
            x = bb[0] + (i + 0.5) / n * (bb[2] - bb[0])
            y = bb[1] + (j + 0.5) / n * (bb[3] - bb[1])
            if point_in_geometry(x, y, cluster["geometry"]):
                tot += 1
                ins += any(point_in_geometry(x, y, g) for g in geoms)
    return ins / tot if tot else 0.0


def split_clusters(geoms, data):
    """Sort the clusters that touch a frame into inside / straddling / only sharing a boundary."""
    inside, straddle, adjacent = [], [], []
    for c in data["dengue_clusters"]:
        if not touches(geoms, c):
            continue
        share = cluster_share_inside(c, geoms)
        (inside if share >= 0.9 else straddle if share >= 0.05 else adjacent).append((c, share))
    return inside, straddle, adjacent


def frame_report(names, data, subzones):
    geoms, assets = frame_assets(names, data, subzones)
    area = sum(subzones[n]["properties"]["SHAPE.AREA"] for n in names) / 1e6
    kinds = Counter(a["kind"] for a in assets)
    classes = Counter(a["cls"] for a in assets if a["kind"] == "facility")
    print("\n" + "=" * 100)
    print(" + ".join(names) + f"   ({area:.2f} km2)")
    print(
        f"  real asset candidates: {len(assets)} = parks {kinds['park']}, park facilities {kinds['facility']}, "
        f"community gardens {kinds['garden']}, drain sensor sites {kinds['drain sensor']}"
    )
    print("  facility classes: " + ", ".join(f"{k} {v}" for k, v in classes.most_common()))

    groups = split_clusters(geoms, data)
    for title, group in zip(("inside the frame", "straddling its boundary", "sharing its boundary from outside"), groups):
        print(f"  dengue clusters {title}: {len(group)}, {sum(c['properties']['CASE_SIZE'] for c, _ in group)} cases")
        for c, share in group:
            print(f"     - {c['properties']['LOCALITY'].strip()} [{c['properties']['CASE_SIZE']} cases, {share:.0%} of its area inside]")

    aedes = [a for a in data["high_aedes_areas"] if touches(geoms, a)]
    print(f"  high-Aedes areas overlapping the frame: {len(aedes)}")

    def in_any(a, feats):
        return any(point_in_geometry(a["lon"], a["lat"], f["geometry"]) for f in feats)

    in_cluster = [a for a in assets if in_any(a, data["dengue_clusters"])]
    near_cluster = [
        a for a in assets
        if any(dist_point_to_geometry_m(a["lon"], a["lat"], c["geometry"]) <= NEAR_CLUSTER_M for c in data["dengue_clusters"])
    ]
    in_aedes = [a for a in assets if in_any(a, data["high_aedes_areas"])]
    neither = [a for a in assets if a not in near_cluster and a not in in_aedes]
    print(
        f"  real assets inside a dengue cluster: {len(in_cluster)}; within {NEAR_CLUSTER_M} m of one: {len(near_cluster)}; "
        f"inside a high-Aedes area: {len(in_aedes)}; in neither: {len(neither)}"
    )
    for a in in_cluster:
        print(f"     - inside a cluster: {a['kind']} {a.get('cls', '')} {a['name']}".rstrip())

    for label, key in (("rainfall", "rainfall_stations"), ("temperature/humidity", "air_temperature_stations")):
        by_station = {}
        for a in assets:
            d, st = min(((dist_m(a["lon"], a["lat"], s["lon"], s["lat"]), s) for s in data[key]), key=lambda t: t[0])
            by_station.setdefault(f"{st['id']} {st['name']}", []).append(d)
        for k, v in sorted(by_station.items(), key=lambda kv: -len(kv[1])):
            print(f"  nearest {label} station {k}: {len(v)} assets, {min(v):.0f} to {max(v):.0f} m away")


def main(argv):
    data = load_all()
    print("loaded: " + ", ".join(f"{k} {len(v)}" for k, v in data.items()))
    if argv and argv[0] == "--frame":
        subzones = {f["properties"]["SUBZONE_N"]: f for f in data["subzone_boundaries"]}
        for spec in argv[1:]:
            frame_report([n.strip().upper() for n in spec.split(",")], data, subzones)
        return
    all_stats = [subzone_stats(sz, data) for sz in data["subzone_boundaries"]]
    if argv:
        want = {a.upper() for a in argv}
        for s in all_stats:
            if s["name"] in want:
                detail(s)
        return
    print("\n== Subzones touched by a current dengue cluster ==")
    table(sorted((s for s in all_stats if s["clusters"]), key=lambda s: (-s["cluster_cases"], -real_asset_count(s))))
    print("\n== Subzones that overlap a high-Aedes area and have the most real assets (top 25) ==")
    table(sorted((s for s in all_stats if s["aedes"]), key=lambda s: -real_asset_count(s))[:25])
    print("\nfac* = park facilities in the classes counted as inspection targets; real = parks + fac* + gardens + drain sensor sites.")
    print("clus/cases include clusters that only share the subzone's boundary. Use --frame for the exact split.")


if __name__ == "__main__":
    main(sys.argv[1:])
