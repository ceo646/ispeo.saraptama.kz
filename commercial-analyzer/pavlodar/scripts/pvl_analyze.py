"""Pavlodar commercial: zone medians, composition-adjusted gross yields, per-listing yield estimates.

usage: pvl_analyze.py <rows.json> <out analysis.json>
Gross yield = asking rent × 12 / asking price. Rent and price are both asking values, so levels are optimistic;
comparisons between zones are the point.
"""
import json, math, random, sys
from collections import defaultdict
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from zones import zone_of, ORDER, km

ROWS, OUT = sys.argv[1], sys.argv[2]
CITY_SEGS = {"офис", "торговое/стрит-ритейл", "свободное назначение", "сервис (салоны, медицина, обучение)"}
GROUP = {"офис": "офис", "торговое/стрит-ритейл": "торговля и услуги", "сервис (салоны, медицина, обучение)": "торговля и услуги",
         "свободное назначение": "свободное назначение"}

rows = [r for r in json.load(open(ROWS)) if not r["excluded"]]
for r in rows:
    r["zone"] = zone_of(r["lat"], r["lon"], r["address"])[0]
    r["grp"] = GROUP.get(r["seg"], r["seg"])
prem = [r for r in rows if r["seg"] in CITY_SEGS and not r["nonstd"]]
odd = [r for r in rows if r["nonstd"]]
wh = [r for r in rows if r["seg"] == "склад/производство" and not r["nonstd"]]


def med(v):
    return float(np.median(v)) if len(v) else None


def boot_yield(rent, sale, n=4000, seed=1):
    """90% interval of median(rent)*12/median(sale) by resampling listings."""
    if len(rent) < 3 or len(sale) < 3:
        return None, None
    rng = np.random.default_rng(seed)
    a, b = np.array(rent), np.array(sale)
    y = [np.median(rng.choice(a, len(a))) * 12 / np.median(rng.choice(b, len(b))) for _ in range(n)]
    return float(np.percentile(y, 5)), float(np.percentile(y, 95))


# ---------- hedonic models: log(₸/м²) ~ zone + segment + size + floor + line + location + renovation
def frame(rs):
    d = pd.DataFrame([dict(lp=math.log(r["ppm"]), zone=r["zone"], grp=r["grp"], la=math.log(r["area"]),
                           floor="1" if r["floor"] == 1 else ("2+" if (r["floor"] or 0) >= 2 else "н/д"),
                           line=r["line"] or "н/д", loc=r["loc"] or "н/д",
                           reno=r["reno"] if r["reno"] in ("свежий ремонт",) else ("нужен ремонт/черновая" if r["reno"] else "н/д"),
                           owner="хозяин" if r["user_type"] == "owner" else "агент/компания") for r in rs])
    return d


FORM = "lp ~ C(zone, Treatment('Центр')) + C(grp) + la + I(la**2) + C(floor) + C(line) + C(loc) + C(reno) + C(owner)"
models = {}
for deal in ("rent", "sale"):
    d = frame([r for r in prem if r["deal"] == deal])
    m = smf.rlm(FORM, d).fit() if False else smf.ols(FORM, d).fit(cov_type="HC1")
    models[deal] = m
coef = {}
for deal, m in models.items():
    for z in ORDER:
        k = f"C(zone, Treatment('Центр'))[T.{z}]"
        coef.setdefault(z, {})[deal] = (0.0, 0.0) if z == "Центр" else ((float(m.params[k]), float(m.bse[k])) if k in m.params else (None, None))

# reference: Центр medians
cr = [r["ppm"] for r in prem if r["zone"] == "Центр" and r["deal"] == "rent"]
cs = [r["ppm"] for r in prem if r["zone"] == "Центр" and r["deal"] == "sale"]
y_ref = med(cr) * 12 / med(cs)

