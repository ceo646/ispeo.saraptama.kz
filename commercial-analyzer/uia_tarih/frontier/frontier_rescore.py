"""Re-score ÜIA offices for the 'frontier island' reality (v2, after adversarial review).

usage: frontier_rescore.py <scored.json> <orient.json> <out.json>

<scored.json>: old per-office scores (key, area, price, ppm, rent, y, handover, loc).
<orient.json>: {key: [factor, reason]}; factor = how the frontage sits relative to the only
real flows (residents walking/driving north to пр. Улы Дала; nothing south or west).

Mature asking rent M = old rent x DEFLATOR x factor, where DEFLATOR moves the old anchor
(ÜIA pre-delivery asks, ~9,200 for the best TARIH frontage) to the delivered-analog level:
base 7,000 (median of delivered analogs ~7,150), upside 8,000, downside 6,000.
"""
import json, sys

src, orient_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
offices = json.load(open(src))
ORIENT = json.load(open(orient_path))

OLD_ANCHOR = 9200
ANCHORS = {"low": 6000, "base": 7000, "high": 8000}
EDGE = 0.88            # factor at or below this = faces empty land
VAC = {False: 0.85, True: 0.80}  # mature vacancy/ОСИ factor: normal / edge-facing
TAX = 0.04             # simplified regime (3% for Astana from 2026 is unverified)
SOC = 260_000          # ИП social payments per year while renting
EMPTY_COST = 150       # ₸/m²/month ОСИ + heating paid by the owner while empty
CAP = 0.10             # exit cap rate for implied value
BUDGET = (65e6, 110e6)

# Months from Oct 2026 to keys. Sources show dates already slipping ~3 quarters,
# so base = announced quarter + 2 quarters, slow = + 4 quarters.
KEYS = {"base": {"4 кв. 2026": 8, "1 кв. 2027": 11, "2 кв. 2027": 14, "3 кв. 2027": 17},
        "slow": {"4 кв. 2026": 14, "1 кв. 2027": 17, "2 кв. 2027": 20, "3 кв. 2027": 23}}
# Ramp after keys: months to the first paying tenant (fit-out + search; +3 for edge units),
# then contract rent as a share of the mature contract rent in lease years 1-3.
RAMP = {"base": dict(lag=9, pct=[0.70, 0.88, 0.95]),
        "slow": dict(lag=15, pct=[0.55, 0.78, 0.90])}


def noi_stab(M, area, price, edge):
    """Stabilised annual net income (old formula, edge-aware vacancy)."""
    return M * area * 12 * 0.9 * VAC[edge] * (1 - TAX) - 0.005 * price - SOC


def five_year(o, M, edge, scen):
    """Average annual net cash yield over 60 months from purchase (income only)."""
    area, price = o["area"], o["price"]
    mk = KEYS[scen][o["handover"]]
    r = RAMP[scen]
    lag = r["lag"] + (3 if edge else 0)
    cash = 0.0
    for m in range(60):
        after = m - mk
        if after < 0:
            continue  # under construction: no income, no property tax yet
        cash -= 0.005 * price / 12
        leased = after - lag
        if leased < 0:
            cash -= EMPTY_COST * area
            continue
        yr = leased // 12
        pct = r["pct"][yr] if yr < len(r["pct"]) else 1.0
        cash += M * 0.9 * pct * VAC[edge] * area * (1 - TAX)
        cash -= SOC / 12
    return cash / price / 5


res = []
for o in offices:
    f, why = ORIENT[o["key"]]
    edge = f <= EDGE
    row = dict(key=o["key"], area=o["area"], price_m=round(o["price"] / 1e6, 2), ppm=int(o["ppm"]),
               handover=o["handover"], old_rent=o["rent"], old_y=round(o["y"] * 100, 1),
               factor=f, edge=edge, why=why, loc=o.get("loc"), h=o.get("h"),
               in_budget=BUDGET[0] <= o["price"] <= BUDGET[1])
    for name, A in ANCHORS.items():
        M = o["rent"] * A / OLD_ANCHOR * f
        row[f"M_{name}"] = round(M)
        row[f"stab_{name}"] = round(noi_stab(M, o["area"], o["price"], edge) / o["price"] * 100, 1)
    Mb = o["rent"] * ANCHORS["base"] / OLD_ANCHOR * f
    row["y5_base"] = round(five_year(o, Mb, edge, "base") * 100, 1)
    row["y5_slow"] = round(five_year(o, o["rent"] * ANCHORS["low"] / OLD_ANCHOR * f, edge, "slow") * 100, 1)
    noi = noi_stab(Mb, o["area"], o["price"], edge)
    row["value_ppm_cap10"] = int(noi / CAP / o["area"])
    row["equity_gap_pct"] = round((noi / CAP - o["price"]) / o["price"] * 100)
    row["price_for_9pct_m"] = round((Mb * o["area"] * 12 * 0.9 * VAC[edge] * (1 - TAX) - SOC) / (0.09 + 0.005) / 1e6, 1)
    res.append(row)
res.sort(key=lambda r: -r["stab_base"])
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
hdr = f"{'key':5} {'bud':3} {'m2':>6} {'M₸':>6} {'₸/m2':>7} {'f':>4} {'M':>5} {'st6k':>5} {'st7k':>5} {'st8k':>5} {'5yB':>5} {'5yS':>5} {'v@10%':>7} {'gap%':>5} {'P9%':>6}"
print(hdr)
for r in res:
    print(f"{r['key']:5} {'да' if r['in_budget'] else '—':3} {r['area']:6.1f} {r['price_m']:6.1f} {r['ppm']:7d} {r['factor']:4.2f} {r['M_base']:5d} "
          f"{r['stab_low']:5.1f} {r['stab_base']:5.1f} {r['stab_high']:5.1f} {r['y5_base']:5.1f} {r['y5_slow']:5.1f} {r['value_ppm_cap10']:7d} {r['equity_gap_pct']:5d} {r['price_for_9pct_m']:6.1f}")
