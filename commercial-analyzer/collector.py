#!/usr/bin/env python3
"""Лёгкий сборщик сырых страниц krisha.kz — для запуска с ТЕЛЕФОНА.

Работает в Termux (Android) или iSH (iPhone). Единственная зависимость —
`requests`. Ничего не парсит и не анализирует: просто скачивает страницы
выдачи (продажа + аренда коммерции) и карточки объявлений о продаже,
сжимает gzip'ом и складывает в data/raw/<дата>/. Дальше анализ делает
Claude в облачной сессии, забрав данные из GitHub.

Запуск:  python collector.py
Повторный запуск в тот же день докачивает недостающее (resume).
"""

from __future__ import annotations

import gzip
import json
import random
import re
import sys
import time
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Нет модуля requests. Установите: pip install requests")

# ------------------------- настройки -------------------------
CITY = "astana"
PRICE_TO = 100_000_000          # ₸, серверный фильтр для продажи
MAX_LIST_PAGES = 25             # страниц выдачи на раздел
MAX_DETAILS = 300               # максимум карточек продажи
DELAY = (2.0, 4.5)              # пауза между запросами, сек
OUT_DIR = Path(__file__).parent / "data" / "raw" / date.today().isoformat()

SALE_URL = f"https://krisha.kz/prodazha/kommercheskaya-nedvizhimost/{CITY}/"
RENT_URL = f"https://krisha.kz/arenda/kommercheskaya-nedvizhimost/{CITY}/"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0.0.0 Safari/537.36"),
    "Accept-Language": "ru,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

AD_ID_RE = re.compile(r"/a/show/(\d+)")

session = requests.Session()
session.headers.update(HEADERS)


def sleep():
    time.sleep(random.uniform(*DELAY))


def fetch(url: str, params: dict | None = None) -> str | None:
    for attempt in range(1, 4):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.text
            print(f"  ! HTTP {r.status_code} на {url} (попытка {attempt}/3)")
        except requests.RequestException as e:
            print(f"  ! ошибка сети: {e} (попытка {attempt}/3)")
        time.sleep(5 * attempt)
    return None


def save(name: str, html: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT_DIR / f"{name}.html.gz", "wt", encoding="utf-8") as f:
        f.write(html)


def crawl_list(base: str, params: dict, prefix: str) -> set[str]:
    """Скачать страницы выдачи; вернуть найденные id объявлений."""
    ids: set[str] = set()
    for page in range(1, MAX_LIST_PAGES + 1):
        fname = f"{prefix}_list_p{page:02d}"
        cached = OUT_DIR / f"{fname}.html.gz"
        if cached.exists():
            with gzip.open(cached, "rt", encoding="utf-8") as f:
                html = f.read()
            print(f"[{prefix}] стр. {page}: уже скачана")
        else:
            p = dict(params)
            if page > 1:
                p["page"] = str(page)
            html = fetch(base, p)
            if html is None:
                print(f"[{prefix}] стр. {page}: не удалось — стоп")
                break
            save(fname, html)
            sleep()
        found = set(AD_ID_RE.findall(html))
        new = found - ids
        print(f"[{prefix}] стр. {page}: +{len(new)} объявлений "
              f"(всего {len(ids | found)})")
        if page > 1 and not new:
            print(f"[{prefix}] новых нет — конец выдачи")
            break
        ids |= found
    return ids


def crawl_details(ids: set[str]) -> int:
    ok = 0
    todo = sorted(ids)[:MAX_DETAILS]
    for i, ad_id in enumerate(todo, 1):
        fname = f"ad_{ad_id}"
        if (OUT_DIR / f"{fname}.html.gz").exists():
            ok += 1
            continue
        html = fetch(f"https://krisha.kz/a/show/{ad_id}")
        if html:
            save(fname, html)
            ok += 1
        if i % 10 == 0:
            print(f"[детали] {i}/{len(todo)} (сохранено {ok})")
        sleep()
    return ok


def main() -> int:
    print(f"Сбор krisha.kz / {CITY} → {OUT_DIR}")
    print("Не выключайте экран/интернет. Займёт ~15–30 минут.\n")

    sale_ids = crawl_list(
        SALE_URL, {"das[price][to]": str(PRICE_TO)}, "sale")
    rent_ids = crawl_list(RENT_URL, {}, "rent")

    if not sale_ids and not rent_ids:
        print("\nНИЧЕГО не скачано — похоже, krisha блокирует. "
              "Попробуйте позже или с другой сети (мобильный интернет).")
        return 1

    print(f"\nКачаю карточки продажи ({min(len(sale_ids), MAX_DETAILS)} шт.)…")
    details = crawl_details(sale_ids)

    manifest = {
        "date": date.today().isoformat(),
        "city": CITY,
        "price_to": PRICE_TO,
        "sale_ids": len(sale_ids),
        "rent_ids": len(rent_ids),
        "detail_pages_saved": details,
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nГотово: продажа {len(sale_ids)} id, аренда {len(rent_ids)} id, "
          f"карточек {details}. Манифест: {OUT_DIR}/manifest.json")
    print("Теперь запустите: bash collect_and_push.sh  (или git add/commit/push)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
