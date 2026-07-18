"""HTML parsing for krisha.kz commercial listings.

All CSS selectors used against krisha markup are centralized here so that,
if krisha changes its layout, only this file needs adjusting.

Two extraction layers are used, most-robust first:
  1. The JSON blob krisha embeds in a <script> ("digitalData" / advert data).
  2. Plain HTML selectors as a fallback.
"""

from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Listing

BASE = "https://krisha.kz"

_NUM_RE = re.compile(r"[\d\s ]+")
_FLOOR_RE = re.compile(r"(-?\d+)")


def _to_int(text: str | None) -> Optional[int]:
    if not text:
        return None
    m = _NUM_RE.search(text.replace(" ", " "))
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group())
    return int(digits) if digits else None


def _to_float_area(text: str | None) -> Optional[float]:
    """Extract an area value like '120.5 м²' -> 120.5."""
    if not text:
        return None
    m = re.search(r"(\d+[.,]?\d*)\s*(?:м2|м²|m2|кв)", text.lower())
    if not m:
        m = re.search(r"(\d+[.,]?\d*)", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def parse_list_page(html: str, deal: str, city: str) -> list[dict]:
    """Return lightweight dicts (id, url, title, price, area, address) for
    every card on a search-results page."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.a-card, div.a-card__inc, [data-id].a-card")
    if not cards:
        cards = soup.select("[data-id]")
    out: list[dict] = []
    seen: set[str] = set()
    for card in cards:
        link = card.select_one("a.a-card__title, .a-card__title a, a[href*='/a/show/']")
        if not link or not link.get("href"):
            continue
        href = urljoin(BASE, link["href"])
        cid = card.get("data-id") or re.sub(r"\D", "", href.split("/")[-1])
        if not cid or cid in seen:
            continue
        seen.add(cid)
        title = link.get_text(strip=True)
        price_el = card.select_one(".a-card__price, .card-stats__price")
        addr_el = card.select_one(".a-card__subtitle, .a-card__stats, "
                                  ".card__stats")
        out.append({
            "id": str(cid),
            "deal": deal,
            "city": city,
            "url": href,
            "title": title,
            "price": _to_int(price_el.get_text() if price_el else None),
            "area": _to_float_area(title),
            "address": addr_el.get_text(" ", strip=True) if addr_el else "",
        })
    return out


def _extract_json_blob(soup: BeautifulSoup) -> dict:
    """krisha embeds advert data as JSON in a <script>. Best-effort parse."""
    for script in soup.find_all("script"):
        txt = script.string or script.get_text() or ""
        if "digitalData" in txt or '"advert"' in txt or "window.data" in txt:
            for m in re.finditer(r"\{.*\}", txt, re.DOTALL):
                try:
                    return json.loads(m.group())
                except (json.JSONDecodeError, ValueError):
                    continue
    return {}


def _params_from_detail(soup: BeautifulSoup) -> dict[str, str]:
    """Parse the offer parameters table into {label: value}."""
    params: dict[str, str] = {}
    for dl in soup.select(".offer__parameters dl, .offer__short-description dl"):
        dt = dl.select_one("dt")
        dd = dl.select_one("dd")
        if dt and dd:
            params[dt.get_text(" ", strip=True)] = dd.get_text(" ", strip=True)
    # generic label/value pairs
    for row in soup.select(".offer__info-item"):
        k = row.select_one(".offer__info-title")
        v = row.select_one(".offer__advert-short-title, .offer__info-value")
        if k and v:
            params[k.get_text(" ", strip=True)] = v.get_text(" ", strip=True)
    return params


def _find_district(text: str, districts: list[str]) -> str:
    for d in districts:
        if d.lower() in text.lower():
            # normalize to short form (Есильский -> Есиль)
            return re.sub(r"(ский|кий|ый|ой)$", "", d).strip()
    return ""


def parse_detail_page(
    html: str,
    stub: dict,
    districts: list[str],
) -> Listing:
    """Enrich a card stub with detail-page data into a full Listing."""
    soup = BeautifulSoup(html, "html.parser")
    params = _params_from_detail(soup)
    blob = _extract_json_blob(soup)

    # title / price
    title_el = soup.select_one(".offer__advert-title h1, h1")
    title = title_el.get_text(" ", strip=True) if title_el else stub.get("title", "")
    price_el = soup.select_one(".offer__price, .offer__sidebar-header .offer__price")
    price = _to_int(price_el.get_text() if price_el else None) or stub.get("price")

    # area: параметр "Площадь" wins, else from title
    area = _to_float_area(params.get("Площадь") or params.get("Общая площадь"))
    if area is None:
        area = stub.get("area") or _to_float_area(title)

    # floor
    floor_raw = params.get("Этаж", "") or params.get("Этажность", "")
    floor = None
    fm = _FLOOR_RE.search(floor_raw)
    if fm:
        floor = int(fm.group(1))

    building_type = (params.get("Тип здания", "") or
                     params.get("Тип помещения", "") or
                     params.get("Назначение", ""))

    # address / district
    addr_el = soup.select_one(".offer__location, .offer__advert-title-adress, "
                              "[itemprop='address']")
    address = (addr_el.get_text(" ", strip=True) if addr_el
               else stub.get("address", ""))
    district = _find_district(address + " " + title, districts)

    # coordinates
    lat = lng = None
    map_el = soup.select_one("[data-lat], #map")
    if map_el:
        try:
            lat = float(map_el.get("data-lat")) if map_el.get("data-lat") else None
            lng = float(map_el.get("data-lon") or map_el.get("data-lng")) \
                if (map_el.get("data-lon") or map_el.get("data-lng")) else None
        except (TypeError, ValueError):
            pass
    if (lat is None or lng is None) and blob:
        adv = blob.get("advert") or blob
        m = adv.get("map") if isinstance(adv, dict) else None
        if isinstance(m, dict):
            lat = lat or m.get("lat")
            lng = lng or m.get("lng") or m.get("lon")

    return Listing(
        id=str(stub["id"]),
        deal=stub["deal"],
        url=stub["url"],
        title=title,
        price=price,
        area=area,
        floor=floor,
        floor_raw=floor_raw,
        building_type=building_type,
        district=district,
        address=address,
        city=stub.get("city", ""),
        lat=lat,
        lng=lng,
        raw_params=params,
    )


def listing_from_stub(stub: dict, districts: list[str]) -> Listing:
    """Build a Listing from just the card stub (when detail fetch is off)."""
    district = _find_district(
        stub.get("address", "") + " " + stub.get("title", ""), districts)
    return Listing(
        id=str(stub["id"]),
        deal=stub["deal"],
        url=stub["url"],
        title=stub.get("title", ""),
        price=stub.get("price"),
        area=stub.get("area"),
        floor=None,
        district=district,
        address=stub.get("address", ""),
        city=stub.get("city", ""),
    )


def get_total_pages(html: str) -> int:
    """Number of result pages from the paginator, min 1."""
    soup = BeautifulSoup(html, "html.parser")
    pages = [1]
    for a in soup.select(".paginator__btn, a.paginator__btn, nav.paginator a"):
        n = _to_int(a.get_text())
        if n:
            pages.append(n)
    return max(pages)
