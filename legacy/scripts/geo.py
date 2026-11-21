"""Small geometry helpers for GeoJSON in longitude/latitude (WGS84). Standard library only.

Distances use a local flat-earth approximation, which is accurate to well under a metre
per kilometre at Singapore's latitude and over neighbourhood-sized distances.
"""

import math

M_PER_DEG_LAT = 110_574.0  # metres per degree of latitude near the equator


def m_per_deg_lon(lat):
    return 111_320.0 * math.cos(math.radians(lat))


def dist_m(lon1, lat1, lon2, lat2):
    """Approximate ground distance in metres between two lon/lat points."""
    mid = (lat1 + lat2) / 2.0
    dx = (lon2 - lon1) * m_per_deg_lon(mid)
    dy = (lat2 - lat1) * M_PER_DEG_LAT
    return math.hypot(dx, dy)


# --------------------------------------------------------------------------- SVY21


class _SVY21:
    """Singapore SVY21 (EPSG:3414) transverse Mercator, WGS84 ellipsoid."""

    a = 6378137.0
    f = 1 / 298.257223563
    o_lat = math.radians(1 + 22 / 60)  # 1 deg 22 min N
    o_lon = math.radians(103 + 50 / 60)  # 103 deg 50 min E
    o_n = 38744.572
    o_e = 28001.642
    k = 1.0

    b = a * (1 - f)
    e2 = 2 * f - f * f
    e4 = e2 * e2
    e6 = e4 * e2
    A0 = 1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256
    A2 = (3.0 / 8.0) * (e2 + e4 / 4 + 15 * e6 / 128)
    A4 = (15.0 / 256.0) * (e4 + 3 * e6 / 4)
    A6 = 35 * e6 / 3072

    @classmethod
    def calc_m(cls, lat):
        return cls.a * (
            cls.A0 * lat - cls.A2 * math.sin(2 * lat) + cls.A4 * math.sin(4 * lat) - cls.A6 * math.sin(6 * lat)
        )


def svy21_to_wgs84(easting, northing):
    """Convert SVY21 easting/northing in metres to (lon, lat) in degrees."""
    c = _SVY21
    n_prime = northing - c.o_n
    m_prime = c.calc_m(c.o_lat) + n_prime / c.k
    n = (c.a - c.b) / (c.a + c.b)
    n2, n3, n4 = n * n, n**3, n**4
    g = c.a * (1 - n) * (1 - n2) * (1 + 9 * n2 / 4 + 225 * n4 / 64) * (math.pi / 180)
    sigma = (m_prime * math.pi / 180) / g
    lat_p = (
        sigma
        + (3 * n / 2 - 27 * n3 / 32) * math.sin(2 * sigma)
        + (21 * n2 / 16 - 55 * n4 / 32) * math.sin(4 * sigma)
        + (151 * n3 / 96) * math.sin(6 * sigma)
        + (1097 * n4 / 512) * math.sin(8 * sigma)
    )
    sin2 = math.sin(lat_p) ** 2
    rho = c.a * (1 - c.e2) / (1 - c.e2 * sin2) ** 1.5
    v = c.a / math.sqrt(1 - c.e2 * sin2)
    psi = v / rho
    psi2, psi3, psi4 = psi * psi, psi**3, psi**4
    t = math.tan(lat_p)
    t2, t4, t6 = t * t, t**4, t**6
    e_prime = easting - c.o_e
    x = e_prime / (c.k * v)
    x3, x5, x7 = x**3, x**5, x**7

    lat_factor = t / (c.k * rho)
    lat1 = lat_factor * (e_prime * x / 2)
    lat2 = lat_factor * (e_prime * x3 / 24) * (-4 * psi2 + 9 * psi * (1 - t2) + 12 * t2)
    lat3 = (
        lat_factor
        * (e_prime * x5 / 720)
        * (
            8 * psi4 * (11 - 24 * t2)
            - 12 * psi3 * (21 - 71 * t2)
            + 15 * psi2 * (15 - 98 * t2 + 15 * t4)
            + 180 * psi * (5 * t2 - 3 * t4)
            + 360 * t4
        )
    )
    lat4 = lat_factor * (e_prime * x7 / 40320) * (1385 - 3633 * t2 + 4095 * t4 + 1575 * t6)
    lat = lat_p - lat1 + lat2 - lat3 + lat4

    sec = 1 / math.cos(lat_p)
    lon1 = x * sec
    lon2 = (x3 * sec / 6) * (psi + 2 * t2)
    lon3 = (x5 * sec / 120) * (-4 * psi3 * (1 - 6 * t2) + psi2 * (9 - 68 * t2) + 72 * psi * t2 + 24 * t4)
    lon4 = (x7 * sec / 5040) * (61 + 662 * t2 + 1320 * t4 + 720 * t6)
    lon = c.o_lon + lon1 - lon2 + lon3 - lon4
    return math.degrees(lon), math.degrees(lat)


