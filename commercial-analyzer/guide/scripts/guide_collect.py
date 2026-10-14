"""Collect krisha.kz Astana commercial listings (rent all + sale <=100M) with
full detail-page parameters, for the office-selection guide.

Outputs (OUT dir): list_rent.json, list_sale.json, coords_rent.json,
coords_sale.json, details.jsonl (checkpointed), done.marker
"""
import json, os, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/home/user/ispeo.saraptama.kz/commercial-analyzer")
import requests
from bs4 import BeautifulSoup
from analyzer import parse, mapsource

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
_tl = threading.local()


def sess():
    if not hasattr(_tl, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "ru,en;q=0.9",
                          "Accept-Encoding": "gzip, deflate"})
        _tl.s = s
    return _tl.s


BACKOFF = (5, 20, 60, 120, 240, 300)


def get(url, params=None, tries=6):
    for a in range(tries):
        try:
            r = sess().get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.text
            log("HTTP", r.status_code, url[:80])
        except requests.RequestException as e:
            log("net", type(e).__name__, url[:80], "sleep", BACKOFF[a])
        time.sleep(BACKOFF[a] + random.random() * 3)
    return None


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def crawl_list(deal, params, cap=400):
    base = f"https://krisha.kz/{'arenda' if deal == 'rent' else 'prodazha'}/kommercheskaya-nedvizhimost/astana/"
    first = get(base, params)
    if first is None:
        raise RuntimeError(f"list {deal}: first page unreachable")
    total = min(parse.get_total_pages(first), cap)
    log(deal, "pages:", total)
    stubs = parse.parse_list_page(first, deal, "astana")
    lock = threading.Lock()

    def one(p):
        html = get(base, dict(params, page=str(p)))
        time.sleep(random.uniform(0.6, 1.2))
        return parse.parse_list_page(html, deal, "astana") if html else []

    with ThreadPoolExecutor(3) as ex:
        for i, res in enumerate(ex.map(one, range(2, total + 1)), 2):
            stubs.extend(res)
            if i % 50 == 0:
                log(deal, "page", i, "stubs", len(stubs))
    uniq = {s["id"]: s for s in stubs}
    log(deal, "unique:", len(uniq))
    return list(uniq.values())


_MAP_RE = re.compile(r'"map"\s*:\s*\{\s*"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lon"\s*:\s*(-?\d+\.\d+)')
_CID_RE = re.compile(r'"complexId"\s*:\s*(\d+|null)')
_ADDR_RE = re.compile(r'"address"\s*:\s*(\{[^{}]*\})')
_OWNER_RE = re.compile(r'"userType"\s*:\s*"([^"]*)"')


def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    d = {}
    h1 = soup.select_one(".offer__advert-title h1")
    d["title"] = h1.get_text(" ", strip=True) if h1 else None
    for it in soup.select(".offer__info-item[data-name]"):
        v = it.select_one(".offer__advert-short-info")
        d[it["data-name"]] = v.get_text(" ", strip=True) if v else None
    for dl in soup.select(".offer__parameters dl"):
        dt, dd = dl.select_one("dt"), dl.select_one("dd")
        if dt is not None and dd is not None:
            d[dt.get("data-name") or dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
    p = soup.select_one(".offer__price")
    d["price_text"] = p.get_text(" ", strip=True) if p else None
    desc = soup.select_one(".js-description")
    d["description"] = desc.get_text(" ", strip=True) if desc else None
    m = _MAP_RE.search(html)
    if m:
        d["lat"], d["lon"] = float(m.group(1)), float(m.group(2))
    cm = _CID_RE.search(html)
    d["complexId"] = None if not cm or cm.group(1) == "null" else int(cm.group(1))
    am = _ADDR_RE.search(html)
    if am:
        try:
            d["address_json"] = json.loads(am.group(1))
        except ValueError:
            pass
    om = _OWNER_RE.search(html)
    d["userType"] = om.group(1) if om else None
    d["photos"] = len(set(re.findall(r'https://krisha-photos\.kcdn\.online/webp/[a-f0-9]{2}/[a-f0-9-]{36}/', html)))
    return d


def crawl_details(stubs, ck_path, workers=5):
    done = set()
    if os.path.exists(ck_path):
        for line in open(ck_path, encoding="utf-8"):
            try:
                done.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                pass
    todo = [s for s in stubs if s["id"] not in done]
    log("details todo:", len(todo), "done:", len(done))
    lock = threading.Lock()
    ck = open(ck_path, "a", encoding="utf-8")
    n = [0]

    def work(s):
        html = get(s["url"])
        rec = {"id": s["id"], "deal": s["deal"], "list": {k: s.get(k) for k in ("title", "price", "area", "district", "address")}}
        if html:
            try:
                rec["detail"] = parse_detail(html)
            except Exception as e:  # noqa
                rec["error"] = repr(e)
        else:
            rec["error"] = "fetch"
        with lock:
            ck.write(json.dumps(rec, ensure_ascii=False) + "\n"); ck.flush()
            n[0] += 1
            if n[0] % 200 == 0:
                log("details", n[0], "/", len(todo))
        time.sleep(random.uniform(0.6, 1.2))

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, todo))
    ck.close()


if __name__ == "__main__":
    t0 = time.time()
    time.sleep(int(os.environ.get("INITIAL_SLEEP", "0")))
    if os.path.exists(f"{OUT}/list_rent.json"):
        rent = json.load(open(f"{OUT}/list_rent.json"))
    else:
        rent = crawl_list("rent", {})
        json.dump(rent, open(f"{OUT}/list_rent.json", "w"), ensure_ascii=False)
    if os.path.exists(f"{OUT}/list_sale.json"):
        sale = json.load(open(f"{OUT}/list_sale.json"))
    else:
        sale = crawl_list("sale", {"das[price][to]": "100000000"})
        json.dump(sale, open(f"{OUT}/list_sale.json", "w"), ensure_ascii=False)
    log("lists done", len(rent), len(sale), round(time.time() - t0), "s")
    for deal, sec in (("rent", "arenda/kommercheskaya-nedvizhimost/"), ("sale", "prodazha/kommercheskaya-nedvizhimost/")):
        if os.path.exists(f"{OUT}/coords_{deal}.json"):
            continue
        try:
            c = mapsource.coords_for_city(sec, mapsource.CITY_BBOX["astana"],
                                          filters={"das[price][to]": "100000000"} if deal == "sale" else None,
                                          workers=5, verbose=True)
            json.dump(c, open(f"{OUT}/coords_{deal}.json", "w"))
            log(deal, "coords:", len(c))
        except Exception as e:  # noqa
            log(deal, "coords failed", repr(e))
    log("coords done", round(time.time() - t0), "s")
    random.seed(1)
    order = rent + sale
    random.shuffle(order)   # interleave so a partial run is still a random sample
    crawl_details(order, f"{OUT}/details.jsonl", workers=3)
    log("ALL DONE", round(time.time() - t0), "s")
    open(f"{OUT}/done.marker", "w").write("ok")
