"""Factor analysis of Astana commercial listings (krisha.kz) for the office guide.

Usage: python3 -E guide_analyze.py <data dir> <out dir>
Reads details.jsonl (+ coords_*.json), writes analysis.md and analysis.json.
"""
import json, math, os, re, sys
from collections import Counter
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

LANDMARKS = {  # approximate, lat/lon
    "Байтерек": (51.1282, 71.4304),
    "Хан Шатыр": (51.1327, 71.4036),
    "Mega Silk Way": (51.0898, 71.4178),
    "EXPO/МФЦА": (51.0894, 71.4168),
    "Старый центр (Республики/Сейфуллина)": (51.1660, 71.4330),
    "Вокзал Нурлы Жол": (51.1951, 71.4857),
    "Аэропорт": (51.0225, 71.4669),
}
KEYWORDS = {
    "угловое": r"углов",
    "витраж": r"витраж|панорамн",
    "трафик/проходимость": r"трафик|проходим|поток",
    "остановка": r"остановк",
    "перекрёсток": r"перекр[её]ст",
    "аллея/бульвар": r"аллея|аллее|бульвар",
    "двор (внутри)": r"во двор|внутри двора|внутри квартала|со двора|дворов",
    "школа/садик рядом": r"школ|детск\w* сад|садик",
    "первая линия (текст)": r"перв\w+ лини|1[- ]?я лини|красн\w+ лини",
    "вторая линия (текст)": r"втор\w+ лини|2[- ]?я лини",
    "отдельный вход (текст)": r"отдельн\w+ вход",
    "два входа": r"два вход|2 вход|двумя вход",
    "парковка (текст)": r"парков",
    "ТРЦ/ТЦ рядом": r"трц|тц |торгов\w+ центр",
    "госорганы/БЦ рядом": r"госорган|министерств|акимат|бизнес[- ]центр|бц ",
    "под общепит": r"общепит|кафе|рестор|кофейн",
    "под аптеку/мед": r"аптек|медиц|стоматол|клиник",
    "арендатор есть": r"с арендатор|действующ\w+ арендатор|сдан[оа]? в аренду|арендатор на месте",
    "срочно": r"срочн",
    "торг": r"торг",
}


