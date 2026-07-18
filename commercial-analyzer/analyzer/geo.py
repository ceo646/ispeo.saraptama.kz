"""Location-precise rent benchmarking by geographic radius.

Instead of a whole-district median, estimate a sale listing's rent from the
rent listings physically nearest to it — expanding the search radius until
enough comparable ads are found. This captures street/quarter-level price
differences that a district median averages away.
"""

from __future__ import annotations

import math
import statistics
from collections import namedtuple

from .models import Listing

RentPoint = namedtuple("RentPoint", "lat lon area ppm bucket")

# search radii in km, tried smallest-first until min_samples is reached
DEFAULT_RADII = (0.5, 0.8, 1.2, 2.0, 3.0)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _bucket(area, edges) -> int:
    if not area:
        return -1
    for i in range(len(edges) - 1):
        if edges[i] <= area < edges[i + 1]:
            return i
    return len(edges) - 2


def build_geo_rents(rent: list[Listing], edges) -> list[RentPoint]:
    pts = []
    for l in rent:
        ppm = l.price_per_m2
        if l.lat and l.lng and ppm and 500 < ppm < 100_000:
            pts.append(RentPoint(l.lat, l.lng, l.area, ppm, _bucket(l.area, edges)))
    return pts


def _trimmed_median(vals: list[float], trim: float = 0.1) -> float | None:
    vals = sorted(vals)
    if not vals:
        return None
    if len(vals) >= 10:
        k = int(len(vals) * trim)
        vals = vals[k: len(vals) - k] or vals
    return statistics.median(vals)


def geo_rent_for(lat, lon, area, pts: list[RentPoint], edges,
                 min_samples: int, radii=DEFAULT_RADII):
    """Return (rent_ppm, n, radius_km, confidence) using nearest rent ads.

    Prefers same-size-bucket ads; if a radius has enough of them, uses those,
    otherwise falls back to all sizes within that radius. Returns None when
    the point has no usable neighbours even at the largest radius."""
    if not (lat and lon):
        return None
    b = _bucket(area, edges)
    # precompute distances once
    with_d = [(p, _haversine_km(lat, lon, p.lat, p.lon)) for p in pts]
    for radius in radii:
        near = [(p, d) for p, d in with_d if d <= radius]
        if not near:
            continue
        same = [p.ppm for p, d in near if p.bucket == b]
        if len(same) >= min_samples:
            med = _trimmed_median(same)
            n, used = len(same), radius
            conf = min(1.0, 0.6 + n / 40.0) * min(1.0, 0.6 / max(radius, 0.5))
            return med, n, used, max(0.3, conf)
        allsz = [p.ppm for p, d in near]
        if len(allsz) >= max(min_samples, 5):
            med = _trimmed_median(allsz)
            n, used = len(allsz), radius
            conf = min(0.8, 0.45 + n / 60.0) * min(1.0, 0.6 / max(radius, 0.5))
            return med, n, used, max(0.25, conf)
    return None