# --------------------------------------------------------------------------- polygons


def polygons_of(geom):
    """Return a list of polygons; each polygon is a list of rings (outer first)."""
    if not geom:
        return []
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return list(geom["coordinates"])
    if t == "GeometryCollection":
        out = []
        for g in geom.get("geometries", []):
            out.extend(polygons_of(g))
        return out
    return []


def positions_of(geom):
    """Yield every position of any geometry type."""
    if not geom:
        return
    if geom.get("type") == "GeometryCollection":
        for g in geom.get("geometries", []):
            yield from positions_of(g)
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


def bbox_of(geom):
    xs, ys = [], []
    for p in positions_of(geom):
        xs.append(p[0])
        ys.append(p[1])
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_overlap(a, b):
    return a and b and a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_geometry(lon, lat, geom):
    """True when the point lies inside a Polygon/MultiPolygon (holes respected)."""
    for poly in polygons_of(geom):
        if poly and _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def _ring_area_centroid(ring):
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[i + 1][0], ring[i + 1][1]
        cr = x0 * y1 - x1 * y0
        a += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    a *= 0.5
    if abs(a) < 1e-18:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    return a, cx / (6 * a), cy / (6 * a)


def centroid_of(geom):
    """Area-weighted centroid (lon, lat) of the outer rings; mean position for other geometry."""
    polys = polygons_of(geom)
    if polys:
        tot = sx = sy = 0.0
        for poly in polys:
            a, cx, cy = _ring_area_centroid(poly[0])
            a = abs(a)
            tot += a
            sx += cx * a
            sy += cy * a
        if tot > 0:
            return sx / tot, sy / tot
    pts = list(positions_of(geom))
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def area_m2(geom):
    """Approximate area in square metres (outer rings minus holes)."""
    total = 0.0
    for poly in polygons_of(geom):
        if not poly:
            continue
        lat0 = poly[0][0][1]
        kx, ky = m_per_deg_lon(lat0), M_PER_DEG_LAT
        for idx, ring in enumerate(poly):
            a, _, _ = _ring_area_centroid(ring)
            total += (abs(a) if idx == 0 else -abs(a)) * kx * ky
    return total


def _seg_dist_m(px, py, ax, ay, bx, by, kx, ky):
    px, ax, bx = px * kx, ax * kx, bx * kx
    py, ay, by = py * ky, ay * ky, by * ky
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / d2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dist_point_to_geometry_m(lon, lat, geom):
    """0 when the point is inside the polygon, otherwise metres to its nearest edge."""
    if point_in_geometry(lon, lat, geom):
        return 0.0
    kx, ky = m_per_deg_lon(lat), M_PER_DEG_LAT
    best = float("inf")
    for poly in polygons_of(geom):
        for ring in poly:
            for i in range(len(ring) - 1):
                d = _seg_dist_m(lon, lat, ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1], kx, ky)
                if d < best:
                    best = d
    if best == float("inf"):  # not a polygon: fall back to nearest vertex
        for p in positions_of(geom):
            best = min(best, dist_m(lon, lat, p[0], p[1]))
    return best


def _segments_cross(p1, p2, p3, p4):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def geometries_intersect(g1, g2):
    """True when two polygon geometries overlap or touch across an edge."""
    if not bbox_overlap(bbox_of(g1), bbox_of(g2)):
        return False
    for p in positions_of(g1):
        if point_in_geometry(p[0], p[1], g2):
            return True
    for p in positions_of(g2):
        if point_in_geometry(p[0], p[1], g1):
            return True
    for pa in polygons_of(g1):
        for ra in pa:
            for pb in polygons_of(g2):
                for rb in pb:
                    for i in range(len(ra) - 1):
                        for j in range(len(rb) - 1):
                            if _segments_cross(ra[i], ra[i + 1], rb[j], rb[j + 1]):
                                return True
    return False
