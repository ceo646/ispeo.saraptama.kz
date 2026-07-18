"""HTML parsing for krisha.kz commercial listings.

Everything the analysis needs (price, area, district, basement flag) comes
straight from the search-results *cards*: krisha renders the total price,
the per-m² price (=> area), the district (subtitle) and a description
snippet right in each card. So no per-listing detail fetch is required.

All CSS selectors and regexes live here; if krisha changes its markup,
this is the only file to touch.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE = "https://krisha.kz"

# a run of digits possibly split by spaces / non-breaking spaces / thin spaces
_NUMRUN_RE = re.compile(r"\d[\d\s   ]*\d|\d")
_AREA_RE = re.compile(r"(\d+[.,]?\d*)\s*(?:м2|м²|m2|кв)", re.IGNORECASE)
_CYR = r"А-Яа-яЁёІіҢңҒғҮүҰұҚқӨөҺһ"
_DISTRICT_RE = re.compile(
    rf"([{_CYR}][{_CYR}\-]+)\s+р-?н|р-?н\s+([{_CYR}][{_CYR}\-]+)"
)
BASEMENT_MARKERS = (
    "цоколь", "цокольн", "подвал", "подвальн", "полуподвал",
    "полу-подвал", "basement", "-1 этаж", "минус первый",
)


def _clean_int(chunk: str) -> Optional[int]:
    digits = re.sub(r"\D", "", chunk)
    return int(digits) if digits else None


def _numbers(text: str | None) -> list[int]:
    if not text:
        return []
    out: list[int] = []
    for m in _NUMRUN_RE.finditer(text):
        v = _clean_int(m.group())
        if v is not None:
            out.append(v)
    return out


def area_from_title(text: str | None) -> Optional[float]:
    if not text:
        return None
    m = _AREA_RE.search(text)
    return float(m.group(1).replace(",", ".")) if m else None


def normalize_district(token: str) -> str:
    """Есильский -> Есиль ; keeps sale & rent district keys consistent."""
    t = re.sub(r"(ский|кий|ой|ый)$", "", token.strip())
    return t


def extract_district(text: str) -> str:
    m = _DISTRICT_RE.search(text or "")
    if not m:
        return ""
    return normalize_district(m.group(1) or m.group(2) or "")


def is_basement(text: str) -> bool:
    return any(mark in (text or "").lower() for mark in BASEMENT_MARKERS)


def _price_and_area(price_text: str, title: str) -> tuple[Optional[int], Optional[float]]:
    """Price cell holds total and per-m² price, e.g.
    '380 000 000 ₸ за всё 1 013 333 ₸ за м²'  ->  (380000000, 375.0)."""
    nums = _numbers(price_text)
    price = nums[0] if nums else None
    area = area_from_title(title)
    if area is None and price and "м²" in (price_text or "") and len(nums) >= 2:
        per_m2 = nums[-1]
        if per_m2:
            area = round(price / per_m2, 1)
    return price, area


def parse_list_page(html: str, deal: str, city: str) -> list[dict]:
    """One dict per card with all fields the analysis needs."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.a-card")
    if not cards:
        cards = soup.select("[data-id].a-card, [data-id]")
    out: list[dict] = []
    seen: set[str] = set()
    for card in cards:
        link = (card.select_one("a.a-card__title")
                or card.select_one(".a-card__title a")
                or card.select_one("a[href*='/a/show/']"))
        if not link or not link.get("href"):
            continue
        href = urljoin(BASE, link["href"])
        cid = card.get("data-id") or re.sub(r"\D", "", href.split("/")[-1])
        if not cid or cid in seen:
            continue
        seen.add(cid)
        title = link.get_text(" ", strip=True)
        price_el = card.select_one(".a-card__price, .card-stats__price")
        sub_el = card.select_one(".a-card__subtitle")
        price, area = _price_and_area(
            price_el.get_text(" ", strip=True) if price_el else "", title)
        subtitle = sub_el.get_text(" ", strip=True) if sub_el else ""
        card_text = card.get_text(" ", strip=True)
        out.append({
            "id": str(cid),
            "deal": deal,
            "city": city,
            "url": href,
            "title": title,
            "price": price,
            "area": area,
            "district": extract_district(subtitle) or extract_district(card_text),
            "address": subtitle,
            "text": card_text,
        })
    return out


_MAP_RE = re.compile(r'"map"\s*:\s*\{\s*"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*'
                     r'"lon"\s*:\s*(-?\d+\.\d+)')
_COMPLEX_ID_RE = re.compile(r'"complexId"\s*:\s*(\d+)')
_ADVERT_AREA_RE = re.compile(r'·\s*(\d+[.,]?\d*)\s*м')


def parse_detail_geo(html: str) -> dict:
    """Extract precise location from a listing detail page:
    {lat, lon, complex_id, area}. Values are None if absent."""
    out: dict = {"lat": None, "lon": None, "complex_id": None, "area": None}
    m = _MAP_RE.search(html)
    if m:
        out["lat"] = float(m.group(1))
        out["lon"] = float(m.group(2))
    cm = _COMPLEX_ID_RE.search(html)
    if cm:
        out["complex_id"] = int(cm.group(1))
    soup = BeautifulSoup(html, "html.parser")
    t = soup.select_one(".offer__advert-title")
    if t:
        am = _ADVERT_AREA_RE.search(t.get_text(" ", strip=True))
        if am:
            out["area"] = float(am.group(1).replace(",", "."))
    return out


def get_total_pages(html: str) -> int:
    """Number of result pages from the paginator, min 1."""
    soup = BeautifulSoup(html, "html.parser")
    pages = [1]
    for a in soup.select("nav.paginator a, .paginator__btn, a.paginator__btn"):
        for n in _numbers(a.get_text()):
            pages.append(n)
    return max(pages)
