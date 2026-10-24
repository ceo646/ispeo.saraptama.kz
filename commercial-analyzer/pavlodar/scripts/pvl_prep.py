"""Merge krisha list cards + detail pages for Pavlodar commercial, clean and classify.

usage: pvl_prep.py <list_all.json> <out rows.json> <details.jsonl ...>
Each row: id, deal, seg, area, price, ppm (₸/m², per month for rent), lat, lon, attributes, flags.
"""
import json, re, sys
from collections import Counter

LIST, OUT, DETS = sys.argv[1], sys.argv[2], sys.argv[3:]

# Pavlodar city proper (villages and dachas outside are kept but flagged)
CITY = (52.205, 76.88, 52.34, 77.07)

LOC = {"бөлек тұрған ғимарат": "отдельное здание", "бизнес орталықта": "бизнес-центр",
       "тұрғын үйде немесе ТК-де": "жилой дом/ЖК", "сауда орталығында": "торговый центр"}
LINE = {"бірінші": "первая линия", "аулада": "во дворе", "жеке секторда": "частный сектор", "екінші": "вторая линия"}
RENO = {"жаңадан жөндеу жүргізген": "свежий ремонт", "косметикалық жөндеу қажет": "нужен косметический",
        "қара сылақпен беріледі": "черновая", "күрделі жөндеу қажет": "нужен капитальный",
        "еркін жоспарлау": "свободная планировка"}

INDUSTRIAL = {"склады", "азс", "автосервисы и автомойки", "сельское хозяйство", "производство", "промбазы"}
RETAIL = {"магазины и бутики", "общепит"}
SERVICE = {"салоны красоты", "медцентры и аптеки", "образование", "фитнес и спорт", "развлечения", "студии"}
OFFICE = {"офисы", "кабинеты и рабочие места", "конференц-залы"}
HOSPITALITY = {"бани", "гостиницы и зоны отдыха"}
BASEMENT = re.compile(r"цокол|подвал|полуподвал|жертөле|цоколь", re.I)
# objects that are not a normal premise: market stalls, movable pavilions, rights of lease, land with houses,
# unfinished shells, dormitories, garage boxes. Their ₸/м² is not comparable with real premises.
NONSTD = [
    ("место на рынке", re.compile(r"рынк[еау]\b.*(?:место|павильон|ряд)|(?:место|павильон|ряд)\b.*рынк[еау]|ярмарк|\bряд\b", re.I)),
    ("павильон/контейнер/киоск", re.compile(r"павиль[оё]н|повильон|контейнер|киоск|\bбудк", re.I)),
    ("право аренды/торговое место", re.compile(r"право аренды|торгов\w* мест|сдаются места|сдается место|рабоч\w* мест\w* в аренду|аренда (?:кресла|кушетки|места)", re.I)),
    ("участок под снос/застройку", re.compile(r"под строительство (?:жил|ЖК|многоэт)|участок, на участке \d+ жил", re.I)),
    ("недострой", re.compile(r"недостро", re.I)),
    ("общежитие целиком", re.compile(r"(?:здание|продам действующее|действующий бизнес аренда жилья)[^.]{0,40}общежити|общежитие сделали|заселени", re.I)),
    ("гаражный бокс", re.compile(r"гаражн\w* кооператив|бокс\w* в гараж", re.I)),
]


def segment(uses, loc, area, ceiling, text):
    u = set(uses)
    if re.search(r"\bцех\w*|производствен\w* (?:помещ|база|комплекс)|промбаз", text, re.I) and loc != "бизнес-центр":
        return "склад/производство"
    if u and u <= INDUSTRIAL | {"свободное назначение"} and u & INDUSTRIAL:
        return "склад/производство"
    if u and u <= HOSPITALITY | {"свободное назначение"} and u & HOSPITALITY:
        return "гостиница/баня"
    if loc == "бизнес-центр" or (u & OFFICE and not u & (RETAIL | INDUSTRIAL) and len(u - OFFICE - {"свободное назначение"}) <= 1):
        return "офис"
    if loc == "торговый центр" or u & RETAIL:
        if len(u & INDUSTRIAL) >= 2 and (area or 0) > 600:
            return "склад/производство"
        return "торговое/стрит-ритейл"
    if u & OFFICE and not u & INDUSTRIAL:
        return "офис"
    if u & INDUSTRIAL and ((ceiling or 0) >= 4.5 or (area or 0) > 800):
        return "склад/производство"
    if u & SERVICE:
        return "сервис (салоны, медицина, обучение)"
    return "свободное назначение"


