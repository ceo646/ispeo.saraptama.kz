"""Open krisha.kz listing pages: exact coordinates, complex id, all attributes and the full description.

The Russian page /a/show/<id> answers scripts with HTTP 468, so the Kazakh mirror /kz/a/show/<id> is used.
Attribute keys (data-name) are language independent; their values on the mirror are in Kazakh.
Resumable; run several copies on disjoint shards (--shard k --of n) to go faster (3 workers worked well).

usage: python3 -P -E krisha_detail.py <list.jsonl> <out.jsonl> [--shard 0 --of 3]
"""
import argparse, json, os, random, sys, time
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ru,kk;q=0.8"})


def get(url):
    for a in range(5):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 410):
                return ""                                   # removed listing
            if r.status_code in (403, 429, 468):
                time.sleep(60 * (a + 1))                    # throttled: back off, do not try to get around it
        except requests.RequestException:
            pass
        time.sleep(3 * 2 ** a + random.random())
    return None


def window_data(html):
    i = html.find("window.data")
    if i < 0:
        return {}
    t = html[i:html.find("</script>", i)]
    try:
        return json.loads(t[t.find("{"):].strip().rstrip(";"))
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out")
    ap.add_argument("--shard", type=int, default=0); ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--sleep", type=float, default=1.0)
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("ok"):
                    done.add(r["id"])
            except Exception:
                pass
    ids = [json.loads(l)["id"] for l in open(a.inp, encoding="utf-8") if l.strip()]
    ids = [i for k, i in enumerate(ids) if k % a.of == a.shard and i not in done]
    print(f"to fetch {len(ids)} (done {len(done)})", flush=True)
    with open(a.out, "a", encoding="utf-8") as fo:
        for n, i in enumerate(ids, 1):
            html = get(f"https://krisha.kz/kz/a/show/{i}")
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
                adv = window_data(html).get("advert") or {}
                mp = adv.get("map") or {}
                d = s.select_one(".a-text") or s.select_one(".offer__description")
                rec.update(lat=mp.get("lat"), lon=mp.get("lon"), price=adv.get("price"), rooms=adv.get("rooms"),
                           square=adv.get("square"), complex_id=adv.get("complexId"), title=adv.get("title"),
                           address_title=adv.get("addressTitle"), address=adv.get("address"),
                           user_type=adv.get("userType"), status=adv.get("status"), fields=f,
                           desc=d.get_text(" ", strip=True) if d else "")
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
            if n % 25 == 0:
                print(n, flush=True)
            time.sleep(a.sleep + random.random())


if __name__ == "__main__":
    main()
