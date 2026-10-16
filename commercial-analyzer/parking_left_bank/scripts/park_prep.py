"""Merge list + detail scrape, apply deterministic checks and pick listings that need a human-grade review.
usage: park_prep.py <park_dir>   -> <park_dir>/merged.json, review_batches.json, auto_ok.json"""
import glob, json, random, re, sys
from shapely.geometry import Point, shape, Polygon
from shapely.prepared import prep

d = sys.argv[1]
L = {r["id"]: r for r in json.load(open(f"{d}/list.json")) if r["kind"] == "Паркинг"}
D = {}
for f in [f"{d}/details.jsonl"] + sorted(glob.glob(f"{d}/details_s*.jsonl")):
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        if r.get("ok"):
            D[r["id"]] = r
B = json.load(open(f"{d}/build/basemap.json"))
left = prep(Polygon(B["left"][0][0], B["left"][0][1:]))

KW = re.compile(r"(\b(2|3|4|5|два|две|двух|три|трёх|трех|четыре|несколько|оба|обa)\s*(парк|машин|мест|м/м|парковоч))|"
                r"(места?\s+рядом)|(рядом\s+(ещ[её]\s+)?(одно\s+)?мест)|(\bдол[яи]\b)|(\bбокс)|(гараж)|(открыт)|(навес)|"
                r"(кладов|келлер|бокс для хранен|хозблок|подсобн)|(аренд|сда[её]тся|сдам)|(мото)|(за вс[её]|каждое|за одно|за 1\b)|"
                r"(предчистов|котлован|строящ)", re.I)


def num(x):
    try:
        return float(str(x).replace(",", ".").split()[0])
    except Exception:
        return None


rows, review, auto = [], [], []
for i, l in L.items():
    dt = D.get(i, {})
    f = dt.get("fields", {})
    price = dt.get("price") or l.get("price")
    area = l.get("area") or num((f.get("land.square") or "").replace("Нысанның ауданы", ""))
    spaces = num(f.get("garage.spaces_count", "").split()[-1]) if f.get("garage.spaces_count") else None
    ptype = f.get("garage.parking_type")
    ptype = {"Жерасты": "подземный", "Подземная": "подземный", "Жерүсті": "наземный", "Наземная": "наземный"}.get(ptype, ptype)
    desc = dt.get("desc") or l.get("preview") or ""
    lat, lon = dt.get("lat"), dt.get("lon")
    inside = bool(lat and lon and left.contains(Point(lon, lat)))
    cx = (f.get("map.complex") or "").replace("Тұрғын үй кешені", "").strip() or l.get("complex")
    r = dict(id=i, url=f"https://krisha.kz/a/show/{i}", district="Есиль" if l["district"] == "astana-esilskij" else "Нура",
             address=l["address"], complex=cx, complex_id=dt.get("complex_id"), price=price, area=area, spaces=spaces,
             parking_type=ptype, lat=lat, lon=lon, inside_left_bank=inside, owner=l.get("owner"), user_type=dt.get("user_type"),
             amenities=f.get("garage.amenities"), comms=f.get("garage.communications"), desc=desc[:1500], fetched=bool(dt))
    flags = []
    if not dt:
        flags.append("нет карточки")
    if not inside:
        flags.append("вне левого берега по координатам")
    if ptype != "подземный":
        flags.append(f"тип: {ptype}")
    if spaces and spaces != 1:
        flags.append(f"мест в объявлении: {spaces:g}")
    if not price or price < 1_000_000 or price > 20_000_000:
        flags.append("цена вне 1–20 млн")
    if area and (area > 25 or area < 9):
        flags.append(f"площадь {area:g}")
    m = KW.search(desc + " " + l.get("title", ""))
    if m:
        flags.append(f"ключевое слово: «{m.group(0)}»")
    r["flags"] = flags
    rows.append(r)
    (review if flags else auto).append(r)

import os
seen = set(json.load(open(f"{d}/reviewed_ids.json"))) if os.path.exists(f"{d}/reviewed_ids.json") else set()
review = [r for r in review if r["fetched"] and r["id"] not in seen]
random.seed(7)
qa = [r for r in random.sample(auto, min(60, len(auto))) if r["id"] not in seen][:max(0, 60 - len([1 for x in seen if x in {a["id"] for a in auto}]))]  # audit sample of the auto-accepted ones
for r in qa:
    r["qa_sample"] = True
todo = review + qa
BS = 55
batches = [todo[k:k + BS] for k in range(0, len(todo), BS)]
json.dump(rows, open(f"{d}/merged.json", "w"), ensure_ascii=False, indent=1)
json.dump(auto, open(f"{d}/auto_ok.json", "w"), ensure_ascii=False, indent=1)
json.dump(todo, open(f"{d}/review_todo.json", "w"), ensure_ascii=False, indent=1)
json.dump([[k, k + len(b)] for k, b in zip(range(0, len(todo), BS), batches)], open(f"{d}/review_ranges.json", "w"))
print("listings", len(rows), "with detail", sum(r["fetched"] for r in rows), "auto", len(auto), "review", len(review),
      "qa", len(qa), "batches", len(batches))
import collections
print(collections.Counter(x.split(":")[0] for r in review for x in r["flags"]).most_common())
