"""Investment analysis: benchmarks, metrics and composite scoring."""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict

from .config import AnalysisConfig, Config
from .models import Listing, ScoredDeal

logger = logging.getLogger("krisha")

CITY_KEY = "__city__"


def _median(values: list[float]) -> float | None:
    values = [v for v in values if v and v > 0]
    return statistics.median(values) if values else None


def _clean_area(l: Listing, cfg: Config) -> bool:
    return bool(l.area and cfg.deal.area_from <= l.area <= cfg.deal.area_to)


def build_rent_benchmarks(rent: list[Listing]) -> dict[str, tuple[float, int]]:
    """district -> (median rent per m2 per month, sample size).

    Includes a CITY_KEY fallback aggregating every valid rent listing.
    """
    by_district: dict[str, list[float]] = defaultdict(list)
    for l in rent:
        ppm = l.price_per_m2
        if ppm and 500 < ppm < 100_000:  # sanity band, tenge/m2/month
            by_district[l.district or ""].append(ppm)
            by_district[CITY_KEY].append(ppm)

    bench: dict[str, tuple[float, int]] = {}
    for district, vals in by_district.items():
        med = _median(vals)
        if med:
            bench[district] = (med, len(vals))
    return bench


def build_sale_price_benchmarks(sale: list[Listing]) -> dict[str, float]:
    """district -> median sale price per m2 (the 'market' reference)."""
    by_district: dict[str, list[float]] = defaultdict(list)
    for l in sale:
        ppm = l.price_per_m2
        if ppm and 10_000 < ppm < 5_000_000:
            by_district[l.district or ""].append(ppm)
            by_district[CITY_KEY].append(ppm)
    out: dict[str, float] = {}
    for d, vals in by_district.items():
        med = _median(vals)
        if med:
            out[d] = med
    return out


def _rent_for(district: str, bench: dict[str, tuple[float, int]],
              min_samples: int) -> tuple[float, int, float]:
    """Return (rent_per_m2, sample_size, confidence[0..1]) for a district,
    falling back to the city aggregate when data is thin."""
    d = bench.get(district)
    if d and d[1] >= min_samples:
        conf = min(1.0, 0.5 + d[1] / 40.0)
        return d[0], d[1], conf
    city = bench.get(CITY_KEY)
    if not city:
        return 0.0, 0, 0.0
    # district known but thin -> blend toward city, lower confidence
    if d:
        blended = (d[0] * d[1] + city[0] * min_samples) / (d[1] + min_samples)
        return blended, d[1], 0.35
    return city[0], 0, 0.25


def _normalize(values: list[float]) -> list[float]:
    """Min-max normalize to 0..1 (constant list -> all 0.5)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def analyze(
    sale: list[Listing],
    rent: list[Listing],
    cfg: Config,
) -> list[ScoredDeal]:
    a: AnalysisConfig = cfg.analysis
    rent_bench = build_rent_benchmarks(rent)
    sale_bench = build_sale_price_benchmarks(sale)

    if CITY_KEY not in rent_bench:
        logger.error("No usable rent data — cannot estimate yields.")
        return []

    candidates: list[ScoredDeal] = []
    skipped = defaultdict(int)
    for l in sale:
        if not l.price or l.price > cfg.deal.price_to:
            skipped["price"] += 1
            continue
        if not _clean_area(l, cfg):
            skipped["area"] += 1
            continue
        if cfg.exclude_basement and l.is_basement():
            skipped["basement"] += 1
            continue

        rent_ppm, n, conf = _rent_for(l.district, rent_bench, a.min_rent_samples)
        if rent_ppm <= 0:
            skipped["no_rent_bench"] += 1
            continue

        est_month = rent_ppm * l.area
        annual = est_month * 12
        gross_yield = annual / l.price
        if not (a.min_plausible_yield <= gross_yield <= a.max_plausible_yield):
            skipped["implausible_yield"] += 1
            continue
        payback = l.price / annual

        market_ppm = sale_bench.get(l.district) or sale_bench.get(CITY_KEY, 0.0)
        discount = ((market_ppm - l.price_per_m2) / market_ppm
                    if market_ppm else 0.0)

        candidates.append(ScoredDeal(
            listing=l,
            est_monthly_rent=est_month,
            rent_per_m2=rent_ppm,
            gross_yield=gross_yield,
            payback_years=payback,
            market_price_per_m2=market_ppm,
            price_discount=discount,
            rent_sample_size=n,
            confidence=conf,
        ))

    logger.info("Candidates: %s (skipped: %s)", len(candidates), dict(skipped))
    if not candidates:
        return []

    # composite score from normalized components
    y = _normalize([c.gross_yield for c in candidates])
    disc = _normalize([max(0.0, c.price_discount) for c in candidates])
    conf = _normalize([c.confidence for c in candidates])
    w = a.weights
    wsum = w.yield_ + w.discount + w.confidence
    for i, c in enumerate(candidates):
        raw = (w.yield_ * y[i] + w.discount * disc[i] + w.confidence * conf[i])
        c.score = 100.0 * raw / wsum

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[: a.top_n]
