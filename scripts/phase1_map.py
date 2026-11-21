#!/usr/bin/env python3
"""Phase 1: draw a candidate neighbourhood straight from the GeoJSON snapshots (no basemap).

    python -I scripts/phase1_map.py "KEBUN BAHRU,YIO CHU KANG WEST,SEMBAWANG HILLS" data/phase1_map_ang_mo_kio.svg
    python -I scripts/phase1_map.py "TAMAN JURONG" data/phase1_map_taman_jurong.svg

Everything on the map is real published data. Nothing is simulated at this stage.
The output is a static SVG, so it opens offline in any browser.
"""

import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase1_neighbourhoods as p1  # noqa: E402
from geo import M_PER_DEG_LAT, bbox_of, bbox_overlap, centroid_of, m_per_deg_lon, point_in_geometry, polygons_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARGIN_M = 750
WIDTH = 860


def main(argv):
    names = [n.strip().upper() for n in argv[0].split(",")]
    out = Path(argv[1])
    data = p1.load_all()
    data["waterbodies"] = p1.load_features("waterbodies")
    subzones = {f["properties"]["SUBZONE_N"]: f for f in data["subzone_boundaries"]}
    chosen = [subzones[n] for n in names]

    boxes = [bbox_of(f["geometry"]) for f in chosen]
    lon0, lat0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    lon1, lat1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    latc = (lat0 + lat1) / 2
    kx, ky = m_per_deg_lon(latc), M_PER_DEG_LAT
    lon0 -= MARGIN_M / kx
    lon1 += MARGIN_M / kx
    lat0 -= MARGIN_M / ky
    lat1 += MARGIN_M / ky
    view = (lon0, lat0, lon1, lat1)
    w_m, h_m = (lon1 - lon0) * kx, (lat1 - lat0) * ky
    scale = WIDTH / w_m  # pixels per metre
    height = round(h_m * scale)

    def xy(lon, lat):
        return (lon - lon0) * kx * scale, (lat1 - lat) * ky * scale

    def path(geom):
        d = []
        for poly in polygons_of(geom):
            for ring in poly:
                pts = [xy(c[0], c[1]) for c in ring]
                d.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z")
        return " ".join(d)

    def in_view(f):
        return bbox_overlap(view, bbox_of(f["geometry"]))

    def pt_in_view(lon, lat):
        return lon0 <= lon <= lon1 and lat0 <= lat <= lat1

    def in_chosen(lon, lat):
        return any(point_in_geometry(lon, lat, c["geometry"]) for c in chosen)

    s = []
    add = s.append
    legend_h = 250
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height + legend_h}" width="{WIDTH}" height="{height + legend_h}" font-family="system-ui, Segoe UI, Arial, sans-serif">')
    add("<title>Candidate demo neighbourhood: " + escape(" + ".join(names)) + "</title>")
    add(f'<rect width="{WIDTH}" height="{height + legend_h}" fill="#ffffff"/>')
    add(f'<clipPath id="clip"><rect width="{WIDTH}" height="{height}"/></clipPath>')
    add('<g clip-path="url(#clip)">')
    add(f'<rect width="{WIDTH}" height="{height}" fill="#f4f2ea"/>')

    # neighbouring subzones (context only)
    for f in data["subzone_boundaries"]:
        if in_view(f) and f not in chosen:
            add(f'<path d="{path(f["geometry"])}" fill="#ebe8dd" stroke="#bdb8a8" stroke-width="1"/>')
    for f in chosen:
        add(f'<path d="{path(f["geometry"])}" fill="#fbfaf5" stroke="none"/>')
    for f in data["waterbodies"]:
        if in_view(f):
            add(f'<path d="{path(f["geometry"])}" fill="#a9cfe6" stroke="#6ba3c7" stroke-width="0.6"/>')
    for f in data["park_polygons"]:
        if in_view(f):
            add(f'<path d="{path(f["geometry"])}" fill="#b9dba3" stroke="#6da455" stroke-width="0.8"/>')
    for f in data["high_aedes_areas"]:
        if in_view(f):
            add(f'<path d="{path(f["geometry"])}" fill="#f2a33a" fill-opacity="0.16" stroke="#c97a10" stroke-width="1" stroke-dasharray="4 3"/>')
    for f in data["dengue_clusters"]:
        if in_view(f):
            add(f'<path d="{path(f["geometry"])}" fill="#d43a2f" fill-opacity="0.22" stroke="#b3261c" stroke-width="1.6"/>')
    for f in chosen:
        add(f'<path d="{path(f["geometry"])}" fill="none" stroke="#2b2b2b" stroke-width="2.4"/>')

    # subzone names
    for f in data["subzone_boundaries"]:
        if in_view(f):
            cx, cy = centroid_of(f["geometry"])
            if pt_in_view(cx, cy):
                x, y = xy(cx, cy)
                bold = f in chosen
                add(f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="middle" font-size="{13 if bold else 10}" font-weight="{700 if bold else 400}" fill="{"#2b2b2b" if bold else "#8d8878"}" letter-spacing="0.6" opacity="{0.85 if bold else 1}">{escape(f["properties"]["SUBZONE_N"])}</text>')

    # points
    counts = {"garden": 0, "facility": 0, "park": 0, "drain": 0}
    for f in data["park_facilities"]:
        lon, lat = p1.pt(f)
        if pt_in_view(lon, lat) and f["properties"]["CLASS"] in p1.WATER_RELEVANT_CLASSES:
            x, y = xy(lon, lat)
            add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#5b6770" stroke="#fff" stroke-width="0.6"/>')
            counts["facility"] += in_chosen(lon, lat)
    for f in data["community_gardens"]:
        lon, lat = p1.pt(f)
        if pt_in_view(lon, lat):
            x, y = xy(lon, lat)
            add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.6" fill="#2e8b3d" stroke="#fff" stroke-width="1.2"/>')
            counts["garden"] += in_chosen(lon, lat)
    for s_ in data["sensors"]:
        if pt_in_view(s_["lon"], s_["lat"]):
            x, y = xy(s_["lon"], s_["lat"])
            add(f'<rect x="{x - 4.5:.1f}" y="{y - 4.5:.1f}" width="9" height="9" fill="#1f6fb2" stroke="#fff" stroke-width="1.2"/>')
            counts["drain"] += in_chosen(s_["lon"], s_["lat"])
    for f in data["parks"]:
        lon, lat = p1.pt(f)
        counts["park"] += in_chosen(lon, lat)

    # dengue cluster case counts
    for f in data["dengue_clusters"]:
        if in_view(f):
            cx, cy = centroid_of(f["geometry"])
            if pt_in_view(cx, cy):
                x, y = xy(cx, cy)
                n = f["properties"]["CASE_SIZE"]
                add(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="11" fill="#b3261c"/><text x="{x:.0f}" y="{y + 4:.0f}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">{n}</text>')

    # rainfall stations
    temp_ids = {t["id"] for t in data["air_temperature_stations"]}
    for st in data["rainfall_stations"]:
        if pt_in_view(st["lon"], st["lat"]):
            x, y = xy(st["lon"], st["lat"])
            add(f'<path d="M{x:.1f},{y - 8:.1f} L{x + 7:.1f},{y + 5:.1f} L{x - 7:.1f},{y + 5:.1f} Z" fill="#111" stroke="#fff" stroke-width="1.2"/>')
            label = f'{st["id"]} {st["name"]}' + (" (rain, temp, humidity)" if st["id"] in temp_ids else " (rain)")
            anchor = "end" if x > WIDTH * 0.6 else "start"
            dx = -10 if anchor == "end" else 10
            add(f'<text x="{x + dx:.0f}" y="{y + 4:.0f}" text-anchor="{anchor}" font-size="11" font-weight="600" fill="#111" stroke="#fff" stroke-width="3" paint-order="stroke">{escape(label)}</text>')

    # scale bar and north arrow
    bar = 500 * scale
    add(f'<g transform="translate(20,{height - 24})"><rect x="-6" y="-18" width="{bar + 12:.0f}" height="30" fill="#fff" fill-opacity="0.8"/><path d="M0,0 H{bar:.0f} M0,-5 V5 M{bar:.0f},-5 V5" stroke="#111" stroke-width="2" fill="none"/><text x="{bar / 2:.0f}" y="-6" text-anchor="middle" font-size="11" fill="#111">500 m</text></g>')
    add(f'<g transform="translate({WIDTH - 30},40)"><path d="M0,-18 L7,8 L0,3 L-7,8 Z" fill="#111"/><text y="24" text-anchor="middle" font-size="11" fill="#111">N</text></g>')
    add("</g>")

    # legend
    def date_of(key):
        f = p1.newest(key, "*.metadata.json")
        return json.loads(f.read_text(encoding="utf-8")).get("lastUpdatedAt", "?")[:10] if f else "?"

    y0 = height + 22
    add(f'<text x="16" y="{y0}" font-size="14" font-weight="700" fill="#111">Candidate demo neighbourhood: {escape(" + ".join(n.title() for n in names))}</text>')
    add(f'<text x="16" y="{y0 + 18}" font-size="11" fill="#444">Drawn only from data.gov.sg snapshots fetched {p1.newest("dengue_clusters").stem} (Singapore time). No simulated data. Open Data Licence.</text>')
    rows = [
        ('<rect x="0" y="-9" width="18" height="11" fill="#d43a2f" fill-opacity="0.22" stroke="#b3261c" stroke-width="1.6"/>', f"Active dengue cluster, number = reported cases (NEA, updated {date_of('dengue_clusters')})"),
        ('<rect x="0" y="-9" width="18" height="11" fill="#f2a33a" fill-opacity="0.16" stroke="#c97a10" stroke-dasharray="4 3"/>', f"Area with high Aedes aegypti population (NEA, updated {date_of('high_aedes_areas')})"),
        ('<rect x="0" y="-9" width="18" height="11" fill="#b9dba3" stroke="#6da455"/>', f"Park managed by NParks (updated {date_of('park_polygons')}); {counts['park']} in the outlined area"),
        ('<circle cx="9" cy="-4" r="4.6" fill="#2e8b3d" stroke="#fff"/>', f"Community garden, Community in Bloom (NParks, updated {date_of('community_gardens')}); {counts['garden']} in the outlined area"),
        ('<circle cx="9" cy="-4" r="2.6" fill="#5b6770"/>', f"Park facility counted as an asset: toilet, shelter, drinking fountain, BBQ pit, allotment garden (NParks); {counts['facility']} in the outlined area"),
        ('<rect x="4.5" y="-8.5" width="9" height="9" fill="#1f6fb2" stroke="#fff"/>', f"Drain water-level sensor site (PUB, updated {date_of('pub_water_level_sensors')}); {counts['drain']} in the outlined area"),
        ('<rect x="0" y="-9" width="18" height="11" fill="#a9cfe6" stroke="#6ba3c7"/>', f"Waterbody, canal or major drain (URA Master Plan 2025, updated {date_of('waterbodies')})"),
        ('<path d="M9,-12 L16,1 L2,1 Z" fill="#111"/>', "Weather station (NEA real-time API)"),
        ('<rect x="0" y="-9" width="18" height="11" fill="none" stroke="#2b2b2b" stroke-width="2.4"/>', "Proposed demo area (URA Master Plan 2019 subzone boundaries)"),
    ]
    for i, (sym, text) in enumerate(rows):
        yy = y0 + 44 + i * 21
        add(f'<g transform="translate(16,{yy})">{sym}<text x="28" y="0" font-size="11.5" fill="#222">{escape(text)}</text></g>')
    add("</svg>")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(s), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes), map {WIDTH}x{height}px, extent {w_m:.0f} m x {h_m:.0f} m, counts in area: {counts}")


if __name__ == "__main__":
    main(sys.argv[1:])
