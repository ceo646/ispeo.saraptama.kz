"""Rank Pavlodar zones for buying commercial premises to rent out.

Components (each scaled 0–1 across zones):
  Y  gross yield of typical premises (30–600 m²), zone median shrunk toward the city median by sample size
     (k = 10 listings); for Айгуль the external check of more listings (≈9%) replaces our 6-listing median;
  R  asking rent level ₸/м² (tenant demand / pricing power), shrunk the same way;
  D  market depth = log(rent + sale listings) — how easy it is to find tenants and to sell later;
  S  internet sentiment: mean of the research verdicts for the zone (−2…+2), see SENT below.
Weights 0.40 / 0.20 / 0.15 / 0.25; robustness: 20 000 random weight vectors (Dirichlet) — share of runs where
each zone is first and in the top 3.
usage: pvl_rank.py <analysis.json> <out rank.json>"""
import json, math, sys
import numpy as np

A = json.load(open(sys.argv[1]))
# research verdicts mapped to our zones (each number is one researcher's −2…+2 verdict on that area)
SENT = {
    "Центр": [2, 2, 2, 2, 2, 2, 2, 2, 1, -1, -1],          # BC belt +, old trade houses on Назарбаева/ЦУМ −
    "Юг центра: Горького–Ломова": [1, 1, 0, 0],            # Ломова–Камзина belt, Затонский рынок → new TD, Сатпаева-юг
    "Квазар и Центральный рынок": [1, 0],
    "пр. Назарбаева: Артур и Ярмарка": [2, -1],
    "Вокзал, Телецентр, Северный": [1, 0],
    "Сарыарка и Batyr Mall": [1, 2, 1, 0, 0, -1],
    "Затон": [0, 0, -1, 0],
    "Усольский": [2, 1, 0, 0, 1, 1, 1],
    "пр. Назарбаева южнее Ломова (Айгуль)": [1, -1],      # targeted research and skeptic pass
    "Горторг, Дачный, Достык": [0, 1, 1, 1, 1, 1, 0],
    "Восток, Второй Павлодар, Зеленстрой": [-1, -2, -1, 0, 0, -1, -1],
    "Химгородки и Лесозавод": [0, -1, -1, -1, 0],
}
zones = [z for z in A["zones"] if z["zone"] in SENT]
sales = A["sales"]
city_y = float(np.median([s["yield_"] for s in sales if s["typical"]]))
# zones where an independent web check of more listings contradicted our small sample: use its estimate
EXTERNAL = {"пр. Назарбаева южнее Ломова (Айгуль)": 0.09}   # research 9–11%, skeptic 8–10% on the avenue frontage
city_r = float(np.median([r["ppm"] for r in A["rent_points"]]))
K = 10


def shrink(v, n, c):
    return (n * v + K * c) / (n + K) if v is not None else c


rows = []
for z in zones:
    y = EXTERNAL.get(z["zone"]) or shrink(z["yield_typ"], z["n_typ"], city_y)
    r = shrink(z["rent"], z["n_rent"], city_r)
    d = math.log(1 + z["n_rent"] + z["n_sale"])
    s = float(np.mean(SENT[z["zone"]])) if SENT[z["zone"]] else 0.0
    rows.append(dict(zone=z["zone"], Y=y, R=r, D=d, S=s, n_s=len(SENT[z["zone"]])))
M = np.array([[x["Y"], x["R"], x["D"], x["S"]] for x in rows])
N = (M - M.min(0)) / (M.max(0) - M.min(0))
W = np.array([0.40, 0.20, 0.15, 0.25])
score = N @ W
rng = np.random.default_rng(7)
Ws = rng.dirichlet([4, 2, 1.5, 2.5], 20000)
S = N @ Ws.T
first = (S == S.max(0)).mean(1)
top3 = (np.argsort(-S, 0)[:3, :][None, :, :] == np.arange(len(rows))[:, None, None]).any(1).mean(1)
for i, x in enumerate(rows):
    x.update(score=float(score[i]), p_first=float(first[i]), p_top3=float(top3[i]),
             nY=float(N[i, 0]), nR=float(N[i, 1]), nD=float(N[i, 2]), nS=float(N[i, 3]))
rows.sort(key=lambda x: -x["score"])
json.dump(dict(city_yield=city_y, city_rent=city_r, weights=W.tolist(), rows=rows), open(sys.argv[2], "w"),
          ensure_ascii=False, indent=1)
print(f"city yield {city_y:.3f} city rent {city_r:.0f}")
for x in rows:
    print(f"{x['score']:.3f} first {x['p_first']*100:4.0f}% top3 {x['p_top3']*100:4.0f}% | Y {x['Y']*100:4.1f} R {x['R']:5.0f} "
          f"D {x['D']:.2f} S {x['S']:+.2f} | {x['zone']}")
