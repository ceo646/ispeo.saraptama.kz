"""CLI entry point.

Usage:
  python -m analyzer --config config.yaml            # live scrape + analyze
  python -m analyzer --demo                           # offline demo run
  python -m analyzer --demo --out report/demo.html    # custom output path
"""

from __future__ import annotations

import argparse
import logging
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
    args = p.parse_args(argv)

    cfg = load_config(args.config)

    if args.demo:
        from .demo import generate
        logger.info("DEMO MODE — синтетические данные, krisha.kz не запрашивается")
        sale, rent = generate()
    else:
        from .scraper import Scraper
        try:
            sale, rent = Scraper(cfg).scrape()
        except Exception as err:  # noqa: BLE001
            logger.error("Скрапинг не удался: %s", err)
            logger.error("krisha.kz недоступен или блокирует запросы. "
                         "Запустите с локального IP в РК или используйте --demo.")
            return 1

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
