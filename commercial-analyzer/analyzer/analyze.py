"""Investment analysis: benchmarks, metrics and composite scoring.

Rent is benchmarked per (district, size-bucket) using a trimmed median, so a
tiny high-€/m² kiosk doesn't inflate the expected rent of a mid-size unit.
Lookups fall back district -> size-bucket -> city, lowering the confidence
weight as the match gets coarser.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict

from .config import AnalysisConfig, Config
from .geo import build_geo_rents, geo_rent_for
from .models import Listing, ScoredDeal

logger = logging.getLogger("krisha")

CITY_KEY = "__city__"
# area buckets (m²) — commercial rent/m² varies strongly with size
SIZE_EDGES = [0, 50, 120, 300, float("inf")]


def size_bucket(area: float | None) -> int:
    if not area:
        return -1
    for i in range(len(SIZE_EDGES) - 1):
        if SIZE_EDGES[i] <= area < SIZE_EDGES[i + 1]:
            return i
    return len(SIZE_EDGES) - 2


def _trimmed_median(values: list[float], trim: float = 0.1) -> float | None:
    vals = sorted(v for v in values if v and v > 0)
    if not vals:
        return None
    if len(vals) >= 10:
        k = int(len(vals) * trim)
        vals = vals[k: len(vals) - k] or vals
    return statistics.median(vals)


def _clean_area(l: Listing, cfg: Config) -> bool:
    return bool(l.area and cfg.deal.area_from <= l.area <= cfg.deal.area_to)


def dedupe(listings: list[Listing]) -> list[Listing]:
    """Collapse re-posts: same price + area + address = same object under
    different ad ids. Keeps the first occurrence."""
    seen: set[tuple] = set()
    out: list[Listing] = []
    for l in listings:
        key = (l.price, round(l.area, 1) if l.area else None,
               (l.address or "").lower()[:40])
        if key in seen:
            continue
        seen.add(key)
        out.append(l)
    return out


def build_rent_benchmarks(rent: list[Listing]) -> dict:
    """Return nested medians:
       bench[district][bucket] and bench[district][-1] (all sizes),
       plus bench[CITY_KEY][...]. Values are (median_rent_per_m2, n)."""
    buckets: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    for l in rent:
        ppm = l.price_per_m2
        if ppm and 500 < ppm < 100_000:  # tenge/m²/month sanity band
            b = size_bucket(l.area)
            d = l.district or ""
            buckets[d][b].append(ppm)
            buckets[d][-1].append(ppm)
            buckets[CITY_KEY][b].append(ppm)
            buckets[CITY_KEY][-1].append(ppm)

    bench: dict[str, dict[int, tuple[float, int]]] = {}
    for d, bmap in buckets.items():
        bench[d] = {}
        for b, vals in bmap.items():
            med = _trimmed_median(vals)
            if med:
                bench[d][b] = (med, len(vals))
    return bench


def build_sale_price_benchmarks(sale: list[Listing]) -> dict[str, float]:
    by_district: dict[str, list[float]] = defaultdict(list)
    for l in sale:
        ppm = l.price_per_m2
        if ppm and 10_000 < ppm < 5_000_000:
            by_district[l.district or ""].append(ppm)
            by_district[CITY_KEY].append(ppm)
    out: dict[str, float] = {}
    for d, vals in by_district.items():
        med = _trimmed_median(vals)
        if med:
            out[d] = med
    return out


def _rent_for(district: str, area: float, bench: dict,
              min_samples: int) -> tuple[float, int, float]:
    """(rent_per_m2, sample_size, confidence 0..1) with graded fallback."""
    b = size_bucket(area)
    d_map = bench.get(district, {})
    city_map = bench.get(CITY_KEY, {})

    # 1) district + exact size bucket
    if b in d_map and d_map[b][1] >= min_samples:
        n = d_map[b][1]
        return d_map[b][0], n, min(1.0, 0.6 + n / 40.0)
    # 2) district, any size
    if -1 in d_map and d_map[-1][1] >= min_samples:
        n = d_map[-1][1]
        return d_map[-1][0], n, min(0.75, 0.45 + n / 60.0)
    # 3) city + size bucket
    if b in city_map and city_map[b][1] >= min_samples:
        n = city_map[b][1]
        return city_map[b][0], n, 0.4
    # 4) city, any size
    if -1 in city_map:
        return city_map[-1][0], city_map[-1][1], 0.25
    return 0.0, 0, 0.0


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p))] if s else 0.0


def district_typical_yields(rent_bench: dict,
                            sale_bench: dict[str, float]) -> dict[str, float]:
    """district -> typical gross yield (rent_median×12 / sale_median)."""
    typ: dict[str, float] = {}
    for d, bmap in rent_bench.items():
        r = bmap.get(-1)
        s = sale_bench.get(d)
        if r and s:
            typ[d] = r[0] * 12 / s
    return typ


def analyze(sale: list[Listing], rent: list[Listing],
            cfg: Config) -> list[ScoredDeal]:
    a: AnalysisConfig = cfg.analysis
    before = len(sale)
    sale = dedupe(sale)
    rent = dedupe(rent)
    if before != len(sale):
        logger.info("Dedupe: %s -> %s sale listings", before, len(sale))
    rent_bench = build_rent_benchmarks(rent)
    sale_bench = build_sale_price_benchmarks(sale)

    if CITY_KEY not in rent_bench:
        logger.error("No usable rent data — cannot estimate yields.")
        return []

    typ = district_typical_yields(rent_bench, sale_bench)
    city_typ = typ.get(CITY_KEY, 0.16)

    use_geo = a.location_mode == "geo"
    geo_pts = build_geo_rents(rent, SIZE_EDGES) if use_geo else []
    if use_geo:
        logger.info("Geo mode: %s rent points with coordinates", len(geo_pts))

    candidates: list[ScoredDeal] = []
    basis_stats: dict[str, int] = defaultdict(int)
    skipped: dict[str, int] = defaultdict(int)
    for l in sale:
        if not l.price or l.price > cfg.deal.price_to:
            skipped["price"] += 1
            continue
        if not _clean_area(l, cfg):
            skipped["area"] += 1
            continue
        ppm = l.price_per_m2
        if not ppm or not (10_000 < ppm < 5_000_000):
            skipped["price_per_m2"] += 1
            continue
        if cfg.exclude_basement and l.is_basement():
            skipped["basement"] += 1
            continue

        rent_ppm = 0.0
        n = 0
        conf = 0.0
        basis = ""
        if use_geo and l.lat and l.lng and geo_pts:
            g = geo_rent_for(l.lat, l.lng, l.area, geo_pts, SIZE_EDGES,
                             a.geo_min_samples)
            if g:
                rent_ppm, n, radius, conf = g
                basis = f"≤{radius:.1f} км · {n} объ."
        if rent_ppm <= 0:  # geo failed or district mode -> district benchmark
            rent_ppm, n, conf = _rent_for(l.district, l.area, rent_bench,
                                          a.min_rent_samples)
            basis = f"район · {n} объ." if rent_ppm > 0 else ""
            conf *= 0.85  # district benchmark is coarser -> slightly less trust
        if rent_ppm <= 0:
            skipped["no_rent_bench"] += 1
            continue
        basis_stats["гео" if basis.startswith("≤") else "район"] += 1

        est_month = rent_ppm * l.area
        annual = est_month * 12
        gross_yield = annual / l.price
        if not (a.min_plausible_yield <= gross_yield <= a.max_plausible_yield):
            skipped["implausible_yield"] += 1
            continue

        market_ppm = sale_bench.get(l.district) or sale_bench.get(CITY_KEY, 0.0)
        discount = ((market_ppm - ppm) / market_ppm) if market_ppm else 0.0
        if discount > a.max_discount:  # suspiciously cheap -> likely a problem
            skipped["suspicious_cheap"] += 1
            continue

        # trust = rent-sample confidence × plausibility. A yield far above the
        # district norm is more likely a data artifact -> lower trust.
        d_typ = typ.get(l.district, city_typ) or city_typ
        plausibility = min(1.0, a.plausibility_factor * d_typ / gross_yield)
        trust = conf * plausibility

        candidates.append(ScoredDeal(
            listing=l, est_monthly_rent=est_month, rent_per_m2=rent_ppm,
            gross_yield=gross_yield, payback_years=l.price / annual,
            market_price_per_m2=market_ppm, price_discount=discount,
            rent_sample_size=n, confidence=trust,
            verify=(gross_yield > a.verify_yield
                    or discount > a.verify_discount or not l.district),
            rent_basis=basis,
        ))

    if use_geo:
        logger.info("Rent basis: %s", dict(basis_stats))
    logger.info("Candidates: %s (skipped: %s)", len(candidates), dict(skipped))
    if not candidates:
        return []

    # winsorize yield & discount so extreme values don't dominate the scale
    cap_y = _percentile([c.gross_yield for c in candidates], a.winsor_pct)
    cap_d = _percentile([max(0.0, c.price_discount) for c in candidates],
                        a.winsor_pct)
    y = _normalize([min(c.gross_yield, cap_y) for c in candidates])
    disc = _normalize([min(max(0.0, c.price_discount), cap_d)
                       for c in candidates])
    conf = _normalize([c.confidence for c in candidates])
    w = a.weights
    wsum = w.yield_ + w.discount + w.confidence
    for i, c in enumerate(candidates):
        raw = w.yield_ * y[i] + w.discount * disc[i] + w.confidence * conf[i]
        c.score = 100.0 * raw / wsum

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[: a.top_n]
