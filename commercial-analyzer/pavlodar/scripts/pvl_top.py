"""Top locations only: first line AND (active district OR dense district).

Premiums of first line / activity / density in rent and price (hedonic OLS on all standard premises), yields of
top-location sale listings against top-location rents, summaries by zone, street corridor and location type,
and the candidate list for verification.
usage: pvl_top.py <rows.json> <loc.json> <out top.json>"""
import json, math, re, sys
from collections import defaultdict
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from zones import zone_of, km

ROWS, LOC, OUT = sys.argv[1:4]
CITY_SEGS = {"офис", "торговое/стрит-ритейл", "свободное назначение", "сервис (салоны, медицина, обучение)"}
GROUP = {"офис": "офис", "торговое/стрит-ритейл": "торговля и услуги", "сервис (салоны, медицина, обучение)": "торговля и услуги",
         "свободное назначение": "свободное назначение"}
L = {o["id"]: o for o in json.load(open(LOC))["listings"]}
rows = []
for r in json.load(open(ROWS)):
    if r["excluded"] or r["nonstd"] or r["seg"] not in CITY_SEGS or r["id"] not in L:
        continue
    r = dict(r, **{k: L[r["id"]][k] for k in ("first_line", "fl_why", "active", "dense", "top", "activity", "dens_idx", "road", "road_m", "density", "flats", "poi", "stops")})
    r["zone"] = zone_of(r["lat"], r["lon"], r["address"])[0]
    r["grp"] = GROUP[r["seg"]]
    r["kind"] = "активный и плотный" if r["active"] and r["dense"] else ("активный" if r["active"] else ("плотный" if r["dense"] else "обычный"))
    rows.append(r)
med = lambda v: float(np.median(v)) if len(v) else None


def frame(rs):
    return pd.DataFrame([dict(lp=math.log(r["ppm"]), zone=r["zone"], grp=r["grp"], la=math.log(r["area"]),
                              fl=int(r["first_line"]), act=int(r["active"]), den=int(r["dense"]),
                              floor="1" if r["floor"] == 1 else ("2+" if (r["floor"] or 0) >= 2 else "н/д"),
                              loc=r["loc"] or "н/д", reno="свежий" if r["reno"] == "свежий ремонт" else ("н/д" if not r["reno"] else "другое"),
                              owner="хозяин" if r["user_type"] == "owner" else "агент") for r in rs])


# location premiums (no zone dummies: the zone is what we are pricing)
F0 = "lp ~ fl + act + den + C(grp) + la + I(la**2) + C(floor) + C(loc) + C(reno) + C(owner)"
prem = {}
for deal in ("rent", "sale"):
    m = smf.ols(F0, frame([r for r in rows if r["deal"] == deal])).fit(cov_type="HC1")
    prem[deal] = {k: dict(pct=float(math.exp(m.params[k]) - 1), lo=float(math.exp(m.params[k] - 1.645 * m.bse[k]) - 1),
                          hi=float(math.exp(m.params[k] + 1.645 * m.bse[k]) - 1), p=float(m.pvalues[k])) for k in ("fl", "act", "den")}
    prem[deal]["n"] = int(m.nobs)

# rent model with zones and location flags for per-listing predictions
F1 = "lp ~ C(zone) + fl + act + den + C(grp) + la + I(la**2) + C(floor) + C(loc) + C(reno) + C(owner)"
rent_rows = [r for r in rows if r["deal"] == "rent"]
mr = smf.ols(F1, frame(rent_rows)).fit()
sd = float(np.sqrt(mr.scale))
CAP = 2.5 * float(np.median([r["ppm"] for r in rent_rows]))      # same outlier rule as pvl_analyze
comp_rows = [r for r in rent_rows if r["ppm"] <= CAP]
top_rent = [r for r in comp_rows if r["top"]]
fl_rent = [r for r in comp_rows if r["first_line"]]


def comps(s, k_min=4):
    # nearby quality comparables first; widen the radius only for broader pools so that a cheaper block does not
    # borrow central rents from 1.5–2 km away
    for pool_name, pool0, radii in (("топ-локации", top_rent, (0.5, 0.8)), ("первая линия", fl_rent, (0.5, 0.8, 1.2)),
                                    ("все", comp_rows, (0.5, 0.8, 1.2, 1.8))):
        for rad in radii:
            c = [r for r in pool0 if km((s["lat"], s["lon"]), (r["lat"], r["lon"])) <= rad and 1 / 3 <= r["area"] / s["area"] <= 3]
            same = [r for r in c if r["grp"] == s["grp"]]
            pool = same if len(same) >= k_min else c
            if len(pool) >= k_min:
                w = [1 / (1 + abs(math.log(r["area"] / s["area"]))) for r in pool]
                acc, tot = 0, sum(w)
                for v, wi in sorted(zip([r["ppm"] for r in pool], w)):
                    acc += wi
                    if acc >= tot / 2:
                        return v, rad, len(pool), pool_name, [r["id"] for r in pool]
    return None, None, 0, None, []


