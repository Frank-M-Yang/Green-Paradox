"""Printable one-page daily task sheet with the inspection route. Static HTML, no scripts.

The sheet is the low-tech fallback: it works on paper, with a pen, with no phone at all.
"""

import html
import math
from datetime import date

import risk

BAND_LABEL = {"high": "Inspect first", "medium": "Inspect this week", "low": "Routine"}
ACTION_CODES = [("Dr", "drained"), ("Em", "emptied"), ("Cl", "cleared"), ("Co", "covered"), ("Re", "repaired"), ("Rp", "reported")]


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {risk.MONTHS[d.month - 1]} {d.year}"


def baseline_parts(asset, snapshot, scenario_id):
    """The four parts of an asset's score as the data script computed them, before any device records."""
    cfg = snapshot["config"]
    as_of = date.fromisoformat(snapshot["meta"]["as_of"])
    last = asset["inspections"][0] if asset["inspections"] else None
    days = (as_of - date.fromisoformat(last["date"])).days if last else None
    parts = snapshot["parts"]
    return [parts[asset["water"]], risk.inspection_part(last, days, cfg), parts[asset["rain"][scenario_id]], parts[asset["location"]]]


def ranked_tasks(snapshot, scenario_id):
    cfg = snapshot["config"]
    tasks = []
    for a in snapshot["assets"]:
        parts = baseline_parts(a, snapshot, scenario_id)
        score, band = risk.total(parts, cfg)
        tasks.append({"asset": a, "parts": parts, "score": score, "band": band})
    insp = lambda t: next(p["points"] for p in t["parts"] if p["key"] == "inspection")  # noqa: E731
    tasks.sort(key=lambda t: (-t["score"], -insp(t), t["asset"]["name"]))
    for i, t in enumerate(tasks, 1):
        t["rank"] = i
    return tasks


def why(parts, limit=3):
    top = sorted((p for p in parts if p["points"] > 0), key=lambda p: -p["points"])[:limit]
    return [f"{p['short']} (+{p['points']})" for p in top]


def plan_route(stops):
    """Order stops: start at the highest priority, go to the nearest next, then untangle with 2-opt.

    Distances are straight lines between points. There is no road network in the data.
    """
    if len(stops) < 3:
        return list(stops)

    def d(a, b):
        return math.hypot(a["asset"]["x"] - b["asset"]["x"], a["asset"]["y"] - b["asset"]["y"])

    route, rest = [stops[0]], list(stops[1:])
    while rest:
        nxt = min(rest, key=lambda s: d(route[-1], s))
        rest.remove(nxt)
        route.append(nxt)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(route) - 1):
            for j in range(i + 1, len(route)):
                before = d(route[i - 1], route[i]) + (d(route[j], route[j + 1]) if j + 1 < len(route) else 0)
                after = d(route[i - 1], route[j]) + (d(route[i], route[j + 1]) if j + 1 < len(route) else 0)
                if after + 1e-6 < before:
                    route[i : j + 1] = reversed(route[i : j + 1])
                    improved = True
    return route


def route_length_m(route):
    return sum(math.hypot(a["asset"]["x"] - b["asset"]["x"], a["asset"]["y"] - b["asset"]["y"]) for a, b in zip(route, route[1:]))


