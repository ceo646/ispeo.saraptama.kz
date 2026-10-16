"""Scrape krisha «Продажа гаражей и паркингов» list pages for Есиль and Нура.
usage: park_list.py <out.json>"""
import json, random, re, sys, time
import requests
from bs4 import BeautifulSoup

out = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "ru,kk;q=0.8"})


def get(url):
    for a in range(6):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        time.sleep(min(60, 4 * 2 ** a) + random.random())
    return None


def num(t):
    t = re.sub(r"[^\d]", "", t or "")
    return int(t) if t else None


rows = {}
for district in ("astana-esilskij", "astana-nura"):
    page, total = 1, None
    while True:
        url = f"https://krisha.kz/prodazha/garazhi/{district}/" + (f"?page={page}" if page > 1 else "")
        h = get(url)
        if not h:
            print("FAILED", url, flush=True); break
        s = BeautifulSoup(h, "html.parser")
        if total is None:
            m = re.search(r"Найдено\s*<span>(\d+)</span>", h)
            total = int(m.group(1)) if m else 0
        cards = s.select(".a-card[data-id]")
        new = 0
        for c in cards:
            i = c["data-id"]
            if i in rows:
                continue
            title = c.select_one(".a-card__title")
            price = c.select_one(".a-card__price")
            addr = c.select_one(".a-card__subtitle")
            prev = c.select_one(".a-card__text-preview")
            owner = c.select_one(".a-card__owner-label") or c.select_one(".a-card__owner")
            t = title.get_text(" ", strip=True) if title else ""
            m = re.search(r"([\d.,]+)\s*м²", t)
            pv = prev.get_text(" ", strip=True) if prev else ""
            cm = re.match(r"жил\. комплекс\s+([^,]+)", pv)
            rows[i] = dict(id=i, district=district, title=t, kind=t.split("·")[0].strip(),
                           area=float(m.group(1).replace(",", ".")) if m else None,
                           price=num(price.get_text() if price else ""),
                           address=addr.get_text(" ", strip=True) if addr else "",
                           complex=cm.group(1).strip() if cm else None, preview=pv,
                           owner=owner.get_text(" ", strip=True) if owner else "",
                           card_text=c.get_text(" | ", strip=True)[:600])
            new += 1
        print(district, page, len(cards), new, total, flush=True)
        if not cards or page * 20 >= total:
            break
        page += 1
        time.sleep(1.5 + random.random())
json.dump(list(rows.values()), open(out, "w"), ensure_ascii=False, indent=1)
print("rows", len(rows))