zones = []
for z in ORDER:
    rr = [r for r in prem if r["zone"] == z and r["deal"] == "rent"]
    ss = [r for r in prem if r["zone"] == z and r["deal"] == "sale"]
    ww = [r for r in wh if r["zone"] == z]
    mr, ms = med([r["ppm"] for r in rr]), med([r["ppm"] for r in ss])
    lo, hi = boot_yield([r["ppm"] for r in rr], [r["ppm"] for r in ss])
    (br, sr), (bs, ss_) = coef[z]["rent"], coef[z]["sale"]
    adj = adj_lo = adj_hi = None
    if br is not None and bs is not None:
        d = br - bs
        se = math.sqrt(sr ** 2 + ss_ ** 2)
        adj, adj_lo, adj_hi = y_ref * math.exp(d), y_ref * math.exp(d - 1.645 * se), y_ref * math.exp(d + 1.645 * se)
    segs = {}
    for g in ("офис", "торговля и услуги", "свободное назначение"):
        a = [r["ppm"] for r in rr if r["grp"] == g]
        b = [r["ppm"] for r in ss if r["grp"] == g]
        segs[g] = dict(n_rent=len(a), n_sale=len(b), rent=med(a), sale=med(b),
                       yield_=(med(a) * 12 / med(b)) if len(a) >= 4 and len(b) >= 4 else None)
    zones.append(dict(zone=z, n_rent=len(rr), n_sale=len(ss), n_wh=len(ww), rent=mr, sale=ms,
                      yield_raw=(mr * 12 / ms) if mr and ms else None, yield_lo=lo, yield_hi=hi,
                      rent_effect=br, sale_effect=bs, yield_adj=adj, yield_adj_lo=adj_lo, yield_adj_hi=adj_hi,
                      first_line=sum(1 for r in rr + ss if r["line"] == "первая линия") / max(1, len(rr + ss)),
                      segs=segs,
                      wh_rent=med([r["ppm"] for r in ww if r["deal"] == "rent"]),
                      wh_sale=med([r["ppm"] for r in ww if r["deal"] == "sale"])))

# ---------- per sale listing: expected rent from nearby comparable rent listings + model prediction
rent_rows_all = [r for r in prem if r["deal"] == "rent"]
# comparables exclude asks above 2.5× the city median (rents with a business, licence or services bundled in)
CAP = 2.5 * float(np.median([r["ppm"] for r in rent_rows_all]))
rent_rows = [r for r in rent_rows_all if r["ppm"] <= CAP]
dr = frame(rent_rows)
m_rent = models["rent"]


def comps(s, k_min=5):
    """Size-matched local comparables: rent listings within a growing radius whose area is within 1/3–3× of the
    object; same group (офис / торговля и услуги / свободное назначение) preferred. Returns weighted median ₸/м²."""
    for rad in (0.5, 0.8, 1.2, 1.8, 2.5):
        c = [r for r in rent_rows if km((s["lat"], s["lon"]), (r["lat"], r["lon"])) <= rad
             and 1 / 3 <= r["area"] / s["area"] <= 3]
        same = [r for r in c if r["grp"] == s["grp"]]
        pool = same if len(same) >= k_min else c
        if len(pool) >= k_min:
            w = [1 / (1 + abs(math.log(r["area"] / s["area"]))) for r in pool]
            order = sorted(zip([r["ppm"] for r in pool], w))
            tot, acc = sum(w), 0
            for v, wi in order:
                acc += wi
                if acc >= tot / 2:
                    return v, rad, len(pool), pool is same, [r["id"] for r in pool]
    return None, None, 0, False, []


resid_sd = float(np.sqrt(m_rent.scale))
sales = []
for s in [r for r in prem if r["deal"] == "sale"]:
    v, rad, n, same, cids = comps(s)
    pred = float(np.exp(m_rent.predict(frame([dict(s, deal="rent")])).iloc[0] + resid_sd ** 2 / 2))
    est = math.sqrt(v * pred) if v else pred          # geometric mean of local comps and the model
    y = est * 12 / s["ppm"]
    flags = []
    if y > 0.2:
        flags.append("проверить: доходность выше 20%")
    if n and n < 8:
        flags.append("мало сравнимых")
    if rad and rad > 1.2:
        flags.append(f"аналоги в радиусе {rad} км")
    if not v:
        flags.append("нет аналогов похожей площади, только модель")
    if s["area"] > 1500:
        flags.append("крупный объект, мало арендаторов такого размера")
    zmed = next(z["sale"] for z in zones if z["zone"] == s["zone"])
    cheap = s["ppm"] < 0.4 * zmed
    if cheap:
        flags.append("цена ниже 40% медианы района")
    if s["auction"]:
        flags.append("залог банка / торги")
    eligible = (15 <= s["area"] <= 1500 and y <= 0.25 and not cheap and n >= 5)
    sales.append(dict(id=s["id"], url=f"https://krisha.kz/a/show/{s['id']}", zone=s["zone"], seg=s["seg"], grp=s["grp"],
                      title=s["title"], address=s["address"], area=s["area"], price=s["price"], ppm=s["ppm"],
                      lat=s["lat"], lon=s["lon"], loc=s["loc"], line=s["line"], floor=s["floor"], reno=s["reno"],
                      comp_rent=v, comp_radius=rad, comp_n=n, model_rent=round(pred), est_rent=round(est),
                      yield_=y, payback=1 / y, flags=flags, eligible=eligible, comp_ids=cids, same_grp=same, owner=s["user_type"], complex=s["complex"],
                      desc=s["desc"][:300]))

