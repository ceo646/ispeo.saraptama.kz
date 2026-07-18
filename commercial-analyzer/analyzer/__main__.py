"""CLI entry point.

Usage:
  python -m analyzer --config config.yaml            # live scrape + analyze
  python -m analyzer --demo                           # offline demo run
  python -m analyzer --demo --out report/demo.html    # custom output path
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .analyze import analyze
from .config import load_config
from .report import write_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("krisha")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="analyzer",
        description="Поиск лучших коммерческих помещений для сдачи в аренду "
                    "по данным krisha.kz.",
    )
    p.add_argument("--config", default="config.yaml",
                   help="путь к config.yaml (по умолчанию: config.yaml)")
    p.add_argument("--demo", action="store_true",
                   help="offline-прогон на синтетических данных (без сети)")
    p.add_argument("--out", default=None, help="путь к HTML-отчёту")
    p.add_argument("--cache", default=None, metavar="DIR",
                   help="сохранить собранные данные в DIR/<city>_{sale,rent}.json")
    p.add_argument("--from-cache", default=None, metavar="DIR",
                   help="анализировать из кэша DIR без скрапинга (быстрые итерации)")
    args = p.parse_args(argv)

    cfg = load_config(args.config)

    if args.from_cache:
        import json
        from .models import Listing
        base = os.path.join(args.from_cache, cfg.city)
        with open(f"{base}_sale.json", encoding="utf-8") as fh:
            sale = [Listing.from_dict(d) for d in json.load(fh)]
        with open(f"{base}_rent.json", encoding="utf-8") as fh:
            rent = [Listing.from_dict(d) for d in json.load(fh)]
        logger.info("Загружено из кэша: %s продажа, %s аренда", len(sale), len(rent))
    elif args.demo:
        from .demo import generate
        logger.info("DEMO MODE — синтетические данные, krisha.kz не запрашивается")
        sale, rent = generate()
    else:
        from .scraper import Scraper
        try:
            scraper = Scraper(cfg)
            sale, rent = scraper.scrape()
            if cfg.scrape.fetch_coords and cfg.analysis.location_mode == "geo":
                # coordinates power the geo-radius rent benchmark
                scraper.enrich_coords(rent, "rent")
                eligible = [l for l in sale if l.price
                            and l.price <= cfg.deal.price_to and l.area]
                scraper.enrich_coords(eligible, "sale")
        except Exception as err:  # noqa: BLE001
            logger.error("Скрапинг не удался: %s", err)
            logger.error("krisha.kz недоступен или блокирует запросы. "
                         "Запустите с локального IP в РК или используйте --demo.")
            return 1
        if args.cache:
            import json
            os.makedirs(args.cache, exist_ok=True)
            base = os.path.join(args.cache, cfg.city)
            for name, data in (("sale", sale), ("rent", rent)):
                with open(f"{base}_{name}.json", "w", encoding="utf-8") as fh:
                    json.dump([l.to_dict() for l in data], fh, ensure_ascii=False)
            logger.info("Данные сохранены в кэш: %s", args.cache)

    logger.info("Продажа: %s объявлений, аренда: %s объявлений",
                len(sale), len(rent))
    deals = analyze(sale, rent, cfg)
    out = write_report(deals, cfg, len(sale), len(rent), args.out)
    logger.info("Готово. Топ-%s → %s", len(deals), out)
    if not deals:
        logger.warning("Шортлист пуст — см. пояснение в HTML-отчёте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
