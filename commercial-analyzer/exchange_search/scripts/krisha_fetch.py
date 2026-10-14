"""Fetch krisha detail pages for ids (exact map coords, info fields, full description).
usage: krisha_fetch.py <ids.txt> <out.jsonl>   (resumable; skips ids already in out)"""
import json, os, random, re, sys, time
import requests
from bs4 import BeautifulSoup

ids_path, out_path = sys.argv[1], sys.argv[2]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "ru,kk;q=0.8"})
MAP = re.compile(r'"map"\s*:\s*\{\s*"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lon"\s*:\s*(-?\d+\.\d+)')
done = set()
if os.path.exists(out_path):
    for l in open(out_path, encoding="utf-8"):
        try: done.add(json.loads(l)["id"])
        except Exception: pass
ids = [i.strip() for i in open(ids_path) if i.strip() and i.strip() not in done]
print(f"to fetch {len(ids)} (done {len(done)})", flush=True)


def get(url):
    for a in range(6):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 410):
                return ""
        except Exception:
            pass
        time.sleep(min(60, 4 * 2 ** a) + random.random())
    return None


with open(out_path, "a", encoding="utf-8") as fo:
    for n, i in enumerate(ids, 1):
        html = get(f"https://krisha.kz/a/show/{i}") or get(f"https://krisha.kz/kz/a/show/{i}")
        rec = {"id": i, "ok": bool(html)}
        if html:
            soup = BeautifulSoup(html, "html.parser")
            f = {}
            for it in soup.select(".offer__info-item[data-name]"):
                v = it.select_one(".offer__advert-short-info") or it.select_one("div:nth-of-type(3)")
                f[it["data-name"]] = v.get_text(" ", strip=True) if v else it.get_text(" ", strip=True)
            for dt in soup.select("dl dt"):
                dd = dt.find_next_sibling("dd")
                if dd:
                    f[dt.get("data-name") or dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
            m = MAP.search(html)
            if m:
                rec["lat"], rec["lon"] = float(m.group(1)), float(m.group(2))
            d = soup.select_one(".a-text") or soup.select_one(".offer__description")
            rec["desc"] = d.get_text(" ", strip=True) if d else ""
            t = soup.select_one("h1")
            rec["h1"] = t.get_text(" ", strip=True) if t else ""
            p = soup.select_one(".offer__price")
            rec["price_text"] = p.get_text(" ", strip=True) if p else ""
            rec["fields"] = f
            rec["archived"] = bool(re.search(r"архивн|снято с публикации|мұрағат", html[:200000], re.I) and not f)
        fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
        if n % 20 == 0:
            print(n, flush=True)
        time.sleep(1.2 + random.random())
