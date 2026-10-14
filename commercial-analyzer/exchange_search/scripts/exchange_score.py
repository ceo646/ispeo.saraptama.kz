"""Score Есиль/Нура commercial sale listings for an apartment-exchange purchase.

usage: exchange_score.py <rows.csv> <geocache.json> <raw.jsonl> <out.json> <details.json> [<details2.json> ...]

raw.jsonl: krisha detail pages fetched directly (exact map coords, info fields, full text);
when present they override the WebFetch summaries.

details*.json: lists of detail rows from the krisha workflows; a row carries either
`exchange_for` (exchange-mention set) or `exchange_stance` (district sweep).
rows.csv: the guide dataset (rent/sale listings with coordinates, line, floor…).

Lists produced:
  A — sellers who accept an exchange for an apartment / real estate (or exchange unspecified)
  B — sellers silent about exchange (refusals removed)
Both: Есиль/Нура, ≤140 M ₸, ground floor, not basement/socle, ready or keys ≤6 months.
"""
import csv, json, math, re, sys, time, urllib.parse, urllib.request

ROWS, CACHE, RAW, OUT, DETAILS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:]
raw = {}
for l in open(RAW, encoding="utf-8"):
    try:
        x = json.loads(l)
    except ValueError:
        continue
    if x.get("ok") and x.get("fields"):
        raw[x["id"]] = x
OFFER = re.compile(r"обмен|айырбас|бартер|обменя", re.I)
REFUSE = re.compile(r"(обмен\w*|айырбас\w*|бартер)\s*(не|нет|жоқ|исключ)|без\s+обмен|не\s+(рассматр|предлаг|интерес)\w*\s+обмен|обмен\w*\s+не\s+(рассматр|предлаг|интерес)", re.I)
CAR_ONLY = re.compile(r"обмен\w*\s+(только\s+)?на\s+(авто|машин|автомоб)", re.I)

# ---------- comps from the guide dataset ----------
rent, sale = [], []
guide_xy = {}
for r in csv.DictReader(open(ROWS, encoding="utf-8")):
    if r.get("lat"):
        try:
            guide_xy[r["id"]] = (float(r["lat"]), float(r["lon"]))
        except ValueError:
            pass
    try:
        lat, lon, ppm = float(r["lat"]), float(r["lon"]), float(r["ppm"])
    except (ValueError, KeyError):
        continue
    fl = (r.get("floor") or "").strip()
    if fl not in ("1 этаж", "не указан", ""):   # guide floor bands: '1 этаж', '2 этаж', '3+ этаж', 'цоколь', 'не указан'
        continue
    if re.search(r"подвал|цокол", (r.get("placement") or "") + (r.get("type") or ""), re.I):
        continue
    pt = dict(lat=lat, lon=lon, ppm=ppm, line=(r.get("line") or ""), area=float(r["area"] or 0))
    (rent if r["deal"] == "rent" else sale).append(pt)
KX = 111.2 * math.cos(math.radians(51.15))


def dist(a, b, c, d):
    return math.hypot((a - c) * 111.2, (b - d) * KX)


def tmed(v):
    v = sorted(v)
    k = int(len(v) * 0.15)
    v = v[k:len(v) - k] if len(v) > 6 else v
    return v[len(v) // 2] if v else None


def comps(pts, lat, lon, area, first_line_only):
    for R in (0.7, 1.0, 1.4):
        c = [p for p in pts if dist(lat, lon, p["lat"], p["lon"]) <= R
             and (not first_line_only or "перв" in p["line"].lower())
             and (not area or not p["area"] or 0.4 * area <= p["area"] <= 2.5 * area)]
        if len(c) >= 6:
            return tmed([p["ppm"] for p in c]), len(c), R
    return None, len(c), R


def density(lat, lon):
    return sum(1 for p in rent + sale if dist(lat, lon, p["lat"], p["lon"]) <= 1.0)


# ---------- geocoding (Nominatim, cached, 1 req/s) ----------
try:
    cache = json.load(open(CACHE))
except (OSError, ValueError):
    cache = {}


def nominatim(q):
    if q in cache:
        return cache[q]
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1, "countrycodes": "kz"})
    req = urllib.request.Request(url, headers={"User-Agent": "ispeo-commercial-analyzer/1.0"})
    try:
        js = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception:
        js = []
    time.sleep(1.1)
    res = None
    if js and 50.95 < float(js[0]["lat"]) < 51.30 and 71.20 < float(js[0]["lon"]) < 71.65:
        res = dict(lat=float(js[0]["lat"]), lon=float(js[0]["lon"]), cls=js[0].get("class"), typ=js[0].get("type"))
    cache[q] = res
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
    return res