def fnum(s):
    m = re.search(r"[\d]+(?:[.,]\d+)?", (s or "").replace(" ", ""))
    return float(m.group(0).replace(",", ".")) if m else None


cards = {r["id"]: r for r in json.load(open(LIST))}
det = {}
for fn in DETS:
    for l in open(fn, encoding="utf-8"):
        r = json.loads(l)
        if r.get("ok"):
            det[r["id"]] = r

rows, why = [], Counter()
for i, c in cards.items():
    d = det.get(i, {})
    f = d.get("fields") or {}
    uses = [u.strip().lower() for u in c["uses"].split(",") if u.strip()]
    area = c["area"] or fnum(f.get("com.square"))
    price = c["price"]
    loc = LOC.get(f.get("com.location"), f.get("com.location"))
    ceiling = fnum(f.get("ceiling"))
    text = " ".join([c.get("preview") or "", d.get("desc") or "", c.get("title") or ""])
    floor_raw = f.get("flat.floor")
    floor = fnum(floor_raw)
    m = re.search(r"(-?\d+)\s*этаж", c.get("preview") or "")
    basement = bool(BASEMENT.search(text)) or (floor is not None and floor <= 0) or "-" in (floor_raw or "")
    lat, lon = d.get("lat"), d.get("lon")
    in_city = bool(lat and CITY[0] <= lat <= CITY[2] and CITY[1] <= lon <= CITY[3])
    bc = f.get("office.complex_name") or ""
    mm = re.match(r"в (бизнес-центре|торговом центре|жилом доме или ЖК)\s+([^,]+)", c.get("preview") or "")
    if mm and not bc:
        bc = mm.group(2).strip()
    nonstd = "место на рынке" if loc == "әмбебап базарда" else next((k for k, rx in NONSTD if rx.search(text)), None)
    seg = segment(uses, loc, area, ceiling, text)
    if nonstd is None and re.search(r"аукцион|торги|залогов", text, re.I):
        nonstd = None; auction = True
    else:
        auction = False
    if not nonstd and loc == "торговый центр" and (area or 0) < 60 and seg != "офис":
        nonstd = "бутик в торговом доме"
    row = dict(id=i, deal=c["deal"], uses=uses, seg=seg, nonstd=nonstd, auction=auction, area=area, price=price,
               ppm=round(price / area) if price and area else None, lat=lat, lon=lon, in_city=in_city,
               address=c.get("address"), loc=loc, complex=bc, line=LINE.get(f.get("com.location_line"), f.get("com.location_line")),
               reno=RENO.get(f.get("com.renovation"), f.get("com.renovation")), floor=floor, ceiling=ceiling,
               year=fnum(f.get("house.year")), entrance=f.get("com.entrance_opts"), owner=c.get("owner"),
               user_type=d.get("user_type"), basement=basement, has_detail=bool(d), date=c.get("date"),
               title=c.get("title"), desc=(d.get("desc") or c.get("preview") or "")[:400])
    rows.append(row)

# duplicates: same deal + price + area + rounded coords (re-posts by several agents)
seen = {}
for r in sorted(rows, key=lambda r: (r["user_type"] != "owner", r["id"])):
    k = (r["deal"], r["price"], round(r["area"] or 0), round(r["lat"] or 0, 3), round(r["lon"] or 0, 3))
    r["dup_of"] = seen.get(k)
    seen.setdefault(k, r["id"])

for r in rows:
    p = r["ppm"]
    bad = None
    if not r["has_detail"]:
        bad = "нет карточки"
    elif not r["lat"]:
        bad = "нет координат"
    elif not r["in_city"]:
        bad = "за пределами города"
    elif r["dup_of"]:
        bad = "дубль"
    elif r["basement"]:
        bad = "цоколь/подвал"
    elif not r["area"] or r["area"] < 8:
        bad = "меньше 8 м² (кресло, полка, место)"
    elif r["deal"] == "rent" and not (300 <= p <= 20000):
        bad = "ставка вне 300–20 000 ₸/м²"
    elif r["deal"] == "rent" and p < 800 and r["seg"] != "склад/производство":
        bad = "ставка ниже 800 ₸/м² для помещения (цена за кабинет или место)"
    elif r["deal"] == "sale" and not (30000 <= p <= 1500000):
        bad = "цена вне 30 тыс.–1,5 млн ₸/м²"
    r["excluded"] = bad
    why[(r["deal"], bad)] += 1

json.dump(rows, open(OUT, "w"), ensure_ascii=False)
print(sorted(why.items(), key=lambda x: str(x)))
print(Counter((r["deal"], r["seg"]) for r in rows if not r["excluded"]))
