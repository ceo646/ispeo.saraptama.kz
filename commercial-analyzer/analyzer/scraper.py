"""HTTP crawler for krisha.kz commercial listings.

Politeness & resilience:
  * randomized delay between requests
  * exponential-backoff retries
  * bounded pagination
Anti-bot note: krisha.kz sits behind Cloudflare and rejects datacenter
IPs. Run this from a residential/office connection in Kazakhstan (or a
local browser session), not from a cloud CI runner.
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

    # -- low level -----------------------------------------------------
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
                    logger.warning("Blocked (%s) on %s — anti-bot. "
                                   "Slowing down.", resp.status_code, url)
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            except requests.RequestException as err:
                last_err = err
                backoff = 2 ** attempt
                logger.warning("Request failed (%s/%s): %s — retry in %ss",
                               attempt, self.cfg.scrape.retries, err, backoff)
                time.sleep(backoff)
        raise RuntimeError(f"Giving up on {url}: {last_err}")

    # -- crawl ---------------------------------------------------------
    def _crawl_deal(self, deal: str) -> list[Listing]:
        base = (self.cfg.sale_base_url() if deal == "sale"
                else self.cfg.rent_base_url())
        params = self.cfg.query_params(deal)
        logger.info("Crawling %s: %s?%s", deal, base, urlencode(params))

        first_html = self._get(base, params)
        total = min(parse.get_total_pages(first_html), self.cfg.scrape.max_pages)
        logger.info("  %s pages to crawl", total)

        stubs: list[dict] = parse.parse_list_page(first_html, deal, self.cfg.city)
        for page in range(2, total + 1):
            self._sleep()
            page_params = dict(params, page=str(page))
            try:
                html = self._get(base, page_params)
            except RuntimeError as err:
                logger.error("Stopping pagination at page %s: %s", page, err)
                break
            stubs.extend(parse.parse_list_page(html, deal, self.cfg.city))
        logger.info("  collected %s %s stubs", len(stubs), deal)

        return self._resolve(stubs, deal)

    def _resolve(self, stubs: list[dict], deal: str) -> list[Listing]:
        districts = self.cfg.districts
        # For rent benchmarks the card stub (area + price) is usually enough;
        # detail fetch is only worth it for sale listings (floor/type/district).
        fetch = self.cfg.scrape.fetch_details and deal == "sale"
        listings: list[Listing] = []
        for i, stub in enumerate(stubs, 1):
            if fetch:
                self._sleep()
                try:
                    html = self._get(stub["url"])
                    listings.append(
                        parse.parse_detail_page(html, stub, districts))
                except RuntimeError as err:
                    logger.warning("Detail fetch failed for %s: %s",
                                   stub["url"], err)
                    listings.append(parse.listing_from_stub(stub, districts))
                if i % 25 == 0:
                    logger.info("  resolved %s/%s details", i, len(stubs))
            else:
                listings.append(parse.listing_from_stub(stub, districts))
        return listings

    def scrape(self) -> tuple[list[Listing], list[Listing]]:
        """Return (sale_listings, rent_listings)."""
        sale = self._crawl_deal("sale")
        rent = self._crawl_deal("rent")
        return sale, rent
