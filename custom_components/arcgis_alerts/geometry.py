"""Point-in-polygon for ArcGIS polygon geometry, without third-party packages."""

from __future__ import annotations

from collections.abc import Sequence

Ring = Sequence[Sequence[float]]


def _crossings(x: float, y: float, ring: Ring) -> int:
    """Count how many edges of a ring a ray cast east from (x, y) crosses."""
    crossings = 0
    count = len(ring)
    if count < 3:
        return 0
    x1, y1 = ring[-1][0], ring[-1][1]
    for point in ring:
        x2, y2 = point[0], point[1]
        if (y1 > y) != (y2 > y):
            x_at_y = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_at_y:
                crossings += 1
        x1, y1 = x2, y2
    return crossings


def point_in_rings(x: float, y: float, rings: Sequence[Ring]) -> bool:
    """Return True when (x, y) lies inside an ArcGIS polygon's rings.

    Uses the even-odd rule over every ring together, so a hole (an inner
    ring) excludes the area it covers and a multipart polygon (several outer
    rings) includes each part. Ring winding order is not relied on.
    """
    return sum(_crossings(x, y, ring) for ring in rings) % 2 == 1


def feature_contains(geometry: dict | None, longitude: float, latitude: float) -> bool:
    """Return True when an ArcGIS JSON polygon geometry covers the point."""
    if not geometry:
        return False
    rings = geometry.get("rings")
    if not rings:
        return False
    return point_in_rings(longitude, latitude, rings)
