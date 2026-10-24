import glob, json, re
from bs4 import BeautifulSoup
def num(t):
    t = re.sub(r"[^\d]", "", t or ""); return int(t) if t else None
recs = {}
for fn in sorted(glob.glob("pages/*.html")):
    deal = fn.split("/")[1].split("_")[0]
    s = BeautifulSoup(open(fn).read(), "html.parser")
    for c in s.select(".a-card[data-id]"):
        g = lambda cl: (c.select_one(cl).get_text(" ", strip=True) if c.select_one(cl) else "")
        t = g(".a-card__title")
        area = re.search(r"·\s*([\d\s.,]+)\s*м²", t)
        prices = [x.get_text(" ", strip=True) for x in c.select(".a-card__price")]
        stats = [x.get_text(" ", strip=True) for x in c.select(".a-card__stats-item")]
        recs[c["data-id"]] = dict(id=c["data-id"], deal=deal, title=t, uses=t.split("·")[0].strip(),
            area=float(area.group(1).replace(" ", "").replace(",", ".")) if area else None,
            price_text=" / ".join(prices), price=(num(re.match(r"\s*([\d\s\xa0]+)", prices[0]).group(1)) if prices and re.match(r"\s*[\d]", prices[0]) else None),
            address=g(".a-card__subtitle"), preview=g(".a-card__text-preview"), owner=g(".a-card__owner-label"),
            city=stats[0] if stats else None, date=stats[1] if len(stats) > 1 else None,
            card=c.get_text(" | ", strip=True)[:600])
json.dump(list(recs.values()), open("list_all.json", "w"), ensure_ascii=False)
with open("ids.jsonl", "w") as f:
    for r in recs.values(): f.write(json.dumps({"id": r["id"]}) + "\n")
from collections import Counter
print(Counter(r["deal"] for r in recs.values()), Counter(r["city"] for r in recs.values()).most_common(5))
for r in list(recs.values())[:3]: print(r["price_text"], "|", r["card"][:250])