sales = []
for s in [r for r in rows if r["deal"] == "sale"]:
    v, rad, n, pool, ids = comps(s)
    pred = float(np.exp(mr.predict(frame([s])).iloc[0] + sd ** 2 / 2))
    est = math.sqrt(v * pred) if v else pred
    y = est * 12 / s["ppm"]
    typical = 30 <= s["area"] <= 600 and not s["auction"] and n >= 4 and y <= 0.35 and "дом" not in (s["desc"] or "")[:40].lower()
    sales.append(dict(id=s["id"], top=s["top"], first_line=s["first_line"], fl_why=s["fl_why"], active=s["active"], dense=s["dense"],
                      kind=s["kind"], zone=s["zone"], grp=s["grp"], area=s["area"], price=s["price"], ppm=s["ppm"], lat=s["lat"], lon=s["lon"],
                      address=s["address"], road=s["road"], road_m=s["road_m"], est_rent=round(est), comp_rent=v, comp_pool=pool,
                      comp_n=n, comp_radius=rad, model_rent=round(pred), yield_=y, typical=typical, comp_ids=ids,
                      loc=s["loc"], floor=s["floor"], auction=s["auction"], title=s["title"]))


def ystats(v):
    ys = [s["yield_"] for s in v if s["typical"]]
    if len(ys) < 4:
        return dict(n=len(ys), y=med(ys), lo=None, hi=None)
    rng = np.random.default_rng(11)
    bs = [np.median(rng.choice(ys, len(ys))) for _ in range(4000)]
    return dict(n=len(ys), y=med(ys), lo=float(np.percentile(bs, 5)), hi=float(np.percentile(bs, 95)))


def summary(key, sel=lambda r: r["top"]):
    g = defaultdict(lambda: dict(rent=[], sale=[], sales=[]))
    for r in rows:
        if sel(r):
            k = key(r)
            g[k]["rent" if r["deal"] == "rent" else "sale"].append(r["ppm"])
    for s in sales:
        if sel(s):
            g[key(s)]["sales"].append(s)
    out = []
    for k, d in g.items():
        out.append(dict(key=k, n_rent=len(d["rent"]), n_sale=len(d["sale"]), rent=med(d["rent"]), sale=med(d["sale"]), **{"y_" + a: b for a, b in ystats(d["sales"]).items()}))
    return sorted(out, key=lambda x: -(x["n_rent"] + x["n_sale"]))


def street(r):
    n = (r.get("road") or "").lower()
    if (r.get("road_m") or 999) > 70 or not n:
        return "Небольшие улицы (дальше 70 м от магистрали)"
    n = re.sub(r"^(улица|проспект|ул\.|пр\.)\s*|\s*(улица|проспект)$", "", n).strip()
    n = n.replace("академика ", "").replace("генерала ", "").replace("нурсултана ", "")
    NICE = {"назарбаева": "пр. Назарбаева", "машхура жусупа": "Машхур Жусупа", "исы байзакова": "Исы Байзакова",
            "бухар жырау": "Бухар жырау", "кабдеша нуркина": "Нуркина", "максима горького": "Горького"}
    return NICE.get(n, n[:1].upper() + n[1:])


res = dict(
    premiums=prem,
    overall=summary(lambda r: "топ-локации" if r["top"] else ("первая линия, тихое место" if r["first_line"] else "не первая линия"), sel=lambda r: True),
    by_kind=summary(lambda r: r["kind"]),
    by_zone=summary(lambda r: r["zone"]),
    by_street=summary(street),
    sales=sales,
    n_top=dict(rent=sum(1 for r in rows if r["top"] and r["deal"] == "rent"), sale=sum(1 for r in rows if r["top"] and r["deal"] == "sale")),
)
json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=1)

f = lambda x: f"{x*100:5.1f}%" if x is not None else "   — "
print("premiums (rent):", {k: (round(v["pct"] * 100), round(v["p"], 3)) for k, v in prem["rent"].items() if k != "n"}, "n", prem["rent"]["n"])
print("premiums (sale):", {k: (round(v["pct"] * 100), round(v["p"], 3)) for k, v in prem["sale"].items() if k != "n"}, "n", prem["sale"]["n"])
for name in ("overall", "by_kind", "by_zone", "by_street"):
    print("==", name)
    for x in res[name]:
        print(f"  {x['key'][:40]:40s} rent {x['n_rent']:3d} {x['rent'] or 0:6.0f}  sale {x['n_sale']:3d} {x['sale'] or 0:8.0f}  y {f(x['y_y'])} [{f(x['y_lo'])}–{f(x['y_hi'])}] n={x['y_n']}")
print("== top-location sales by yield")
for s in sorted([s for s in sales if s["top"] and s["typical"]], key=lambda s: -s["yield_"])[:25]:
    print(f"  {s['yield_']*100:5.1f}% {s['zone'][:16]:16s} {s['kind'][:8]:8s} {s['area']:6.0f} м² {s['ppm']:7d} est {s['est_rent']} ({s['comp_pool']}, n{s['comp_n']}) | {s['address'][:35]} | {s['fl_why']}")
