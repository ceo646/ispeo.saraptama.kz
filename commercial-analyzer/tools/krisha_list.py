"""Collect every krisha.kz listing card for a section/category/region, beating the 1000-page cap.

krisha shows at most 1000 pages x 20 cards per search. When a search finds more than CAP listings, the
script splits it into price slices (das[price][from|to]) recursively until each slice fits, then pages
through every slice. Output is one JSON line per listing card, deduplicated by id; the run is resumable.

usage:
  python3 -P -E krisha_list.py <out.jsonl> --path prodazha/kvartiry --regions astana-esilskij astana-nura ...
  extra query (filters) can be passed with --query 'das[who]=1&das[live.rooms][]=2'
"""
import argparse, json, os, random, re, sys, time
import requests
from bs4 import BeautifulSoup

CAP = 19000          # keep slices safely under 1000 pages x 20 cards
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ru,kk;q=0.8"})


def get(url):
    for a in range(6):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                return r.text
            print("HTTP", r.status_code, url, file=sys.stderr, flush=True)
            if r.status_code in (403, 429, 468):   # throttled or challenged: back off hard, never try to solve it
                time.sleep(60 * (a + 1))
        except requests.RequestException:
            pass                                   # the agent proxy sometimes resets the tunnel; just retry
        time.sleep(min(60, 3 * 2 ** a) + random.random())
    return None


def found(html):
    m = re.search(r"Найдено\s*<span>([\d\s\xa0]+)</span>", html)
    return int(re.sub(r"\D", "", m.group(1))) if m else 0


def title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m.group(1).strip() if m else ""


def url_for(path, region, query, lo=None, hi=None, page=1):
    q = [query] if query else []
    if lo is not None:
        q.append(f"das[price][from]={lo}")
    if hi is not None:
        q.append(f"das[price][to]={hi}")
    q.append("sort_by=price-asc")                 # stable order inside a slice
    if page > 1:
        q.append(f"page={page}")
    return f"https://krisha.kz/{path}/{region}/?" + "&".join(q)


def slices(path, region, query, lo=0, hi=5_000_000_000):
    """Yield (lo, hi, count) price slices whose count fits under CAP."""
    h = get(url_for(path, region, query, lo, hi))
    n = found(h or "")
    if n <= CAP or hi - lo < 100_000:
        if n > CAP:
            print(f"WARNING slice {lo}-{hi} still has {n} > {CAP}; tail will be cut", file=sys.stderr)
        yield lo, hi, n
        return
    mid = (lo + hi) // 2 if hi < 5_000_000_000 else 60_000_000   # first split near the market median
    yield from slices(path, region, query, lo, mid)
    yield from slices(path, region, query, mid + 1, hi)


def num(t):
    t = re.sub(r"[^\d]", "", t or "")
    return int(t) if t else None


def parse_cards(html, region):
    s = BeautifulSoup(html, "html.parser")
    out = []
    for c in s.select(".a-card[data-id]"):
        g = lambda cl: (c.select_one(cl).get_text(" ", strip=True) if c.select_one(cl) else "")
        t = g(".a-card__title")
        rooms = re.match(r"(\d+)-комнат", t)
        area = re.search(r"([\d.,]+)\s*м²", t)
        fl = re.search(r"(\d+)/(\d+)\s*этаж", t)
        pv = g(".a-card__text-preview")
        cx = re.match(r"жил\. комплекс\s+([^,]+)", pv)
        yr = re.search(r"(\d{4})\s*г\.п\.", pv)
        stats = [x.get_text(" ", strip=True) for x in c.select(".a-card__stats-item")]
        out.append(dict(id=c["data-id"], region=region, title=t, price=num(g(".a-card__price")),
                        rooms=int(rooms.group(1)) if rooms else None,
                        area=float(area.group(1).replace(",", ".")) if area else None,
                        floor=int(fl.group(1)) if fl else None, floors=int(fl.group(2)) if fl else None,
                        address=g(".a-card__subtitle"), complex=cx.group(1).strip() if cx else None,
                        year=int(yr.group(1)) if yr else None, preview=pv, owner=g(".a-card__owner-label"),
                        city=stats[0] if stats else None, date=stats[1] if len(stats) > 1 else None))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--path", default="prodazha/kvartiry")
    ap.add_argument("--regions", nargs="+", required=True)
    ap.add_argument("--query", default="")
    ap.add_argument("--sleep", type=float, default=1.5)
    a = ap.parse_args()
    seen = set()
    if os.path.exists(a.out):
        for l in open(a.out, encoding="utf-8"):
            try:
                seen.add(json.loads(l)["id"])
            except Exception:
                pass
    with open(a.out, "a", encoding="utf-8") as fo:
        for region in a.regions:
            h = get(url_for(a.path, region, a.query))
            if not h:
                print("FAILED", region, file=sys.stderr); continue
            print(region, "found", found(h), "|", title(h)[:80], flush=True)
            if "в Казахстане" in title(h):   # an unknown slug silently falls back to the whole country
                print("WARNING: unknown region slug, krisha fell back to all of Kazakhstan:", region, file=sys.stderr)
                continue
            for lo, hi, n in slices(a.path, region, a.query):
                pages = (n + 19) // 20
                print(f"  slice {lo:>11}-{hi:<11} {n:6d} listings, {pages} pages", flush=True)
                for p in range(1, min(pages, 1000) + 1):
                    h = get(url_for(a.path, region, a.query, lo, hi, p))
                    if not h:
                        print("  FAILED page", p, file=sys.stderr); continue
                    new = 0
                    for r in parse_cards(h, region):
                        if r["id"] not in seen:
                            seen.add(r["id"]); fo.write(json.dumps(r, ensure_ascii=False) + "\n"); new += 1
                    fo.flush()
                    if p % 50 == 0:
                        print(f"    page {p}/{pages}, total {len(seen)}", flush=True)
                    time.sleep(a.sleep + random.random())
    print("done, listings:", len(seen))


if __name__ == "__main__":
    main()
