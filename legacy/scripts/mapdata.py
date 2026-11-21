"""Turn GeoJSON into small SVG path strings for the offline map. Standard library only.

The site draws its map from these strings alone, so no map tiles or network are needed.
Coordinates are whole metres east and south of the view's top-left corner.
"""

import math

from geo import M_PER_DEG_LAT, m_per_deg_lon, polygons_of


class View:
    """A rectangular map view in local metres. x grows east, y grows south."""

    def __init__(self, lon0, lat0, lon1, lat1):
        self.lon0, self.lat0, self.lon1, self.lat1 = lon0, lat0, lon1, lat1
        self.kx = m_per_deg_lon((lat0 + lat1) / 2)
        self.ky = M_PER_DEG_LAT
        self.width = (lon1 - lon0) * self.kx
        self.height = (lat1 - lat0) * self.ky

    def xy(self, lon, lat):
        return (lon - self.lon0) * self.kx, (self.lat1 - lat) * self.ky

    def contains(self, lon, lat):
        return self.lon0 <= lon <= self.lon1 and self.lat0 <= lat <= self.lat1

    def bbox(self):
        return (self.lon0, self.lat0, self.lon1, self.lat1)


# --------------------------------------------------------------------------- simplify


def _dp(points, tol):
    """Douglas-Peucker on an open line of (x, y) tuples."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        d2 = dx * dx + dy * dy
        worst, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            if d2 == 0:
                dist = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / d2))
                dist = ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5
            if dist > worst:
                worst, idx = dist, i
        if worst > tol:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(points, keep) if k]


def simplify_line(points, tol):
    return _dp(points, tol)


def simplify_ring(points, tol):
    """Simplify a closed ring. Splits it at its farthest point so both halves keep their shape."""
    pts = list(points)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 4:
        return pts
    ax, ay = pts[0]
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - ax) ** 2 + (pts[i][1] - ay) ** 2)
    first = _dp(pts[: far + 1], tol)
    second = _dp(pts[far:] + [pts[0]], tol)
    return first[:-1] + second[:-1]


# --------------------------------------------------------------------------- clip


def clip_ring(points, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of a ring against a rectangle."""

    def clip(pts, inside, cross):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        return out

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    pts = list(points)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    for inside, cross in (
        (lambda p: p[0] >= x0, at_x(x0)),
        (lambda p: p[0] <= x1, at_x(x1)),
        (lambda p: p[1] >= y0, at_y(y0)),
        (lambda p: p[1] <= y1, at_y(y1)),
    ):
        if not pts:
            break
        pts = clip(pts, inside, cross)
    return pts


def clip_line(points, x0, y0, x1, y1):
    """Clip an open line against a rectangle. Returns a list of line pieces."""

    def code(p):
        return (1 if p[0] < x0 else 2 if p[0] > x1 else 0) | (4 if p[1] < y0 else 8 if p[1] > y1 else 0)

    def clip_segment(a, b):
        ca, cb = code(a), code(b)
        while True:
            if not (ca | cb):
                return a, b
            if ca & cb:
                return None
            c = ca or cb
            if c & 1:
                x, y = x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0])
            elif c & 2:
                x, y = x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0])
            elif c & 4:
                x, y = a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0
            else:
                x, y = a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1
            if c == ca:
                a, ca = (x, y), code((x, y))
            else:
                b, cb = (x, y), code((x, y))

    pieces, cur = [], []
    for i in range(len(points) - 1):
        seg = clip_segment(points[i], points[i + 1])
        if seg is None:
            if len(cur) > 1:
                pieces.append(cur)
            cur = []
            continue
        a, b = seg
        if cur and cur[-1] == a:
            cur.append(b)
        else:
            if len(cur) > 1:
                pieces.append(cur)
            cur = [a, b]
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


# --------------------------------------------------------------------------- SVG paths


