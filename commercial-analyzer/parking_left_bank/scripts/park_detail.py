"""Fetch krisha parking detail pages: exact coords, complexId, spaces count, parking type, full description.
usage: park_detail.py <list.json> <out.jsonl>   (resumable; skips ids already in out)"""
import json, os, random, re, sys, time
import requests
from bs4 import BeautifulSoup

list_path, out_path = sys.argv[1], sys.argv[2]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "ru,kk;q=0.8"})
done = set()
if os.path.exists(out_path):
    for l in open(out_path, encoding="utf-8"):
        try:
            r = json.loads(l)
            if r.get("ok"):
                done.add(r["id"])
        except Exception:
            pass
ids = [r["id"] for r in json.load(open(list_path)) if r["kind"] == "Паркинг" and r["id"] not in done]
print(f"to fetch {len(ids)} (done {len(done)})", flush=True)


def get(url):
    for a in range(4):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 410):
                return ""
        except Exception:
            pass
        time.sleep(3 * 2 ** a + random.random())
    return None


def window_data(html):
    i = html.find("window.data")
    if i < 0:
        return {}
    j = html.find("</script>", i)
    t = html[i:j]
    try:
        return json.loads(t[t.find("{"):].strip().rstrip(";"))
    except Exception:
        return {}


with open(out_path, "a", encoding="utf-8") as fo:
    for n, i in enumerate(ids, 1):
        html = get(f"https://krisha.kz/kz/a/show/{i}")
        if html is None:
            html = get(f"https://krisha.kz/a/show/{i}")
        rec = {"id": i, "ok": bool(html)}
        if html:
            s = BeautifulSoup(html, "html.parser")
            f = {}
            for it in s.select(".offer__info-item[data-name]"):
                v = it.select_one(".offer__advert-short-info")
                f[it["data-name"]] = v.get_text(" ", strip=True) if v else it.get_text(" ", strip=True)
            for dt in s.select("dl dt"):
                dd = dt.find_next_sibling("dd")
                if dd:
                    f[dt.get("data-name") or dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
            a = window_data(html).get("advert") or {}
            mp = a.get("map") or {}
            rec.update(lat=mp.get("lat"), lon=mp.get("lon"), price=a.get("price"), complex_id=a.get("complexId"),
                       title=a.get("title"), address_title=a.get("addressTitle"), user_type=a.get("userType"),
                       status=a.get("status"), storage=a.get("storage"), address=a.get("address"), fields=f)
            d = s.select_one(".a-text") or s.select_one(".offer__description")
            rec["desc"] = d.get_text(" ", strip=True) if d else ""
            pub = re.search(r'"createdAt"\s*:\s*"([^"]+)"', html) or re.search(r'"addedAt"\s*:\s*"([^"]+)"', html)
            rec["created"] = pub.group(1) if pub else None
        fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
        if n % 25 == 0:
            print(n, flush=True)
        time.sleep(0.9 + random.random())
