"""Save every krisha list page (raw HTML) for Pavlodar commercial rent and sale; two sort orders so nothing slips."""
import os, re, sys, time, random, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kget import get
from bs4 import BeautifulSoup
os.makedirs("pages", exist_ok=True)
def found(h):
    m = re.search(r"Найдено\s*<span>([\d\s\xa0]+)</span>", h); return int(re.sub(r"\D", "", m.group(1))) if m else 0
ids = {}
for deal, path in (("rent", "arenda"), ("sale", "prodazha")):
    for sort in ("price-asc", "price-desc", ""):
        p, n = 1, None
        while True:
            fn = f"pages/{deal}_{sort or 'date'}_{p}.html"
            if os.path.exists(fn):
                h = open(fn).read()
            else:
                params = {"page": str(p)} if p > 1 else {}
                if sort: params["sort_by"] = sort
                h = get(f"https://krisha.kz/{path}/kommercheskaya-nedvizhimost/pavlodar/", params)
                if not h: print("FAILED", deal, sort, p); break
                open(fn, "w").write(h); time.sleep(1.2 + random.random())
            n = n or found(h)
            for c in BeautifulSoup(h, "html.parser").select(".a-card[data-id]"):
                ids.setdefault(deal, set()).add(c["data-id"])
            if p * 20 >= n: break
            p += 1
        print(deal, sort or "date", "found", n, "unique so far", len(ids[deal]), flush=True)
json.dump({k: sorted(v) for k, v in ids.items()}, open("ids.json", "w"))
print("DONE")
