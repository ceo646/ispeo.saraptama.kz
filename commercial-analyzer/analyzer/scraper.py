"""HTTP crawler for krisha.kz commercial listings.

Everything needed is on the search-results pages, so the crawler only
paginates through sale and rent results — no per-listing detail requests.

Politeness & resilience: randomized delay, exponential-backoff retries,
bounded pagination. krisha.kz sits behind Cloudflare and may reject
datacenter IPs; run from a network where krisha is reachable.
"""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import urlencode

import requests

from .config import Config
from .models import Listing
from . import parse

logger = logging.getLogger("krisha")


class Scraper:
    def __init__(self, config: Config):
        self.cfg = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.scrape.user_agent,
            "Accept-Language": "ru,en;q=0.9",
            "Accept": ("text/html,application/xhtml+xml,application/xml;"
                       "q=0.9,*/*;q=0.8"),
        })

    def _sleep(self) -> None:
        lo, hi = self.cfg.scrape.request_delay
        time.sleep(random.uniform(lo, hi))

    def _get(self, url: str, params: dict | None = None) -> str:
        last_err: Exception | None = None
        for attempt in range(1, self.cfg.scrape.retries + 1):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.cfg.scrape.timeout)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code in (403, 429):
                    logger.warning("Blocked (%s) on %s — anti-bot; backing off",
                                   resp.status_code, url)
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            except requests.RequestException as err:
                last_err = err
                backoff = 2 ** attempt
                logger.warning("Request failed (%s/%s): %s — retry in %ss",
                               attempt, self.cfg.scrape.retries, err, backoff)
                time.sleep(backoff)
        raise RuntimeError(f"Giving up on {url}: {last_err}")

    def _stub_to_listing(self, stub: dict) -> Listing:
        return Listing(
            id=stub["id"], deal=stub["deal"], url=stub["url"],
            title=stub.get("title", ""), price=stub.get("price"),
            area=stub.get("area"), floor=None,
            district=stub.get("district", ""), address=stub.get("address", ""),
            city=stub.get("city", ""), description=stub.get("text", ""),
        )

    def _crawl_deal(self, deal: str) -> list[Listing]:
        base = (self.cfg.sale_base_url() if deal == "sale"
                else self.cfg.rent_base_url())
        params = self.cfg.query_params(deal)
        logger.info("Crawling %s: %s?%s", deal, base, urlencode(params))

        cap = (self.cfg.scrape.max_pages_sale if deal == "sale"
               else self.cfg.scrape.max_pages_rent) or self.cfg.scrape.max_pages
        first_html = self._get(base, params)
        total = min(parse.get_total_pages(first_html), cap)
        logger.info("  %s page(s) to crawl", total)

        stubs = parse.parse_list_page(first_html, deal, self.cfg.city)
        for page in range(2, total + 1):
            self._sleep()
            try:
                html = self._get(base, dict(params, page=str(page)))
            except RuntimeError as err:
                logger.error("Stopping pagination at page %s: %s", page, err)
                break
            new = parse.parse_list_page(html, deal, self.cfg.city)
            stubs.extend(new)
            if not new:
                break
        # de-duplicate by id (paginator overlaps happen)
        uniq: dict[str, dict] = {s["id"]: s for s in stubs}
        logger.info("  collected %s unique %s listings", len(uniq), deal)
        return [self._stub_to_listing(s) for s in uniq.values()]

    def scrape(self) -> tuple[list[Listing], list[Listing]]:
        """Return (sale_listings, rent_listings)."""
        sale = self._crawl_deal("sale")
        rent = self._crawl_deal("rent")
        return sale, rent