def _rel_path(points, close):
    pts = [(int(round(x)), int(round(y))) for x, y in points]
    dedup = [pts[0]]
    for p in pts[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    if close and len(dedup) > 1 and dedup[0] == dedup[-1]:
        dedup.pop()
    if len(dedup) < (3 if close else 2):
        return ""
    out = [f"M{dedup[0][0]},{dedup[0][1]}"]
    steps = []
    for (ax, ay), (bx, by) in zip(dedup, dedup[1:]):
        steps.append(f"{bx - ax},{by - ay}")
    out.append("l" + " ".join(steps))
    if close:
        out.append("z")
    return "".join(out)


def polygon_path(geom, view, tol=2.0, pad=30.0):
    """SVG path for a Polygon or MultiPolygon, clipped to the view (plus a small pad)."""
    parts = []
    for poly in polygons_of(geom):
        for ring in poly:
            pts = [view.xy(c[0], c[1]) for c in ring]
            pts = clip_ring(pts, -pad, -pad, view.width + pad, view.height + pad)
            if len(pts) < 3:
                continue
            pts = simplify_ring(pts, tol)
            if len(pts) >= 3:
                parts.append(_rel_path(pts, True))
    return "".join(p for p in parts if p)


def line_path(geom, view, tol=3.0, pad=30.0):
    """SVG path for a LineString or MultiLineString, clipped to the view."""
    lines = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
    parts = []
    for line in lines:
        pts = [view.xy(c[0], c[1]) for c in line]
        for piece in clip_line(pts, -pad, -pad, view.width + pad, view.height + pad):
            piece = simplify_line(piece, tol)
            if len(piece) >= 2:
                parts.append(_rel_path(piece, False))
    return "".join(p for p in parts if p)


def island_outline(geoms, focus_bbox, cell_m=150.0, tol_cells=1.5, min_area_km2=1.5):
    """One coastline for many touching polygons, without a polygon-union library.

    The subzone file tiles the whole of Singapore with 332 polygons. Painting them all onto a
    coarse grid and walking round the edge of the painted cells gives the outline of the land,
    however the polygons meet inside. Used for the small locator map only, so 150 m cells are
    plenty. Returns {"w", "h", "d", "box"}: a path in grid cells and the focus area's box in
    the same units. Islets smaller than `min_area_km2` are left out.
    """
    boxes = []
    for g in geoms:
        for poly in polygons_of(g):
            xs = [c[0] for c in poly[0]]
            ys = [c[1] for c in poly[0]]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
    view = View(min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    cols, rows = int(view.width / cell_m) + 3, int(view.height / cell_m) + 3   # one empty cell all round

    def cell_xy(lon, lat):
        x, y = view.xy(lon, lat)
        return x / cell_m + 1, y / cell_m + 1

    grid = [bytearray(cols) for _ in range(rows)]
    for g in geoms:
        for poly in polygons_of(g):
            crossings = {}
            for ring in poly:                      # outer ring and holes together: even-odd fill
                pts = [cell_xy(c[0], c[1]) for c in ring]
                for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
                    if ay == by:
                        continue
                    lo, hi = (ay, by) if ay < by else (by, ay)
                    r = max(0, math.ceil(lo - 0.5))
                    while r + 0.5 < hi and r < rows:   # rows whose centre line this edge crosses
                        crossings.setdefault(r, []).append(ax + (bx - ax) * (r + 0.5 - ay) / (by - ay))
                        r += 1
            for r, xs in crossings.items():
                xs.sort()
                for xa, xb in zip(xs[0::2], xs[1::2]):
                    c0 = max(0, int(xa + 0.5))
                    c1 = min(cols, int(xb + 0.5))
                    for c in range(c0, c1):
                        grid[r][c] = 1

    # Edges between a painted cell and an empty one, each drawn with the land on its right.
    nxt = {}
    for r in range(rows):
        row = grid[r]
        for c in range(cols):
            if not row[c]:
                continue
            if r == 0 or not grid[r - 1][c]:
                nxt.setdefault((c, r), []).append((c + 1, r))
            if c == cols - 1 or not row[c + 1]:
                nxt.setdefault((c + 1, r), []).append((c + 1, r + 1))
            if r == rows - 1 or not grid[r + 1][c]:
                nxt.setdefault((c + 1, r + 1), []).append((c, r + 1))
            if c == 0 or not row[c - 1]:
                nxt.setdefault((c, r + 1), []).append((c, r))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop, at = [start], start
        while True:
            ends = nxt[at]
            to = ends.pop()
            if not ends:
                del nxt[at]
            if to == start:
                break
            loop.append(to)
            at = to
        loops.append(loop)

    def area(loop):
        return sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(loop, loop[1:] + loop[:1])) / 2

    min_cells = min_area_km2 * 1e6 / (cell_m * cell_m)
    parts = []
    for loop in sorted(loops, key=lambda lp: -abs(area(lp))):
        if abs(area(loop)) < min_cells:
            continue
        pts = simplify_ring(loop, tol_cells)
        if len(pts) >= 3:
            parts.append(_rel_path(pts, True))
    x0, y0 = cell_xy(focus_bbox[0], focus_bbox[3])
    x1, y1 = cell_xy(focus_bbox[2], focus_bbox[1])
    return {"w": cols, "h": rows, "d": "".join(parts), "box": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]}


def touches_view(geom_bbox, view):
    b = view.bbox()
    return geom_bbox and geom_bbox[0] <= b[2] and b[0] <= geom_bbox[2] and geom_bbox[1] <= b[3] and b[1] <= geom_bbox[3]
