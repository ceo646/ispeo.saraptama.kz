"""Configuration loading and krisha.kz URL helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


# krisha.kz uses a city slug in the URL path for commercial sections, e.g.
#   https://krisha.kz/prodazha/kommercheskaya-nedvizhimost/astana/
CITY_SLUGS = {
    "astana": "astana",
    "almaty": "almaty",
    "shymkent": "shymkent",
    "karaganda": "karaganda",
    "aktobe": "aktobe",
    "atyrau": "atyrau",
}

# Known city districts (район). Used to resolve a listing's district from its
# free-text address. Extend as needed.
CITY_DISTRICTS = {
    "astana": ["Есиль", "Есильский", "Алматы", "Алматинский", "Сарыарка",
               "Сарыаркинский", "Байконур", "Байконыр", "Нура", "Нуринский"],
    "almaty": ["Алмалинский", "Ауэзовский", "Бостандыкский", "Медеуский",
               "Наурызбайский", "Турксибский", "Жетысуский", "Алатауский"],
    "shymkent": ["Абайский", "Аль-Фарабийский", "Енбекшинский",
                 "Каратауский", "Туран"],
}


@dataclass
class DealConfig:
    price_to: int = 100_000_000
    price_from: int = 0
    area_from: float = 20.0
    area_to: float = 5000.0


@dataclass
class ScrapeConfig:
    max_pages: int = 40                # fallback cap for both deal types
    max_pages_sale: int | None = None  # overrides max_pages for sale
    max_pages_rent: int | None = None  # overrides max_pages for rent
    request_delay: tuple[float, float] = (2.0, 5.0)
    timeout: int = 30
    retries: int = 4
    fetch_details: bool = True
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


@dataclass
class Weights:
    yield_: float = 0.5
    discount: float = 0.3
    confidence: float = 0.2


@dataclass
class AnalysisConfig:
    weights: Weights = field(default_factory=Weights)
    top_n: int = 20
    min_rent_samples: int = 3
    # ignore sale listings whose computed yield is implausible (data errors).
    # Astana commercial gross yields are ~8-16%; >28% is almost always a data
    # artifact (wrong area, a share/land plot, or a benchmark mismatch).
    max_plausible_yield: float = 0.28
    min_plausible_yield: float = 0.03


@dataclass
class Config:
    city: str = "astana"
    exclude_basement: bool = True
    deal: DealConfig = field(default_factory=DealConfig)
    scrape: ScrapeConfig = field(default_factory=ScrapeConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    report_path: str = "report/top20.html"

    @property
    def city_slug(self) -> str:
        return CITY_SLUGS.get(self.city.lower(), self.city.lower())

    @property
    def districts(self) -> list[str]:
        return CITY_DISTRICTS.get(self.city.lower(), [])

    def sale_base_url(self) -> str:
        return (f"https://krisha.kz/prodazha/kommercheskaya-nedvizhimost/"
                f"{self.city_slug}/")

    def rent_base_url(self) -> str:
        return (f"https://krisha.kz/arenda/kommercheskaya-nedvizhimost/"
                f"{self.city_slug}/")

    def query_params(self, deal: str) -> dict[str, str]:
        """Server-side filters. Client-side filtering is authoritative, so
        these only trim the crawl volume."""
        params: dict[str, str] = {}
        if deal == "sale":
            if self.deal.price_to:
                params["das[price][to]"] = str(self.deal.price_to)
            if self.deal.price_from:
                params["das[price][from]"] = str(self.deal.price_from)
        if self.deal.area_from:
            params["das[square][from]"] = str(int(self.deal.area_from))
        if self.deal.area_to:
            params["das[square][to]"] = str(int(self.deal.area_to))
        return params


def _dget(d: dict, path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_config(path: str | None = None) -> Config:
    """Load config from a YAML file, falling back to defaults."""
    data: dict = {}
    if path and os.path.exists(path):
        if yaml is None:
            raise RuntimeError("pyyaml is required to read a config file")
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    cfg = Config()
    cfg.city = data.get("city", cfg.city)
    cfg.exclude_basement = _dget(data, "filters.exclude_basement",
                                 cfg.exclude_basement)
    cfg.report_path = _dget(data, "report.output", cfg.report_path)

    d = data.get("deal", {})
    cfg.deal = DealConfig(
        price_to=d.get("price_to", cfg.deal.price_to),
        price_from=d.get("price_from", cfg.deal.price_from),
        area_from=d.get("area_from", cfg.deal.area_from),
        area_to=d.get("area_to", cfg.deal.area_to),
    )

    s = data.get("scrape", {})
    delay = s.get("request_delay", list(cfg.scrape.request_delay))
    cfg.scrape = ScrapeConfig(
        max_pages=s.get("max_pages", cfg.scrape.max_pages),
        max_pages_sale=s.get("max_pages_sale", cfg.scrape.max_pages_sale),
        max_pages_rent=s.get("max_pages_rent", cfg.scrape.max_pages_rent),
        request_delay=tuple(delay),
        timeout=s.get("timeout", cfg.scrape.timeout),
        retries=s.get("retries", cfg.scrape.retries),
        fetch_details=s.get("fetch_details", cfg.scrape.fetch_details),
        user_agent=s.get("user_agent", cfg.scrape.user_agent),
    )

    a = data.get("analysis", {})
    w = a.get("weights", {})
    cfg.analysis = AnalysisConfig(
        weights=Weights(
            yield_=w.get("yield", Weights().yield_),
            discount=w.get("discount", Weights().discount),
            confidence=w.get("confidence", Weights().confidence),
        ),
        top_n=a.get("top_n", cfg.analysis.top_n),
        min_rent_samples=a.get("min_rent_samples", cfg.analysis.min_rent_samples),
        max_plausible_yield=a.get("max_plausible_yield",
                                  cfg.analysis.max_plausible_yield),
        min_plausible_yield=a.get("min_plausible_yield",
                                  cfg.analysis.min_plausible_yield),
    )
    return cfg
