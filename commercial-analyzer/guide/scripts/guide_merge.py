"""Merge curl details.jsonl + WebFetch wf/*.jsonl into one details file for guide_analyze.py.

Usage: python3 -E guide_merge.py <data dir> <wf dir> <out jsonl>
Adds coordinates from coords_rent.json / coords_sale.json and, when missing, from
korter complex coordinates matched by complex name.
"""
import glob, json, os, re, sys

DATA, WF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
lists = {}
for deal in ("rent", "sale"):
    p = f"{DATA}/list_{deal}.json"
    if os.path.exists(p):
        for x in json.load(open(p)):
            lists[x["id"]] = x
coords = {}
for deal in ("rent", "sale"):
    p = f"{DATA}/coords_{deal}.json"
    if os.path.exists(p):
        coords.update(json.load(open(p)))

KORTER = "/home/user/ispeo.saraptama.kz/commercial-analyzer/bigville/data/korter_astana_buildings.json"
kor = {}
if os.path.exists(KORTER):
    for b in json.load(open(KORTER)):
        name = re.sub(r"^(жк|кг|клубный дом)\s+", "", (b.get("name") or "").lower()).strip()
        name = re.sub(r"[^a-zа-яё0-9]+", " ", name).strip()
        if name and b.get("lat"):
            kor[name] = (b["lat"], b["lng"])


def kor_lookup(cname):
    n = re.sub(r"^(жк|кг)\s+", "", (cname or "").lower())
    n = re.sub(r"[^a-zа-яё0-9]+", " ", n).strip()
    if not n:
        return None
    if n in kor:
        return kor[n]
    for k, v in kor.items():
        if len(n) >= 5 and (n in k or k in n):
            return v
    return None


out, seen = [], set()
# 1) curl details
p = f"{DATA}/details.jsonl"
if os.path.exists(p):
    for line in open(p, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not r.get("detail") or r["id"] in seen:
            continue
        seen.add(r["id"])
        d = r["detail"]
        if not d.get("lat") and coords.get(r["id"]):
            d["lat"], d["lon"] = coords[r["id"]]["lat"], coords[r["id"]]["lon"]
        if not d.get("lat"):
            k = kor_lookup(d.get("office.complex_name"))
            if k:
                d["lat"], d["lon"], d["geo_src"] = k[0], k[1], "korter"
        r["src"] = "curl"
        out.append(r)

# 2) WebFetch rows
MAP = {"ceiling": "ceiling", "renovation": "com.renovation", "line": "com.location_line", "entrance": "com.entrance_opts",
       "parking": "com.parking_opts", "power_kw": "indust.max_electr", "communications": "com.communications",
       "placement": "com.location", "complex": "office.complex_name", "floor": "house.floor_num", "year": "house.year",
       "address": "map.street", "description": "description", "title": "title", "photos": "photos"}
for f in sorted(glob.glob(f"{WF}/*.jsonl")):
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            w = json.loads(line)
        except ValueError:
            continue
        wid = str(w.get("id") or "")
        if not wid or w.get("error") or wid in seen:
            continue
        L = lists.get(wid, {})
        price = w.get("price") or L.get("price")
        area = w.get("area_m2") or L.get("area")
        deal = w.get("deal") or L.get("deal")
        if deal not in ("rent", "sale"):
            continue
        if not price and w.get("price_per_m2") and area:
            price = w["price_per_m2"] * area
        d = {}
        for k, v in MAP.items():
            val = w.get(k)
            if val is not None and val != "":
                d[v] = str(val) if k in ("ceiling", "power_kw", "year", "floor") else val
        if "ceiling" in d:
            d["ceiling"] = d["ceiling"] + " м"
        if "indust.max_electr" in d:
            d["indust.max_electr"] = d["indust.max_electr"] + " кВт"
        d["com.square"] = f"{area} м²" if area else None
        d["userType"] = {"от хозяина": "owner", "специалист": "specialist", "агентство": "agency"}.get((w.get("owner_type") or "").lower(), w.get("owner_type"))
        if coords.get(wid):
            d["lat"], d["lon"] = coords[wid]["lat"], coords[wid]["lon"]
        else:
            k = kor_lookup(w.get("complex"))
            if k:
                d["lat"], d["lon"], d["geo_src"] = k[0], k[1], "korter"
        seen.add(wid)
        out.append({"id": wid, "deal": deal, "src": "wf",
                    "list": {"title": L.get("title") or w.get("title"), "price": price, "area": area,
                             "district": L.get("district"), "address": L.get("address") or w.get("address")},
                    "detail": d})

with open(OUT, "w", encoding="utf-8") as fh:
    for r in out:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
n_geo = sum(1 for r in out if r["detail"].get("lat"))
print(f"merged {len(out)} rows ({sum(1 for r in out if r['src']=='curl')} curl, {sum(1 for r in out if r['src']=='wf')} wf); with coords {n_geo}")
