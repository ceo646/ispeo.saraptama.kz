"""HTTP crawler for krisha.kz commercial listings.

Everything needed is on the search-results pages, so the crawler only
paginates through sale and rent results — no per-listing detail requests.

Politeness & resilience: randomized delay, exponential-backoff retries,
bounded pagination. krisha.kz sits behind Cloudflare and may reject
datacenter IPs; run from a network where krisha is reachable.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import requests

from .config import Config
from .models import Listing
from . import parse

logger = logging.getLogger("krisha")


class Scraper:
    def __init__(self, config: Config):
        self.cfg = config
        self._tls = threading.local()
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

    def _thread_session(self) -> requests.Session:
        if not hasattr(self._tls, "session"):
            s = requests.Session()
            s.headers.update(self.session.headers)
            self._tls.session = s
        return self._tls.session

    def _get_once(self, url: str) -> str | None:
        """Single GET with light retries, for concurrent workers."""
        for attempt in range(1, self.cfg.scrape.retries + 1):
            try:
                r = self._thread_session().get(url, timeout=self.cfg.scrape.timeout)
                if r.status_code == 200:
                    return r.text
            except requests.RequestException:
                pass
            time.sleep(1.5 * attempt + random.random())
        return None

    def enrich_coords(self, listings: list[Listing], label: str = "",
                      workers: int = 6, checkpoint: str | None = None) -> int:
        """Fetch detail pages concurrently and fill lat/lon (+complex id).

        Resumable: if `checkpoint` is given, each result is appended to that
        JSONL file and already-recorded ids are skipped on restart, so an
        interrupted run continues instead of starting over.
        """
        import json as _json
        import threading

        cache: dict[str, dict] = {}
        if checkpoint and os.path.exists(checkpoint):
            for line in open(checkpoint, encoding="utf-8"):
                try:
                    o = _json.loads(line)
                    cache[o["id"]] = o
                except (ValueError, KeyError):
                    pass
        # apply cached coords, collect the rest
        todo: list[Listing] = []
        for l in listings:
            c = cache.get(l.id)
            if c and c.get("lat"):
                l.lat, l.lng = c["lat"], c["lon"]
            elif l.lat is None:
                todo.append(l)
        logger.info("Enriching %s%s listings with coordinates (%s cached)",
                    len(todo), f" {label}" if label else "", len(cache))

        lock = threading.Lock()
        ck = open(checkpoint, "a", encoding="utf-8") if checkpoint else None
        done = [0]

        def work(l: Listing) -> None:
            html = self._get_once(l.url)
            geo = parse.parse_detail_geo(html) if html else {}
            lat, lon = geo.get("lat"), geo.get("lon")
            if lat and lon:
                l.lat, l.lng = lat, lon
                if geo.get("complex_id"):
                    l.raw_params["complex_id"] = geo["complex_id"]
                if geo.get("area"):
                    l.area = geo["area"]
            with lock:
                done[0] += 1
                if ck:
                    ck.write(_json.dumps({"id": l.id, "lat": lat, "lon": lon}) + "\n")
                    ck.flush()
                if done[0] % 100 == 0:
                    logger.info("  %s/%s enriched", done[0], len(todo))
            time.sleep(random.uniform(0.15, 0.5))

        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(work, todo))
        if ck:
            ck.close()
        ok = sum(1 for l in listings if l.lat)
        logger.info("Coordinates: %s/%s listings have coordinates", ok, len(listings))
        return ok
