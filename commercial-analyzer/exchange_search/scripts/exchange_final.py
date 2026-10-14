"""Final ranking of verified Есиль/Нура first-line units for an apartment-exchange purchase.

usage: exchange_final.py <out.json> <judges.json|-> <cand1.json> <verified1.json> [<cand2.json> <verified2.json> ...]

judges.json: standardised classification (include, shopfront_on_street, frontage_class, maturity,
exchange_ok, duplicate_of, note_ru, risk_ru) from two independent judges + tie-breaker; it overrides
the keyword heuristics below.

Location comes first (the investor's priority), then yield on LIVE rent comps, then the verifier's verdict.
"""
import json, re, sys

out_path, judges_path, pairs = sys.argv[1], sys.argv[2], sys.argv[3:]
judges = {}
if judges_path != "-":
    for j in json.load(open(judges_path)):
        judges[str(j["id"])] = j
cand, ver = {}, {}
for i in range(0, len(pairs), 2):
    for c in json.load(open(pairs[i])):
        cand[c["id"]] = c
    for v in json.load(open(pairs[i + 1])):
        ver[v["id"]] = v

MAJOR = re.compile(r"major (avenue|arter|street)|проспект|пр\.|даңғыл|туран|кабанбай|қабанбай|мангилик|мәңгілік|сыганак|сығанақ|кунаев|қонаев|достык|достық|улы дала|ұлы дала|хусейн|керей|бокейхан|бөкейхан|коргалжин|қорғалжын|кургальжин", re.I)
MINOR = re.compile(r"internal|driveway|courtyard|двор|service road|parking|паркинг", re.I)
DISTRICT = re.compile(r"district|local|tertiary|residential street|collector|minor", re.I)


def frontage_score(t):
    t = t or ""
    head = t[:160]
    if MINOR.search(head) and not MAJOR.search(head):
        return 0.5, "внутр. проезд/двор"
    if re.search(r"not (a )?major|не магистрал", t, re.I) or (DISTRICT.search(head) and not re.search(r"major (avenue|arter)", head, re.I)):
        return 0.75, "районная улица"
    if MAJOR.search(head):
        return 1.0, "крупная улица"
    return 0.75, "районная улица"


def maturity_score(t):
    t = (t or "").lower()
    if re.search(r"frontier|окраин|пустыр|undevelop", t):
        return 0.5, "окраина"
    if re.search(r"mature|prime|центр|core|established", t):
        return 1.0, "обжитой"
    if re.search(r"developing|filling|populat|still|new", t):
        return 0.8, "заселяется"
    return 0.8, "заселяется"


rows = []
for i, v in ver.items():
    c = cand.get(i, {})
    lst = c.get("list")
    ok = v.get("active") and v.get("ground_floor_ok") and v.get("first_line_confirmed") and v.get("verdict") != "exclude"
    ex = v.get("exchange_verdict")
    if lst == "A" and ex not in ("accepts_apartment", "accepts_exchange_unspecified"):
        ok = False
    if lst == "B" and ex == "refuses":
        ok = False
    if lst == "B" and ex in ("accepts_apartment", "accepts_exchange_unspecified"):
        lst = "A"  # the card does offer an exchange
    price = v.get("price_now") or c.get("price")
    area = v.get("area_m2") or c.get("area_m2")
    if not (price and area and price <= 140e6):
        ok = False
    rent = v.get("rent_median_ppm")
    y = None
    if rent and price and area:
        y = (rent * area * 12 * 0.9 * 0.85 * 0.96 - 0.005 * price - 260_000) / price
    fs, fl = frontage_score(v.get("frontage_street"))
    ms, ml = maturity_score(v.get("area_maturity"))
    sep = 1.0 if v.get("separate_street_entrance") else 0.8
    jd = judges.get(i)
    note = risk = dup = None
    if jd:
        fs, fl = {"major_avenue": (1.0, "крупная улица"), "district_street": (0.75, "районная улица"),
                  "internal_or_courtyard": (0.45, "внутр. проезд/двор")}[jd["frontage_class"]]
        ms, ml = {"mature": (1.0, "обжитой"), "populating": (0.8, "заселяется"), "frontier": (0.5, "окраина")}[jd["maturity"]]
        sep = 1.0 if jd["shopfront_on_street"] else 0.6
        ok = bool(ok and jd["include"] and jd["exchange_ok"] and jd["shopfront_on_street"]) if jd.get("source") != "unresolved" else False
        note, risk, dup = jd.get("note_ru"), jd.get("risk_ru"), (jd.get("duplicate_of") or None)
    loc = fs * ms * sep
    vs = {"strong": 1.0, "ok": 0.8, "weak": 0.5}.get(v.get("verdict"), 0)
    yn = max(0.0, min(1.0, ((y or 0) - 0.04) / 0.10))  # 4% → 0, 14% → 1
    score = 0.55 * loc + 0.30 * yn + 0.15 * vs
    rows.append(dict(id=i, list=lst, ok=bool(ok), score=round(score, 3), loc=round(loc, 2), frontage=fl, maturity=ml,
                     price=price, area=area, ppm=round(price / area) if price and area else None, rent=rent,
                     yield_=round(y * 100, 1) if y is not None else None, verdict=v.get("verdict"), exchange=ex,
                     exchange_quote=v.get("exchange_quote"), complex=v.get("complex_name"), street=v.get("frontage_street"),
                     maturity_text=v.get("area_maturity"), ceiling=v.get("ceiling_m"), power=v.get("power_kw"),
                     ready=v.get("ready"), red_flags=v.get("red_flags"), reason=v.get("verdict_reason"),
                     address=c.get("address"), lat=v.get("lat"), lon=v.get("lon"), url=f"https://krisha.kz/a/show/{i}",
                     note_ru=note, risk_ru=risk, duplicate_of=dup))
# collapse duplicates: keep the cheaper listing of the same unit
by = {r["id"]: r for r in rows}
for r in rows:
    d = r.get("duplicate_of")
    if d and d in by and by[d]["ok"] and r["ok"]:
        loser = r if (r["price"] or 0) >= (by[d]["price"] or 0) else by[d]
        loser["ok"] = False
        loser["dup_removed"] = True
json.dump(rows, open(out_path, "w"), ensure_ascii=False, indent=1)
for lst in ("A", "B"):
    L = sorted([r for r in rows if r["list"] == lst and r["ok"]], key=lambda r: -r["score"])
    print(f"=== {lst}: {len(L)} pass")
    for n, r in enumerate(L, 1):
        print(f"{n:2d} {r['id']} {r['score']:.3f} loc {r['loc']:.2f} {r['frontage']:18s} {r['maturity']:10s} {r['price']/1e6:6.1f}M {r['area']:6.1f}m² "
              f"{r['ppm']/1000:5.0f}k rent {r['rent']} y {r['yield_']}% {r['verdict']:6s} {r['exchange']} | {(r['address'] or '')[:40]}")
