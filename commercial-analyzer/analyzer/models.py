"""Data models for listings and scored results."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    """A single krisha.kz commercial listing (sale or rent)."""

    id: str
    deal: str  # "sale" | "rent"
    url: str
    title: str
    price: Optional[int]          # tenge (sale: full price; rent: per month)
    area: Optional[float]         # m2
    floor: Optional[int]          # storey number, None if unknown
    floor_raw: str = ""           # raw floor text ("цокольный", "1 из 5", ...)
    building_type: str = ""       # тип здания / помещения
    district: str = ""            # район (Есиль/Алматы/Сарыарка/...)
    address: str = ""
    city: str = ""
    description: str = ""         # card snippet / detail text (basement check)
    lat: Optional[float] = None
    lng: Optional[float] = None
    raw_params: dict = field(default_factory=dict)

    @property
    def price_per_m2(self) -> Optional[float]:
        if self.price and self.area:
            return self.price / self.area
        return None

    def is_basement(self) -> bool:
        """True if the unit is a basement / semi-basement / plinth floor."""
        text = " ".join(
            [
                self.floor_raw,
                self.building_type,
                self.title,
                self.description,
                " ".join(f"{k} {v}" for k, v in self.raw_params.items()),
            ]
        ).lower()
        markers = (
            "цоколь", "цокольн", "подвал", "подвальн", "полуподвал",
            "полу-подвал", "basement", "ниже уровня земли", "-1 этаж",
            "минус первый", "сутеренный",
        )
        return any(m in text for m in markers)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["price_per_m2"] = self.price_per_m2
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        known = ("id", "deal", "url", "title", "price", "area", "floor",
                 "floor_raw", "building_type", "district", "address", "city",
                 "description", "lat", "lng", "raw_params")
        fields = {f: d[f] for f in known if f in d}
        if fields.get("raw_params") is None:
            fields.pop("raw_params", None)
        return cls(**fields)


@dataclass
class ScoredDeal:
    """A sale listing enriched with investment metrics and composite score."""

    listing: Listing
    est_monthly_rent: float          # expected rent, tenge/month
    rent_per_m2: float               # district benchmark used, tenge/m2/month
    gross_yield: float               # annual rent / price
    payback_years: float             # price / annual rent
    market_price_per_m2: float       # district median sale price/m2
    price_discount: float            # (market - listing) / market  (>0 = cheaper)
    rent_sample_size: int            # rent listings backing the benchmark
    confidence: float                # 0..1 data-trust factor (conf × plausibility)
    score: float = 0.0               # composite score, 0..100
    verify: bool = False             # "too good" — flag for manual verification
    rent_basis: str = ""             # how rent was benchmarked (radius/district)

    def to_row(self) -> dict:
        l = self.listing
        return {
            "score": round(self.score, 1),
            "title": l.title,
            "district": l.district or "—",
            "price": l.price,
            "area": l.area,
            "price_per_m2": round(l.price_per_m2) if l.price_per_m2 else None,
            "est_monthly_rent": round(self.est_monthly_rent),
            "rent_per_m2": round(self.rent_per_m2),
            "gross_yield_pct": round(self.gross_yield * 100, 1),
            "payback_years": round(self.payback_years, 1),
            "market_price_per_m2": round(self.market_price_per_m2),
            "price_discount_pct": round(self.price_discount * 100, 1),
            "floor": l.floor_raw or (str(l.floor) if l.floor is not None else "—"),
            "confidence": round(self.confidence, 2),
            "verify": self.verify,
            "rent_basis": self.rent_basis,
            "url": l.url,
        }
