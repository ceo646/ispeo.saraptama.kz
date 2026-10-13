"""Rent/sale benchmark per BI Group bigville from krisha rows (data/<slug>.json).

Usage: python bvcalc.py data   -> prints the table, writes data/summary.json
"""
import glob, json, os, statistics, sys

BV = sys.argv[1]
ASK_DISCOUNT = 0.90   # реальная ставка сделки ≈ 90% от запрашиваемой
NET_FACTOR = 0.85     # простой ~1 мес/год + налог/обслуживание
YIELDS = (0.12, 0.10, 0.08)


def q(vals, p):
    vals = sorted(vals)
    if not vals:
        return None
    k = (len(vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def tmed(vals):
    vals = sorted(vals)
    if len(vals) >= 10:
        k = len(vals) // 10
        vals = vals[k:len(vals) - k]
    return statistics.median(vals) if vals else None


def clean(rows, deal):
    out, seen = [], set()
    for r in rows:
        if r.get("deal") != deal or r.get("basement") or r.get("flag"):
            continue
        area, price = r.get("area"), r.get("price")
        if not area or not price or area < 15 or area > 1000:
            continue
        ppm = price / area
        ok = (2000 <= ppm <= 40000) if deal == "rent" else (150_000 <= ppm <= 3_000_000)
        if not ok:
            continue
        key = (round(area), round(price, -3), (r.get("address") or "")[:25])
        if key in seen or r.get("id") in seen:
            continue
        seen.add(key); seen.add(r.get("id"))
        out.append(dict(r, ppm=ppm))
    return out


import re
BRAND = {"greenline": "green", "uia": "uia|ūia|üia|уиа", "capitalpark": "capital", "family": "family",
         "jetisu": "jetisu|жетысу", "auez": "auez|äuez|ауэз", "alem": "alem", "arna": "arna",
         "lavita": "lavita|лавита", "impulse": "impulse|импульс"}
res = {}
for f in sorted(glob.glob(os.path.join(BV, "*.json"))):
    if f.endswith("summary.json"):
        continue
    d = json.load(open(f))
    if not isinstance(d, dict) or "rows" not in d:
        continue
    slug = os.path.basename(f)[:-5]
    rent_all = clean(d["rows"], "rent")
    sale_all = clean(d["rows"], "sale")
    inside = [r for r in rent_all if r.get("scope", "inside") == "inside"]
    rent = inside if len(inside) >= 8 else rent_all
    small = [r["ppm"] for r in rent if r["area"] <= 200]
    rv = [r["ppm"] for r in rent]
    sv = [r["ppm"] for r in sale_all if r.get("scope", "inside") == "inside"] or [r["ppm"] for r in sale_all]
    own_re = re.compile(BRAND.get(slug, "^$"), re.I)
    own = lambda r: bool(own_re.search((r.get("complex") or "") + " " + (r.get("address") or "") + " " + (r.get("title") or "")))
    rown = [r["ppm"] for r in rent_all if own(r)]
    sown = [r["ppm"] for r in sale_all if own(r)]
    rm = tmed(rv)
    sm = tmed(sv)
    out = dict(
        bigville=d.get("bigville", slug), n_rent=len(rent), n_rent_inside=len(inside),
        n_rent_nearby=len(rent_all) - len(inside), n_sale=len(sv),
        rent_med=rm, rent_p25=q(rv, .25), rent_p75=q(rv, .75),
        rent_small_med=tmed(small) if small else None,
        sale_med=sm, sale_p25=q(sv, .25), sale_p75=q(sv, .75),
        resale_gross_yield=(rm * 12 / sm) if rm and sm else None,
        n_rent_own=len(rown), rent_own_med=tmed(rown) if rown else None,
        n_sale_own=len(sown), sale_own_med=tmed(sown) if sown else None,
        raw=d.get("totals"), notes=d.get("notes", ""), location=d.get("location"),
    )
    if rm:
        net = rm * ASK_DISCOUNT * NET_FACTOR * 12
        out["net_rent_year"] = net
        out["max_price"] = {f"{int(y*100)}%": net / y for y in YIELDS}
    res[slug] = out

json.dump(res, open(os.path.join(BV, "summary.json"), "w"), ensure_ascii=False, indent=1)
fmt = lambda v: "-" if v is None else f"{v:,.0f}".replace(",", " ")
print(f"{'bigville':12} {'nR':>4} {'in':>3} {'rent_med':>9} {'p25':>7} {'p75':>7} {'<=200':>7} {'nS':>3} {'sale_med':>10} {'yld':>5} {'max@12':>10} {'max@10':>10} {'max@8':>10}")
for s, o in sorted(res.items(), key=lambda kv: -(kv[1]["rent_med"] or 0)):
    m = o.get("max_price", {})
    y = o["resale_gross_yield"]
    print(f"{s:12} {o['n_rent']:>4} {o['n_rent_inside']:>3} {fmt(o['rent_med']):>9} {fmt(o['rent_p25']):>7} {fmt(o['rent_p75']):>7} {fmt(o['rent_small_med']):>7} {o['n_sale']:>3} {fmt(o['sale_med']):>10} {('-' if y is None else f'{y*100:.1f}%'):>5} {fmt(m.get('12%')):>10} {fmt(m.get('10%')):>10} {fmt(m.get('8%')):>10}")

print()
for s, o in sorted(res.items(), key=lambda kv: -(kv[1]["rent_med"] or 0)):
    print(f"{s:12} own: rent n={o['n_rent_own']:>3} med={fmt(o['rent_own_med']):>7} | sale n={o['n_sale_own']:>3} med={fmt(o['sale_own_med']):>10}")