KZ = [(r"мангилик\s*ел|мангелик\s*ел|мәңгілік\s*ел", "Мәңгілік Ел"), (r"кабанбай\s*батыр\w*", "Қабанбай батыр"),
      (r"\bтуран\b", "Тұран"), (r"сыганак", "Сығанақ"), (r"улы\s*дала", "Ұлы Дала"), (r"достык", "Достық"),
      (r"кунаев\w*", "Қонаев"), (r"акмешит", "Ақмешіт"), (r"алихан\s*бокейхан\w*|бокейхан\w*", "Әлихан Бөкейхан"),
      (r"туркестан", "Түркістан"), (r"(чингиз\s*)?айтматов\w*", "Шыңғыс Айтматов"), (r"коргалжинское\s*шоссе|кургальжинское\s*шоссе|коргалжын\w*", "Қорғалжын тас жолы"),
      (r"(кайыма\s*)?мухамедханов\w*", "Қайым Мұхамедханов"), (r"жошы[\s-]*хан\w*", "Жошы хан"), (r"бухар\s*жырау", "Бұқар жырау"),
      (r"керей\w*.{0,6}жанибек\w*(\s*хан\w*)?", "Керей, Жәнібек хандар"), (r"\b[ЕEе]\s*-?\s*(\d{1,3})\b", r"Е-\1")]


def kz_norm(a):
    for pat, rep in KZ:
        a = re.sub(pat, rep, a, flags=re.I)
    return a


def geocode(addr):
    a = re.sub(r"^[^,]*р-н,\s*", "", addr or "")
    a = re.sub(r"мкр\s+[^,]+,\s*", "", a)
    main, _, landmark = a.partition("—")
    main = main.strip()
    for q in (f"{main}, Астана", f"{kz_norm(main)}, Астана", f"{landmark.strip()}, Астана" if landmark.strip() else None):
        if q:
            g = nominatim(q)
            if g:
                return g, q
    return None, None


# ---------- helpers ----------
ART = re.compile(r"кабанбай|қабанбай|туран|мангилик|мәңгілік|мангелик|сыганак|сығанақ|достык|достық|кунаев|қонаев|орынбор|акмешит|ақмешіт|сауран|керей|жанибек|хусейн|улы дала|ұлы дала|казыбек|қазыбек|толе би|төле би|бухар|бокейхан|бөкейхан|туркестан|түркістан|айтматов|коргалжин|кургальжин|рыскулов|мухамедханов|байтурсын|сарайшык|акжол", re.I)


def ground(fl, base):
    """True = ground floor, None = floor not stated (verify), False = basement/socle/upper floor/attic."""
    f = (fl or "").lower()
    if base or re.search(r"цокол|подвал|-1|минус|чердак|мансард", f):
        return False
    m = re.match(r"\s*(\d+)", f)
    if m:
        return m.group(1) == "1"
    return None


def first_line(r):
    t = ((r.get("line") or "") + " " + (r.get("street_frontage") or "")).lower()
    if re.search(r"втор|двор|аулада|екінші", r.get("line") or "", re.I):
        return False
    return bool(re.search(r"перв|бірінші|1\s*-?\s*я?\s*лини", t))


def ready(r):
    y = r.get("year_built") or 0
    s = (r.get("ready_status") or "").lower()
    if re.search(r"строит|котлован", s) and not re.search(r"ключ|сдач[аи]\s+(в\s+)?(окт|ноя|дек|янв|фев|мар)", s):
        return False
    return not y or y <= 2026 or bool(re.search(r"(1|i)\s*кв\w*\s*2027|январ|феврал|март", s))


