"""Write the candidate file for the verification workflow: top eligible sale listings with full card text and comps."""
import json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from zones import km

A = json.load(open("analysis.json"))
det = {}
for l in open("det_all.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r.get("ok"):
        det[r["id"]] = r
rows = {r["id"]: r for r in json.load(open("rows.json"))}
rent = {r["id"]: r for r in A["rent_points"]}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 24
cand = sorted([s for s in A["sales"] if s["eligible"]], key=lambda s: -s["yield_"])[:N]
zones = {z["zone"]: z for z in A["zones"]}
out = []
for s in cand:
    d = det[s["id"]]
    comps = []
    for cid in s["comp_ids"]:
        r = rent[cid]
        comps.append(dict(id=cid, address=r["address"], area=r["area"], rent_per_m2=r["ppm"], grp=r["grp"],
                          km=round(km((s["lat"], s["lon"]), (r["lat"], r["lon"])), 2), title=r["title"][:80]))
    z = zones[s["zone"]]
    out.append(dict(id=s["id"], url_ru=f"https://krisha.kz/a/show/{s['id']}", url_kz=f"https://krisha.kz/kz/a/show/{s['id']}",
                    zone=s["zone"], group=s["grp"], title_ru=rows[s["id"]]["title"], address=s["address"],
                    lat=s["lat"], lon=s["lon"], area_m2=s["area"], price_tenge=s["price"], price_per_m2=s["ppm"],
                    fields_kz=d.get("fields"), description=d.get("desc"), seller_type=d.get("user_type"),
                    our_estimate=dict(rent_per_m2_month=s["est_rent"], local_comps_median=s["comp_rent"],
                                      model_rent=s["model_rent"], gross_yield=round(s["yield_"], 4), flags=s["flags"]),
                    zone_stats=dict(rent_median=z["rent"], sale_median=z["sale"], n_rent=z["n_rent"], n_sale=z["n_sale"]),
                    comps=comps))
json.dump(out, open("candidates.json", "w"), ensure_ascii=False, indent=1)
print(len(out), "candidates")
for c in out:
    print(c["id"], c["zone"][:20], c["area_m2"], c["price_per_m2"], c["our_estimate"]["gross_yield"], c["address"][:40])