def route_map_svg(snapshot, route):
    m = snapshot["map"]
    xs = [t["asset"]["x"] for t in route]
    ys = [t["asset"]["y"] for t in route]
    pad = 260
    x0, y0 = max(0, min(xs) - pad), max(0, min(ys) - pad)
    x1, y1 = min(m["w"], max(xs) + pad), min(m["h"], max(ys) + pad)
    w, h = x1 - x0, y1 - y0
    target = 2.7  # width to height of the box on the page: wide and low, to leave room for the table
    if w / h < target:
        grow = (h * target - w) / 2
        x0, x1 = max(0, x0 - grow), min(m["w"], x1 + grow)
    else:
        grow = (w / target - h) / 2
        y0, y1 = max(0, y0 - grow), min(m["h"], y1 + grow)
    w, h = x1 - x0, y1 - y0
    u = w / 190  # one millimetre on paper, in map metres
    s = [f'<svg class="route" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Route map">']
    s.append(f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" fill="#f6f5ef"/>')
    s.append(f'<path d="{m["water"]}" fill="#c9dfec"/>')
    s.append(f'<path d="{m["parks"]}" fill="#d6e8c8"/>')
    s.append(f'<path d="{m["roads"]}" fill="none" stroke="#b9b5a8" stroke-width="{u * 0.35:.1f}"/>')
    for c in m["clusters"]:
        s.append(f'<path d="{c["d"]}" fill="#6250d6" fill-opacity="0.12" stroke="#6250d6" stroke-width="{u * 0.35:.1f}" stroke-dasharray="{u * 1.2:.0f} {u * 0.8:.0f}"/>')
    for f in m["frame"]:
        s.append(f'<path d="{f["d"]}" fill="none" stroke="#333" stroke-width="{u * 0.45:.1f}"/>')
    pts = " ".join(f'{t["asset"]["x"]},{t["asset"]["y"]}' for t in route)
    s.append(f'<polyline points="{pts}" fill="none" stroke="#1d4e89" stroke-width="{u * 0.6:.1f}" stroke-linejoin="round"/>')
    for i, t in enumerate(route, 1):
        a = t["asset"]
        s.append(f'<circle cx="{a["x"]}" cy="{a["y"]}" r="{u * 2.6:.1f}" fill="#fff" stroke="#1d4e89" stroke-width="{u * 0.5:.1f}"/>')
        s.append(f'<text x="{a["x"]}" y="{a["y"] + u * 1.15:.1f}" text-anchor="middle" font-size="{u * 3.2:.1f}" font-weight="700" fill="#1d4e89">{i}</text>')
    bar = 250
    bx, by = x0 + u * 4, y1 - u * 4
    s.append(f'<path d="M{bx:.0f},{by:.0f}h{bar}" stroke="#333" stroke-width="{u * 0.5:.1f}"/><text x="{bx + bar / 2:.0f}" y="{by - u * 1.2:.0f}" text-anchor="middle" font-size="{u * 2.6:.1f}" fill="#333">250 m</text>')
    s.append("</svg>")
    return "".join(s)


CSS = """
@page { size: A4 portrait; margin: 8mm; }
* { box-sizing: border-box; }
body { font: 8.5pt/1.25 system-ui, "Segoe UI", Arial, sans-serif; color: #1c1c1c; margin: 0 auto; max-width: 194mm; padding: 3mm; }
h1 { font-size: 14pt; margin: 0; }
.sub { margin: 0.6mm 0 1.4mm; color: #333; }
.note { border: 0.3mm solid #999; padding: 1mm 1.6mm; margin: 0 0 1.6mm; font-size: 7.6pt; }
.route { width: 100%; height: 60mm; border: 0.3mm solid #999; display: block; background: #f6f5ef; }
.cap { font-size: 7pt; color: #444; margin: 0.6mm 0 1.4mm; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th, td { border: 0.25mm solid #777; padding: 0.7mm 1.1mm; vertical-align: top; text-align: left; overflow-wrap: anywhere; }
th { background: #eee; font-size: 7pt; }
col.c1 { width: 9mm; } col.c2 { width: 52mm; } col.c3 { width: 16mm; } col.c4 { width: 55mm; } col.c5 { width: 15mm; } col.c6 { width: 27mm; }
td.n { font-size: 11pt; font-weight: 700; text-align: center; color: #1d4e89; overflow-wrap: normal; }
td.s { text-align: center; font-size: 7pt; }
td.s b { font-size: 12pt; display: block; line-height: 1.1; }
td.chk, td.act { font-size: 7.4pt; line-height: 1.5; }
.sim { border: 0.3mm solid #1c1c1c; font-size: 6pt; font-weight: 700; padding: 0 0.7mm; letter-spacing: 0.04em; margin-left: 1mm; white-space: nowrap; }
.ty { font-size: 7.4pt; color: #333; }
.why { font-size: 7.6pt; color: #222; }
.look { font-size: 6.8pt; color: #444; }
.box { display: inline-block; width: 2.6mm; height: 2.6mm; border: 0.3mm solid #222; vertical-align: -0.4mm; margin: 0 0.5mm 0 0.2mm; }
.act span.a { white-space: nowrap; margin-right: 0.8mm; }
footer { margin-top: 1.4mm; font-size: 6.6pt; color: #333; }
@media screen { body { background: #fff; box-shadow: 0 0 0 1px #ddd; margin-top: 12px; } }
@media print { body { padding: 0; max-width: none; } }
"""


def render(snapshot):
    meta = snapshot["meta"]
    real = snapshot["scenarios"][0]
    tasks = ranked_tasks(snapshot, real["id"])
    chosen = tasks[: meta["daily_capacity"]]
    route = plan_route(chosen)
    km = route_length_m(route) / 1000
    e = html.escape
    rows = []
    for i, t in enumerate(route, 1):
        a = t["asset"]
        sim = '<span class="sim">SIMULATED</span>' if a["simulated"] else ""
        look = snapshot["types"][a["type"]]["look_for"]
        acts = " ".join(f'<span class="a"><span class="box"></span>{code}</span>' for code, _ in ACTION_CODES)
        rows.append(
            f'<tr><td class="n">{i}</td>'
            f'<td><b>{e(a["name"])}</b>{sim}<div class="ty">{e(snapshot["types"][a["type"]]["label"])} · rank {t["rank"]}</div>'
            f'<div class="look">Look for: {e(look)}</div></td>'
            f'<td class="s"><b>{t["score"]}</b>{BAND_LABEL[t["band"]]}</td>'
            f'<td class="why">{"; ".join(e(w) for w in why(t["parts"]))}</td>'
            f'<td class="chk"><span class="box"></span>water<br><span class="box"></span>larvae</td>'
            f'<td class="act">{acts}</td><td class="wr"></td></tr>'
        )
    stations = ", ".join(f'{s["id"]} {s["name"]}' for s in real["stations"])
    srcs = "; ".join(
        f'{s["title"]} ({s["agency"]}, snapshot {long_date(s["snapshot_date"])})'
        for s in snapshot["sources"]
        if s.get("snapshot_date") and s["key"] in ("dengue_clusters", "high_aedes_areas", "parks", "park_facilities", "community_gardens", "pub_water_level_sensors")
    )
    codes = ", ".join(f"{c} = {w}" for c, w in ACTION_CODES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>Daily task sheet, {e(long_date(meta["as_of"]))}</title><style>{CSS}</style></head><body>
<h1>Canopy Care daily task sheet</h1>
<p class="sub"><b>{e(meta["neighbourhood"])}</b> · {e(long_date(meta["as_of"]))} · top {len(route)} of {len(tasks)} assets, in walking order</p>
<p class="note">This sheet ranks inspections. It is <b>not a prediction of dengue cases</b>. Thresholds are placeholders awaiting expert review.
Locations of parks, gardens and PUB sensor sites are real. Assets marked SIMULATED and all past inspection dates are made up for the demo.</p>
{route_map_svg(snapshot, route)}
<p class="cap">Route starts at the highest priority, then goes to the nearest next stop. About {km:.1f} km in straight lines; walking it will be longer.
Dashed violet: active dengue clusters. Dark outline: the demo area.</p>
<table>
<colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"><col class="c5"><col class="c6"><col></colgroup>
<tr><th>Stop</th><th>Asset</th><th>Priority</th><th>Why it is on today's sheet</th><th>Found</th><th>Action taken</th><th>Note</th></tr>
{"".join(rows)}
</table>
<footer>
Actions: {e(codes)}. General measures only. Rain used: {e(long_date(real["from"]))} to {e(long_date(real["to"]))}, NEA stations {e(stations)}.<br>
Sources: {e(srcs)}. Contains information from data.gov.sg accessed under the {e(meta["licence"])}.
Generated {e(meta["generated_at"][:16].replace("T", " "))} SGT by the once-a-day data script.
</footer>
</body></html>
"""


def write(snapshot, path):
    text = render(snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))
