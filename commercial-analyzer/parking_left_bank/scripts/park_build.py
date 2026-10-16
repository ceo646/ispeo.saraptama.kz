"""Merge auto-accepted listings with the agents' review and render the interactive map.
usage: park_build.py <park_dir> <out.html> [workflow_output.json ...]
Writes <park_dir>/final_listings.json and the page."""
import json, re, statistics, sys
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

d, out_html, wf_paths = sys.argv[1], sys.argv[2], sys.argv[3:]
merged = {r["id"]: r for r in json.load(open(f"{d}/merged.json"))}
auto = {r["id"] for r in json.load(open(f"{d}/auto_ok.json"))}
B = json.load(open(f"{d}/build/basemap.json"))
left = prep(Polygon(B["left"][0][0], B["left"][0][1:]))

# agent decisions: verifier overrides classifier
dec = {}
for p in wf_paths:
    o = json.load(open(p))
    res = o.get("result", o)
    for b in res.get("results") or []:
        for it in b.get("items") or []:
            dec[str(it["id"])] = dict(it, source="classifier")
        for it in b.get("verified") or []:
            first = dec.get(str(it["id"]))
            dec[str(it["id"])] = dict(it, source="verifier", first=first)

TYPE = {"underground": "u", "covered_above_ground": "c", "above_ground_unclear": "a"}
final, excluded = [], []
for i, r in merged.items():
    x = dec.get(i)
    if x is None and i not in auto:
        excluded.append(dict(id=i, why="не проверено")); continue
    if x is None:  # auto-accepted ordinary underground single place
        rec = dict(r, ppp=r["price"], t="u", storage=False, uc=False, why="авто")
    else:
        t = TYPE.get(x["place_type"])
        keep = x["include"] or x["place_type"] == "above_ground_unclear"
        if not keep or not t or not x.get("price_per_place"):
            excluded.append(dict(id=i, why=x["place_type"], reason=x.get("reason_ru"), source=x["source"])); continue
        rec = dict(r, ppp=x["price_per_place"], t=t, storage=x["storage_included"], uc=x["under_construction"], why=x["reason_ru"],
                   places=x["places_in_price"], src=x["source"])
    if not (rec.get("lat") and rec.get("lon") and left.contains(Point(rec["lon"], rec["lat"]))):
        excluded.append(dict(id=i, why="координаты вне левого берега")); continue
    if not (700_000 <= rec["ppp"] <= 30_000_000):
        excluded.append(dict(id=i, why=f"цена за место {rec['ppp']}")); continue
    final.append(rec)

# duplicates: same complex + same price + same area -> keep one
seen, dedup = {}, []
for r in sorted(final, key=lambda r: r["id"]):
    k = ((r.get("complex") or "").lower(), r["ppp"], r.get("area"), r.get("desc", "")[:60])
    if k in seen:
        excluded.append(dict(id=r["id"], why=f"дубль {seen[k]}")); continue
    seen[k] = r["id"]
    dedup.append(r)
final = dedup


def gkey(r):
    if r.get("complex_id"):
        return f"c{r['complex_id']}"
    if r.get("complex"):
        return "n" + r["complex"].lower()
    return f"p{round(r['lat'], 3)},{round(r['lon'], 3)}"


listings = []
for r in final:
    a = r.get("area")
    if r.get("places", 1) and r.get("places", 1) > 1 and a:
        a = a / r["places"]
    listings.append(dict(id=r["id"], url=r["url"], lat=round(r["lat"], 6), lon=round(r["lon"], 6), p=round(r["ppp"]),
                         a=a if a and 9 <= a <= 25 else None, t=r["t"], cx=r.get("complex") or "", g=gkey(r),
                         d="Е" if r["district"] == "Есиль" else "Н", st=bool(r.get("storage")), uc=bool(r.get("uc"))))
json.dump(final, open(f"{d}/final_listings.json", "w"), ensure_ascii=False, indent=1)
json.dump(listings, open(f"{d}/map_listings.json", "w"), ensure_ascii=False, indent=1)
json.dump(excluded, open(f"{d}/excluded.json", "w"), ensure_ascii=False, indent=1)

nt = {k: sum(1 for x in listings if x["t"] == k) for k in "uca"}
notes = [
    f"Источник: все объявления о продаже паркингов в Есильском и Нура районах на krisha.kz на 16.10.2026 — 1 036 карточек, каждая открыта.",
    f"На карте {len(listings)} мест: {nt['u']} подземных, {nt['c']} наземных крытых и {nt['a']} наземных без уточнения (видны только в режиме «+ наземные»). "
    f"Убрано {len(excluded)}: гаражи-боксы, открытые стоянки, аренда, продажа целого паркинга, места без понятной цены, дубли.",
    "Если в объявлении несколько мест за одну цену, цена поделена на число мест. Цена — запрос продавца, сделки обычно на 5–15 % ниже.",
    "Поверхность — сглаженная медиана соседних ЖК (вес ЖК растёт с числом объявлений). Чем прозрачнее цвет, тем меньше рядом данных; там, где объявлений нет, цвета нет.",
]
landmarks = [dict(name="Хан Шатыра", lat=51.1325, lon=71.4039), dict(name="Байтерека", lat=51.1283, lon=71.4305),
             dict(name="EXPO", lat=51.0928, lon=71.4215), dict(name="Акорды", lat=51.1258, lon=71.4465),
             dict(name="ТРЦ Керуен", lat=51.1278, lon=71.4253)]
data = dict(date="16.10.2026", listings=listings, notes=notes, landmarks=landmarks)
tpl = open(f"{d}/build/template.html").read()
leaflet_css = open(f"{d}/build/leaflet.css").read()
leaflet_css = re.sub(r"url\([^)]*\)", "none", leaflet_css)
html = (tpl.replace("/*__LEAFLET_CSS__*/", leaflet_css)
        .replace("/*__BASEMAP__*/", json.dumps(B, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
        .replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
open(out_html, "w").write(html)
print("final", len(listings), nt, "excluded", len(excluded), "html KB", len(html) // 1024)
by = {}
for x in listings:
    by.setdefault(x["d"], []).append(x["p"])
print({k: (len(v), statistics.median(v)) for k, v in by.items()})