def hav(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def num(s):
    if not s:
        return None
    m = re.search(r"(\d+[.,]?\d*)", str(s).replace(" ", ""))
    return float(m.group(1).replace(",", ".")) if m else None


def floor_cat(s, text):
    t = (s or "").lower()
    full = (text or "").lower()
    if any(k in t for k in ("подвал", "полуподвал")) or "подвал" in full[:0]:
        return "подвал/полуподвал"
    if "цокол" in t:
        return "цоколь"
    m = re.match(r"\s*(-?\d+)", t)
    if m:
        f = int(m.group(1))
        if f <= 0:
            return "подвал/полуподвал"
        if f == 1:
            return "1 этаж"
        if f == 2:
            return "2 этаж"
        return "3+ этаж"
    return "не указан"


def entrance_cat(v):
    v = (v or "").lower()
    if not v or v == "не указан":
        return "не указан"
    yard, street, common, sep = "со двора" in v, "с улицы" in v, "общий" in v, "отдельный" in v
    if yard and not street:
        return "со двора"
    if common and not sep and not street:
        return "общий (через подъезд)"
    if (sep or street) and not yard and not common:
        return "отдельный с улицы"
    return "смешанный"


def area_band(a):
    if a is None or a != a:
        return None
    for lo, hi, name in ((0, 30, "<30"), (30, 60, "30–60"), (60, 100, "60–100"), (100, 150, "100–150"),
                         (150, 250, "150–250"), (250, 500, "250–500"), (500, 1e9, "500+")):
        if lo <= a < hi:
            return name


def band(v, edges, labels):
    if v is None or v != v:
        return None
    for e, l in zip(edges, labels):
        if v < e:
            return l
    return labels[-1]


coords = {}
for deal in ("rent", "sale"):
    p = f"{DATA}/coords_{deal}.json"
    if os.path.exists(p):
        coords.update(json.load(open(p)))

rows = []
for line in open(f"{DATA}/details.jsonl", encoding="utf-8"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    d = r.get("detail") or {}
    L = r.get("list") or {}
    price = L.get("price")
    area = num(d.get("com.square")) or L.get("area")
    if not price or not area or area <= 0:
        continue
    ppm = price / area
    deal = r["deal"]
    if deal == "rent" and not (1500 <= ppm <= 60000):
        continue
    if deal == "sale" and not (100_000 <= ppm <= 4_000_000):
        continue
    if area < 10 or area > 2000:
        continue
    title = d.get("title") or L.get("title") or ""
    ttype = title.split("·")[0].strip()
    first_type = ttype.split(",")[0].strip().lower()
    desc = (d.get("description") or "")
    text = (title + " " + desc).lower()
    addr = d.get("map.street") or L.get("address") or ""
    dm = re.search(r"([А-Яа-яЁё\-]+)\s+р-н", addr)
    district = dm.group(1) if dm else (L.get("district") or "")
    lat, lon = d.get("lat"), d.get("lon")
    if (not lat) and coords.get(r["id"]):
        lat, lon = coords[r["id"]]["lat"], coords[r["id"]]["lon"]
    ceiling = num(d.get("ceiling"))
    if ceiling and ceiling > 20:  # typed in cm
        ceiling = ceiling / 100
    if ceiling and (ceiling > 8 or ceiling < 2.2):
        ceiling = None
    power = num(d.get("indust.max_electr"))
    year = num(d.get("house.year"))
    comm = (d.get("com.communications") or "").lower()
    row = dict(
        id=r["id"], deal=deal, price=price, area=area, ppm=ppm, lppm=math.log(ppm),
        type=first_type, multi_type=("," in ttype), district=district, complex=(d.get("office.complex_name") or "").strip(),
        line=(d.get("com.location_line") or "не указана").strip().lower(),
        entrance=entrance_cat(d.get("com.entrance_opts")), entrance_raw=(d.get("com.entrance_opts") or "").strip().lower(),
        renovation=(d.get("com.renovation") or "не указано").strip().lower(),
        parking=(d.get("com.parking_opts") or "не указана").strip().lower(),
        placement=(d.get("com.location") or "не указано").strip().lower(),
        ceiling=ceiling, ceiling_band=band(ceiling, (3.0, 3.5, 4.0, 99), ("<3 м", "3–3.5 м", "3.5–4 м", "4 м+")),
        power=power, power_band=band(power, (10, 20, 40, 80, 1e9), ("<10 кВт", "10–20", "20–40", "40–80", "80+")),
        floor=floor_cat(d.get("house.floor_num"), text), year=year,
        year_band=band(year, (2010, 2018, 2022, 2025, 9999), ("<2010", "2010–2017", "2018–2021", "2022–2024", "2025+")),
        area_band=area_band(area), owner=(d.get("userType") or "?"),
        vent=("вентиляц" in comm), sewer=("канализ" in comm), photos=d.get("photos") or 0,
        lat=lat, lon=lon, desc_len=len(desc),
    )
    for k, rx in KEYWORDS.items():
        row["kw:" + k] = bool(re.search(rx, text))
    if lat and lon:
        for name, (la, lo) in LANDMARKS.items():
            row["d_" + name] = hav(lat, lon, la, lo)
        row["d_center"] = min(row["d_Байтерек"], row["d_Старый центр (Республики/Сейфуллина)"])
        row["d_leftbank"] = min(row["d_Байтерек"], row["d_Хан Шатыр"], row["d_Mega Silk Way"])
    rows.append(row)

df = pd.DataFrame(rows)
df["dist_band"] = df.get("d_center", pd.Series(dtype=float)).map(
    lambda v: band(v, (1.5, 3, 5, 8, 1e9), ("<1.5 км", "1.5–3", "3–5", "5–8", "8+ км")) if v == v else None)

# supply density: rent listings within 300 m / 1 km (all rent rows with coords)
rent_pts = df[(df.deal == "rent") & df.lat.notna()][["lat", "lon"]].to_numpy()
if len(rent_pts):
    lat0 = np.radians(rent_pts[:, 0]); lon0 = np.radians(rent_pts[:, 1])
    def dens(lat, lon, km):
        if lat != lat or lat is None:
            return None
        p1 = math.radians(lat); dl = lon0 - math.radians(lon); dp = lat0 - p1
        a = np.sin(dp / 2) ** 2 + math.cos(p1) * np.cos(lat0) * np.sin(dl / 2) ** 2
        return int((2 * 6371 * np.arcsin(np.sqrt(a)) <= km).sum()) - 1
    df["n300"] = [dens(a, b, 0.3) if a == a else None for a, b in zip(df.lat, df.lon)]
    df["n1000"] = [dens(a, b, 1.0) if a == a else None for a, b in zip(df.lat, df.lon)]
    df["dens_band"] = df.n300.map(lambda v: band(v, (3, 10, 25, 1e9), ("0–2", "3–9", "10–24", "25+")) if v == v else None)

out = {"n": {"rent": int((df.deal == "rent").sum()), "sale": int((df.deal == "sale").sum())}}
md = [f"# Факторный анализ krisha.kz · Астана · аренда n={out['n']['rent']}, продажа n={out['n']['sale']}\n"]
fmt = lambda v: "-" if v is None or v != v else f"{v:,.0f}".replace(",", " ")


def table(deal, col, min_n=8, label=None, order=None):
    sub = df[df.deal == deal].copy()
    sub = sub[sub[col].notna()]
    if sub.empty:
        return
    # index relative to the district median to remove district mix
    dmed = sub.groupby("district").ppm.median()
    sub["idx"] = sub.ppm / sub.district.map(dmed)
    g = sub.groupby(col).agg(n=("ppm", "size"), med=("ppm", "median"), p25=("ppm", lambda s: s.quantile(.25)),
                             p75=("ppm", lambda s: s.quantile(.75)), idx=("idx", "median"))
    g = g[g.n >= min_n]
    if g.empty:
        return
    if order:
        g = g.reindex([o for o in order if o in g.index])
    else:
        g = g.sort_values("med", ascending=False)
    unit = "₸/м²/мес" if deal == "rent" else "₸/м²"
    md.append(f"\n### {label or col} · {'аренда' if deal == 'rent' else 'продажа'} ({unit})\n")
    md.append("| уровень | n | медиана | p25 | p75 | индекс к району |\n|---|---|---|---|---|---|")
    for k, r in g.iterrows():
        md.append(f"| {k} | {int(r.n)} | {fmt(r.med)} | {fmt(r.p25)} | {fmt(r.p75)} | {r.idx:.2f} |")
    out.setdefault("tables", {}).setdefault(deal, {})[label or col] = {str(k): dict(n=int(r.n), med=float(r.med), idx=float(r.idx)) for k, r in g.iterrows()}


FACTORS = [
    ("district", "Район", None), ("type", "Тип помещения (первый в заголовке)", None),
    ("line", "Линия домов", None), ("entrance", "Вход", None), ("ceiling_band", "Высота потолков", ["<3 м", "3–3.5 м", "3.5–4 м", "4 м+"]),
    ("floor", "Этаж", ["подвал/полуподвал", "цоколь", "1 этаж", "2 этаж", "3+ этаж", "не указан"]),
    ("renovation", "Состояние", None), ("parking", "Парковка", None), ("placement", "Размещение объекта", None),
    ("power_band", "Выделенная мощность", ["<10 кВт", "10–20", "20–40", "40–80", "80+"]),
    ("year_band", "Год постройки", ["<2010", "2010–2017", "2018–2021", "2022–2024", "2025+"]),
    ("area_band", "Площадь", ["<30", "30–60", "60–100", "100–150", "150–250", "250–500", "500+"]),
    ("dist_band", "Расстояние до центра (Байтерек/старый центр)", ["<1.5 км", "1.5–3", "3–5", "5–8", "8+ км"]),
    ("dens_band", "Объявлений аренды в радиусе 300 м (конкуренция/кластер)", ["0–2", "3–9", "10–24", "25+"]),
    ("owner", "Кто разместил", None), ("vent", "Вентиляция в коммуникациях", None),
]
for deal in ("rent", "sale"):
    md.append(f"\n## {'АРЕНДА' if deal == 'rent' else 'ПРОДАЖА'}\n")
    for col, label, order in FACTORS:
        if col in df.columns:
            table(deal, col, label=label, order=order)
    md.append(f"\n### Ключевые слова в описании · {'аренда' if deal == 'rent' else 'продажа'}\n")
    md.append("| слово | n с | медиана с | медиана без | индекс с | индекс без |\n|---|---|---|---|---|---|")
    sub = df[df.deal == deal].copy()
    dmed = sub.groupby("district").ppm.median(); sub["idx"] = sub.ppm / sub.district.map(dmed)
    for k in KEYWORDS:
        c = "kw:" + k
        a, b = sub[sub[c]], sub[~sub[c]]
        if len(a) >= 8:
            md.append(f"| {k} | {len(a)} | {fmt(a.ppm.median())} | {fmt(b.ppm.median())} | {a.idx.median():.2f} | {b.idx.median():.2f} |")

# Line premium by district (rent)
md.append("\n## Премия первой линии по районам · аренда\n")
md.append("| район | n первая | медиана первая | n во дворе | медиана во дворе | первая / двор |\n|---|---|---|---|---|---|")
sub = df[df.deal == "rent"]
out["line_by_district"] = []
for dname, g in sub.groupby("district"):
    a, b = g[g.line == "первая"].ppm, g[g.line == "во дворе"].ppm
    if len(a) >= 10 and len(b) >= 5:
        md.append(f"| {dname} | {len(a)} | {fmt(a.median())} | {len(b)} | {fmt(b.median())} | {a.median()/b.median():.2f} |")
        out["line_by_district"].append(dict(district=dname, n_first=int(len(a)), first=float(a.median()), n_yard=int(len(b)), yard=float(b.median())))
md.append("\n## Вход по районам · аренда\n")
md.append("| район | отдельный с улицы (n, медиана) | со двора (n, медиана) | общий через подъезд (n, медиана) |\n|---|---|---|---|")
for dname, g in sub.groupby("district"):
    a, b, c = g[g.entrance == "отдельный с улицы"].ppm, g[g.entrance == "со двора"].ppm, g[g.entrance == "общий (через подъезд)"].ppm
    if len(a) >= 10:
        md.append(f"| {dname} | {len(a)}, {fmt(a.median())} | {len(b)}, {fmt(b.median()) if len(b) else '-'} | {len(c)}, {fmt(c.median()) if len(c) else '-'} |")

# Complex-level: rent vs sale
md.append("\n## ЖК с арендой и продажей: валовая доходность\n")
cx = df[df.complex != ""].groupby(["complex", "deal"]).agg(n=("ppm", "size"), med=("ppm", "median"), district=("district", "first")).unstack("deal")
if not cx.empty and ("n", "rent") in cx.columns and ("n", "sale") in cx.columns:
    cx = cx[(cx[("n", "rent")] >= 3) & (cx[("n", "sale")] >= 3)].copy()
    cx["yield"] = cx[("med", "rent")] * 12 / cx[("med", "sale")]
    cx = cx.sort_values("yield", ascending=False)
    md.append("| ЖК | район | n аренда | аренда ₸/м²/мес | n продажа | продажа ₸/м² | валовая доходность |\n|---|---|---|---|---|---|---|")
    yv = lambda r: float(r["yield"].iloc[0]) if hasattr(r["yield"], "iloc") else float(r["yield"])
    for k, r in cx.iterrows():
        md.append(f"| {k} | {r[('district','rent')]} | {int(r[('n','rent')])} | {fmt(r[('med','rent')])} | {int(r[('n','sale')])} | {fmt(r[('med','sale')])} | {yv(r)*100:.1f}% |")
    out["complex_yield"] = [dict(complex=k, district=r[("district", "rent")], n_rent=int(r[("n", "rent")]), rent=float(r[("med", "rent")]), n_sale=int(r[("n", "sale")]), sale=float(r[("med", "sale")]), yld=yv(r)) for k, r in cx.iterrows()]

# District rent vs sale
md.append("\n## Районы: аренда vs продажа\n")
dd = df.groupby(["district", "deal"]).agg(n=("ppm", "size"), med=("ppm", "median")).unstack("deal")
md.append("| район | n аренда | аренда ₸/м²/мес | n продажа | продажа ₸/м² | валовая доходность |\n|---|---|---|---|---|---|")
for k, r in dd.iterrows():
    nr, ns = r.get(("n", "rent"), 0), r.get(("n", "sale"), 0)
    if nr >= 10 and ns >= 10:
        y = r[("med", "rent")] * 12 / r[("med", "sale")]
        md.append(f"| {k} | {int(nr)} | {fmt(r[('med','rent')])} | {int(ns)} | {fmt(r[('med','sale')])} | {y*100:.1f}% |")

# OLS: effects controlling for district, type, area
md.append("\n## Регрессия log(₸/м²): эффект каждого фактора при прочих равных\n")
out["ols"] = {}
for deal in ("rent", "sale"):
    sub = df[df.deal == deal].copy()
    for c in ("line", "entrance", "ceiling_band", "floor", "renovation", "placement", "area_band", "year_band", "dist_band", "dens_band", "district", "type", "power_band", "parking"):
        if c in sub.columns:
            sub[c] = sub[c].fillna("не указано").astype(str)
            vc = sub[c].value_counts()
            sub.loc[sub[c].isin(vc[vc < 8].index), c] = "прочее"
    sub["line"] = pd.Categorical(sub.line, categories=sorted(sub.line.unique(), key=lambda x: (x != "первая", x)))
    sub["floor"] = pd.Categorical(sub.floor, categories=sorted(sub.floor.unique(), key=lambda x: (x != "1 этаж", x)))
    sub["entrance"] = pd.Categorical(sub.entrance, categories=sorted(sub.entrance.unique(), key=lambda x: (x != "отдельный с улицы", x)))
    sub["type"] = pd.Categorical(sub.type, categories=sorted(sub.type.unique(), key=lambda x: (x != "свободное назначение", x)))
    sub["district"] = pd.Categorical(sub.district, categories=sorted(sub.district.unique(), key=lambda x: (x != "Есильский", x)))
    sub["year_band"] = pd.Categorical(sub.year_band, categories=sorted(sub.year_band.unique(), key=lambda x: (x != "2018–2021", x)))
    sub["dist_band"] = pd.Categorical(sub.dist_band, categories=sorted(sub.dist_band.unique(), key=lambda x: (x != "1.5–3", x)))
    sub["renovation"] = pd.Categorical(sub.renovation, categories=sorted(sub.renovation.unique(), key=lambda x: (x != "cвежий ремонт" and x != "свежий ремонт", x)))
    sub["ceiling_band"] = pd.Categorical(sub.ceiling_band, categories=sorted(sub.ceiling_band.unique(), key=lambda x: (x != "3–3.5 м", x)))
    sub["area_band"] = pd.Categorical(sub.area_band, categories=sorted(sub.area_band.unique(), key=lambda x: (x != "60–100", x)))
    kws = [c for c in sub.columns if c.startswith("kw:")]
    for c in kws:
        sub[c.replace("kw:", "kw_").replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")] = sub[c].astype(int)
    kwc = [c for c in sub.columns if c.startswith("kw_")]
    keep_kw = [c for c in kwc if any(k in c for k in ("углов", "витраж", "трафик", "остановк", "первая_линия", "вторая_линия", "парковка", "аллея", "двор", "школа", "ТРЦ", "госорган", "арендатор"))]
    formula = "lppm ~ C(district) + C(type) + C(line) + C(entrance) + C(ceiling_band) + C(floor) + C(renovation) + C(area_band) + C(year_band) + C(dist_band) + C(dens_band) + " + " + ".join(keep_kw)
    try:
        m = smf.ols(formula, data=sub).fit(cov_type="HC1")
    except Exception as e:  # noqa
        md.append(f"\n{deal}: регрессия не построена: {e}\n")
        continue
    md.append(f"\n### {'аренда' if deal == 'rent' else 'продажа'} · n={int(m.nobs)} · R²={m.rsquared:.2f}\n")
    md.append("| фактор | эффект на ₸/м² | p | n уровня |\n|---|---|---|---|")
    res = []
    for name, coef in m.params.items():
        if name == "Intercept":
            continue
        p = m.pvalues[name]
        lvl_n = None
        mm = re.match(r"C\((\w+)\)\[T\.(.+)\]", name)
        if mm:
            lvl_n = int((sub[mm.group(1)].astype(str) == mm.group(2)).sum())
            label = f"{mm.group(1)} = {mm.group(2)}"
        else:
            lvl_n = int(sub[name].sum()) if name in sub.columns else None
            label = name.replace("kw_", "описание: ")
        res.append((label, (math.exp(coef) - 1) * 100, p, lvl_n))
    res.sort(key=lambda x: -abs(x[1]))
    for label, eff, p, n in res:
        if n is None or n >= 8:
            md.append(f"| {label} | {eff:+.0f}% | {p:.3f} | {n} |")
    out["ols"][deal] = [dict(factor=l, effect_pct=e, p=p, n=n) for l, e, p, n in res]

# Within-complex contrasts (complex fixed effects) for rent
md.append("\n## Внутри одного ЖК (фиксированный эффект ЖК) · аренда\n")
sub = df[(df.deal == "rent") & (df.complex != "")].copy()
big = sub.complex.value_counts(); sub = sub[sub.complex.isin(big[big >= 4].index)]
if len(sub) > 50:
    for c in ("line", "entrance", "ceiling_band", "floor", "renovation", "area_band"):
        sub[c] = sub[c].fillna("не указано").astype(str)
    sub["line"] = pd.Categorical(sub.line, categories=sorted(sub.line.unique(), key=lambda x: (x != "первая", x)))
    sub["entrance"] = pd.Categorical(sub.entrance, categories=sorted(sub.entrance.unique(), key=lambda x: (x != "отдельный с улицы", x)))
    sub["floor"] = pd.Categorical(sub.floor, categories=sorted(sub.floor.unique(), key=lambda x: (x != "1 этаж", x)))
    sub["area_band"] = pd.Categorical(sub.area_band, categories=sorted(sub.area_band.unique(), key=lambda x: (x != "60–100", x)))
    try:
        m = smf.ols("lppm ~ C(complex) + C(line) + C(entrance) + C(ceiling_band) + C(floor) + C(renovation) + C(area_band) + kw_угловое + kw_витраж", data=sub.assign(**{"kw_угловое": sub["kw:угловое"].astype(int), "kw_витраж": sub["kw:витраж"].astype(int)})).fit(cov_type="HC1")
        md.append(f"n={int(m.nobs)}, ЖК={sub.complex.nunique()}, R²={m.rsquared:.2f}\n")
        md.append("| фактор | эффект | p |\n|---|---|---|")
        for name, coef in m.params.items():
            if name.startswith("C(complex)") or name == "Intercept":
                continue
            md.append(f"| {name} | {(math.exp(coef)-1)*100:+.0f}% | {m.pvalues[name]:.3f} |")
    except Exception as e:  # noqa
        md.append(f"не построено: {e}")

# Coverage of fields
md.append("\n## Заполненность полей (аренда)\n")
sub = df[df.deal == "rent"]
for c, lab in (("line", "Линия домов"), ("entrance", "Вход"), ("ceiling", "Высота потолков"), ("renovation", "Состояние"), ("power", "Мощность"), ("year", "Год постройки"), ("complex", "Название ЖК"), ("lat", "Координаты")):
    if c in sub.columns:
        filled = sub[c].notna() & ~sub[c].astype(str).isin(["", "не указана", "не указан", "не указано"])
        md.append(f"- {lab}: {filled.mean()*100:.0f}%")

open(f"{OUT}/analysis.md", "w", encoding="utf-8").write("\n".join(md))
json.dump(out, open(f"{OUT}/analysis.json", "w"), ensure_ascii=False, indent=1, default=float)
df.to_csv(f"{OUT}/rows.csv", index=False)
print("\n".join(md[:3])); print("written", OUT)