rows = []
for f in DETAILS:
    for r in json.load(open(f)):
        if r.get("ok") is False:
            continue
        x = raw.get(r["id"])
        if x:
            fl = x["fields"]
            r = dict(r)
            r["lat_raw"], r["lon_raw"] = x.get("lat"), x.get("lon")
            if fl.get("flat.floor"):
                r["floor"] = fl["flat.floor"]
            ln = fl.get("com.location_line") or ""
            if ln:
                r["line"] = {"бірінші": "первая", "екінші": "вторая", "аулада": "во дворе"}.get(ln.strip(), ln)
            if fl.get("com.entrance_opts"):
                r["entrance"] = fl["com.entrance_opts"]
            if fl.get("house.year", "").isdigit():
                r["year_built"] = int(fl["house.year"])
            if fl.get("map.street"):
                r["address"] = fl["map.street"]
            r["desc_raw"] = x.get("desc", "")
            d = x.get("desc", "")
            if REFUSE.search(d):
                r["exchange_stance_raw"] = "refuses_exchange"
            elif OFFER.search(d):
                r["exchange_stance_raw"] = "car_only" if CAR_ONLY.search(d) and not re.search(r"квартир|недвиж|жиль|пәтер", d, re.I) else "offers_exchange"
            else:
                r["exchange_stance_raw"] = "silent"
        rows.append(r)
seen, out = set(), []
for r in rows:
    if r["id"] in seen:
        continue
    seen.add(r["id"])
    addr = r.get("address") or ""
    dist_ok = re.search(r"есил|нура|нұра", (r.get("district") or "") + addr, re.I)
    price, area = r.get("price") or 0, r.get("area_m2") or 0
    stance = r.get("exchange_stance")
    ex = r.get("exchange_for")
    rs = r.get("exchange_stance_raw")
    if ex is not None:
        lst = "A" if ex in ("apartment", "any_real_estate", "unspecified", "car_or_real_estate") else None
    else:
        lst = "A" if stance == "offers_exchange" else "B" if stance == "silent" else None
    if rs == "refuses_exchange" or (rs == "car_only" and ex not in ("apartment", "any_real_estate")):
        lst = None
    elif rs == "offers_exchange" and lst == "B":
        lst = "A"
    row = dict(r, list=lst, district_ok=bool(dist_ok), ground=ground(r.get("floor"), r.get("basement_or_socle")),
               first_line=first_line(r), ready=ready(r), arterial=bool(ART.search(addr)))
    row["eligible"] = bool(lst and dist_ok and 0 < price <= 140e6 and area >= 30 and row["ground"] is not False and row["ready"])
    if row["eligible"]:
        if r.get("lat_raw"):
            g, q = dict(lat=r["lat_raw"], lon=r["lon_raw"], cls="krisha"), "krisha map"
        elif r["id"] in guide_xy:
            g, q = dict(lat=guide_xy[r["id"]][0], lon=guide_xy[r["id"]][1], cls="krisha(guide)"), "guide coords"
        else:
            g, q = geocode(addr)
        if g:
            row.update(lat=g["lat"], lon=g["lon"], geo_q=q, geo_cls=g["cls"])
            rm, rn, rr = comps(rent, g["lat"], g["lon"], area, True)
            if rm is None:
                rm_all, rn, rr = comps(rent, g["lat"], g["lon"], area, False)
                rm = rm_all * 1.12 if rm_all else None  # first line vs mixed comps (guide: courtyard −12%)
                row["rent_basis"] = f"все 1 эт. ×1.12, n={rn}, r={rr} км"
            else:
                row["rent_basis"] = f"1-я линия, n={rn}, r={rr} км"
            sm, sn, sr = comps(sale, g["lat"], g["lon"], area, False)
            row.update(rent_ppm=round(rm) if rm else None, sale_ppm_comps=round(sm) if sm else None,
                       density_1km=density(g["lat"], g["lon"]))
            if rm:
                net = rm * area * 12 * 0.9 * 0.85 * 0.96 - 0.005 * price - 260_000
                row["yield"] = round(net / price * 100, 1)
            if sm:
                row["price_vs_comps"] = round((price / area / sm - 1) * 100)
    out.append(row)
json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
el = [r for r in out if r["eligible"]]
print(f"rows {len(out)}; eligible {len(el)} (A {sum(r['list']=='A' for r in el)}, B {sum(r['list']=='B' for r in el)}); "
      f"first line {sum(r['first_line'] for r in el)}; geocoded {sum('lat' in r for r in el)}")