for z in zones:
    ys = [s["yield_"] for s in sales if s["zone"] == z["zone"] and s["comp_n"] >= 5 and s["yield_"] <= 0.35]
    z["yield_listing_med"] = med(ys)
    z["n_yield_listing"] = len(ys)
    if len(ys) >= 4:
        rng = np.random.default_rng(3)
        bs = [np.median(rng.choice(ys, len(ys))) for _ in range(4000)]
        z["yield_listing_lo"], z["yield_listing_hi"] = float(np.percentile(bs, 5)), float(np.percentile(bs, 95))
    else:
        z["yield_listing_lo"] = z["yield_listing_hi"] = None

# typical premises: 30–600 m², not auctions, not houses sold as commercial — the robust headline per zone
RID = {r["id"]: r for r in rows}
def typical(s):
    r = RID[s["id"]]
    return (30 <= s["area"] <= 600 and not r["auction"] and s["comp_n"] >= 5 and s["yield_"] <= 0.35
            and "дом" not in (r["desc"] or "")[:40].lower())
for s in sales:
    s["typical"] = typical(s)
for z in zones:
    ys = [s["yield_"] for s in sales if s["zone"] == z["zone"] and s["typical"]]
    z["yield_typ"], z["n_typ"] = med(ys), len(ys)
    z["sale_typ"] = med([s["ppm"] for s in sales if s["zone"] == z["zone"] and s["typical"]])
    if len(ys) >= 4:
        rng = np.random.default_rng(5)
        bs = [np.median(rng.choice(ys, len(ys))) for _ in range(4000)]
        z["yield_typ_lo"], z["yield_typ_hi"] = float(np.percentile(bs, 5)), float(np.percentile(bs, 95))
    else:
        z["yield_typ_lo"] = z["yield_typ_hi"] = None

json.dump(dict(y_ref=y_ref, zones=zones, sales=sales,
               rent_points=[dict(id=r["id"], lat=r["lat"], lon=r["lon"], ppm=r["ppm"], area=r["area"], grp=r["grp"],
                                 zone=r["zone"], address=r["address"], title=r["title"]) for r in rent_rows_all], rent_cap=CAP,
               warehouses=[dict(id=r["id"], deal=r["deal"], lat=r["lat"], lon=r["lon"], ppm=r["ppm"], area=r["area"],
                                zone=r["zone"], address=r["address"]) for r in wh],
               model_rent=dict(r2=models["rent"].rsquared, n=int(models["rent"].nobs)),
               model_sale=dict(r2=models["sale"].rsquared, n=int(models["sale"].nobs)),
               params_rent={k: float(v) for k, v in models["rent"].params.items()},
               params_sale={k: float(v) for k, v in models["sale"].params.items()}),
          open(OUT, "w"), ensure_ascii=False, indent=1)

print(f"ref yield Центр {y_ref:.3f}; rent model R2={models['rent'].rsquared:.2f} n={int(models['rent'].nobs)}; "
      f"sale model R2={models['sale'].rsquared:.2f} n={int(models['sale'].nobs)}")
print(f"{'зона':45s} {'аренда':>12s} {'продажа':>14s} {'дох.сырая':>18s} {'дох.скорр.':>18s}")
for z in zones:
    f = lambda x: f"{x*100:4.1f}" if x else "  — "
    print(f"{z['zone'][:40]:40s} {z['n_rent']:3d} {z['rent'] or 0:7.0f}  {z['n_sale']:3d} {z['sale'] or 0:9.0f}  "
          f"{f(z['yield_raw'])} [{f(z['yield_lo'])}-{f(z['yield_hi'])}]  {f(z['yield_adj'])} [{f(z['yield_adj_lo'])}-{f(z['yield_adj_hi'])}]"
          f"  listing {f(z['yield_listing_med'])} [{f(z['yield_listing_lo'])}-{f(z['yield_listing_hi'])}] n={z['n_yield_listing']}")
print("\nsegment medians, city:")
for g in ("офис", "торговля и услуги", "свободное назначение"):
    a = [r["ppm"] for r in prem if r["grp"] == g and r["deal"] == "rent"]
    b = [r["ppm"] for r in prem if r["grp"] == g and r["deal"] == "sale"]
    print(f"  {g:22s} rent {len(a)} {med(a):.0f}  sale {len(b)} {med(b):.0f}  y {med(a)*12/med(b)*100:.1f}%")
print("\neligible", sum(s["eligible"] for s in sales), "of", len(sales))
print("\ntop sales by yield:")
for s in sorted([s for s in sales if s["eligible"]], key=lambda s: -s["yield_"])[:40]:
    print(f"  {s['yield_']*100:5.1f}% {s['zone'][:22]:22s} {s['grp'][:12]:12s} {s['area']:6.0f} м² {s['price']/1e6:6.1f} млн "
          f"{s['ppm']:7d}/м² comp {s['comp_rent']} r{s['comp_radius']} n{s['comp_n']} model {s['model_rent']} | {s['address'][:35]} {s['flags']}")
