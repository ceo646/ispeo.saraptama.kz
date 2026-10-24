"""Candidate file for top-location sale listings not yet verified (same format as candidates.json, plus location facts)."""
import json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from zones import km
T = json.load(open("top.json")); L = {o["id"]: o for o in json.load(open("loc.json"))["listings"]}
rows = {r["id"]: r for r in json.load(open("rows.json"))}
det = {}
for l in open("det_all.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r.get("ok"): det[r["id"]] = r
ids = sys.argv[1].split(",")
S = {s["id"]: s for s in T["sales"]}
out = []
for i in ids:
    s = S[i]; d = det[i]; lo = L[i]
    comps = [dict(id=c, address=rows[c]["address"], area=rows[c]["area"], rent_per_m2=rows[c]["ppm"],
                  km=round(km((s["lat"], s["lon"]), (rows[c]["lat"], rows[c]["lon"])), 2), title=rows[c]["title"][:80]) for c in s["comp_ids"]]
    out.append(dict(id=i, url_ru=f"https://krisha.kz/a/show/{i}", url_kz=f"https://krisha.kz/kz/a/show/{i}", zone=s["zone"], group=s["grp"],
                    title_ru=rows[i]["title"], address=s["address"], lat=s["lat"], lon=s["lon"], area_m2=s["area"], price_tenge=s["price"],
                    price_per_m2=s["ppm"], fields_kz=d.get("fields"), description=d.get("desc"), seller_type=d.get("user_type"),
                    location=dict(place=s["kind"], first_line_reason=s["fl_why"], nearest_main_road=s["road"], road_m=s["road_m"],
                                  shops_cafes_offices_400m=lo["poi"], transit_stops_300m=lo["stops"], residents_per_km2=lo["density"],
                                  flats_for_sale_500m=lo["flats"]),
                    our_estimate=dict(rent_per_m2_month=s["est_rent"], local_comps_median=s["comp_rent"], comps_pool=s["comp_pool"],
                                      model_rent=s["model_rent"], gross_yield=round(s["yield_"], 4)),
                    comps=comps))
json.dump(out, open("candidates_top.json", "w"), ensure_ascii=False, indent=1)
print(len(out))
