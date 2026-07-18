"""Synthetic (offline) dataset generator.

krisha.kz blocks datacenter/CI IPs, so this lets you exercise the full
analysis + report pipeline without network access. The numbers below are
plausible Astana ranges (mid-2020s) but are NOT real listings — use them
only to validate the tooling and preview the report layout.
"""

from __future__ import annotations

import random

from .models import Listing

# Astana districts with a plausible sale price/m2 and rent/m2/month band.
# (tenge). Central/business districts pricier; outskirts cheaper.
_DISTRICTS = {
    "Есиль":     {"sale": (650_000, 1_100_000), "rent": (4500, 8000)},
    "Алматы":    {"sale": (420_000, 720_000),   "rent": (3000, 5500)},
    "Сарыарка":  {"sale": (380_000, 650_000),   "rent": (2800, 5000)},
    "Байконур":  {"sale": (350_000, 600_000),   "rent": (2500, 4500)},
    "Нура":      {"sale": (300_000, 520_000),   "rent": (2200, 4200)},
}

_TYPES = ["Офис", "Помещение свободного назначения", "Магазин",
          "Помещение общепита", "Салон красоты", "Склад"]
_FLOORS_OK = ["1 из 5", "1 из 9", "2 из 5", "1 из 12", "1 из 3", "3 из 9"]
_FLOORS_BAD = ["Цокольный", "Подвальный", "Полуподвальный", "-1 из 9"]


def _rand_price(band, area, rng):
    ppm = rng.uniform(*band)
    return int(ppm * area)


def generate(seed: int = 42, n_sale: int = 220, n_rent: int = 260
             ) -> tuple[list[Listing], list[Listing]]:
    rng = random.Random(seed)
    districts = list(_DISTRICTS)
    sale: list[Listing] = []
    rent: list[Listing] = []

    # rent listings: define the true market rent per district
    for i in range(n_rent):
        d = rng.choice(districts)
        area = round(rng.uniform(25, 400), 1)
        rent_ppm = rng.uniform(*_DISTRICTS[d]["rent"])
        price = int(rent_ppm * area)
        rent.append(Listing(
            id=f"r{i}", deal="rent", city="astana",
            url=f"https://krisha.kz/a/show/rent{i}",
            title=f"Аренда, {rng.choice(_TYPES)} {area} м²",
            price=price, area=area, floor=1, floor_raw="1 из 5",
            district=d, address=f"Астана, {d} район",
        ))

    # sale listings: most priced near market, some underpriced gems,
    # a few basements (to prove they get filtered out).
    for i in range(n_sale):
        d = rng.choice(districts)
        area = round(rng.uniform(25, 500), 1)
        base_ppm = rng.uniform(*_DISTRICTS[d]["sale"])
        # 18% are genuine bargains (10-35% below market)
        if rng.random() < 0.18:
            base_ppm *= rng.uniform(0.65, 0.90)
        price = int(base_ppm * area)
        is_basement = rng.random() < 0.12
        floor = rng.choice(_FLOORS_BAD if is_basement else _FLOORS_OK)
        btype = "Помещение в цоколе" if is_basement else rng.choice(_TYPES)
        sale.append(Listing(
            id=f"s{i}", deal="sale", city="astana",
            url=f"https://krisha.kz/a/show/sale{i}",
            title=f"Продажа, {btype} {area} м²",
            price=price, area=area,
            floor=None if is_basement else 1,
            floor_raw=floor, building_type=btype,
            district=d, address=f"Астана, {d} район",
            raw_params={"Площадь": f"{area} м²", "Этаж": floor,
                        "Тип помещения": btype},
        ))
    return sale, rent
