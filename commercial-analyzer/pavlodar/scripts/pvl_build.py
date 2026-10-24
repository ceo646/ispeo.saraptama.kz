"""Assemble the report page data (pavlodar_report.html) from the analysis, ranking, zone polygons, basemap,
offer checks and the curated web findings.
usage: pvl_build.py <work dir> <template.html> <out.html> <checks.json>"""
import json, re, sys
from urllib.parse import urlparse
import numpy as np

W, TPL, OUT, CHECKS = sys.argv[1:5]
A = json.load(open(f"{W}/analysis.json"))
RK = json.load(open(f"{W}/rank.json"))
ZP = json.load(open(f"{W}/zone_polys.json"))
B = json.load(open(f"{W}/basemap.json"))
F = json.load(open(f"{W}/findings_all.json"))
CAND = {c["id"]: c for c in json.load(open(f"{W}/candidates.json"))}
CHK = {c["id"]: c for c in json.load(open(CHECKS))}
ROWS = json.load(open(f"{W}/rows.json"))
AIG = json.load(open(f"{W}/aigul.json")) if __import__("os").path.exists(f"{W}/aigul.json") else None

SHORT = {"Центр": "Центр", "Юг центра: Горького–Ломова": "Юг центра", "Квазар и Центральный рынок": "Квазар",
         "пр. Назарбаева: Артур и Ярмарка": "Артур, Ярмарка", "Вокзал, Телецентр, Северный": "Вокзал",
         "Сарыарка и Batyr Mall": "Сарыарка", "Затон": "Затон", "Усольский": "Усольский",
         "пр. Назарбаева южнее Ломова (Айгуль)": "Айгуль", "Горторг, Дачный, Достык": "Горторг, Достык",
         "Восток, Второй Павлодар, Зеленстрой": "Восток", "Химгородки и Лесозавод": "Химгородки",
         "Промзоны (Северная, Центральная, Восточная)": "Промзона"}
NOTE = {
    "Центр": "Сатпаева – Торайгырова – Бектурова – Лермонтова, площадь Победы, набережная",
    "Юг центра: Горького–Ломова": "Горького – Ломова от Иртыша до Абая: вузы, бывший Затонский рынок",
    "Квазар и Центральный рынок": "Естая – Абая – Нуркина – Бухар жырау, ТД «Квазар», центральный рынок",
    "пр. Назарбаева: Артур и Ярмарка": "пр. Назарбаева от Толстого до Торайгырова: «Артур», «Гулливер», «Ярмарка»",
    "Вокзал, Телецентр, Северный": "Привокзальная площадь, Телецентр, частный сектор у железной дороги",
    "Сарыарка и Batyr Mall": "Катаева – Камзина – Ломова, ТРЦ Batyr Mall",
    "Затон": "южнее Ломова у затона: бараки, частный сектор, ул. Затон",
    "Усольский": "Бекхожина, Ткачёва, Майры, набережная Усолки",
    "пр. Назарбаева южнее Ломова (Айгуль)": "пр. Назарбаева от Ломова до Макатаева: «Айгуль», автосалоны, «12 месяцев»",
    "Горторг, Дачный, Достык": "юг: частный сектор Горторга, Дачный, новый микрорайон Достык",
    "Восток, Второй Павлодар, Зеленстрой": "восточнее Камзина: Восточный, Второй Павлодар, Зеленстрой",
    "Химгородки и Лесозавод": "север у Иртыша: Химгородки, Хромзавод, Лесозавод",
    "Промзоны (Северная, Центральная, Восточная)": "Северная, Центральная и Восточная промзоны, ул. Торговая",
}
WEB = {
    "Центр": "32 бизнес-центра, вузы, акиматы. Лучшие отзывы у обновлённых БЦ (Capital, Аблай, Altyn); старый ЦУМ и City Centre пустеют",
    "Юг центра: Горького–Ломова": "Местные считают это центром; на месте Затонского рынка строят торговый дом",
    "Квазар и Центральный рынок": "Живой рынок, трафик держит Kazak Market; квартал отдают под многоэтажки",
    "пр. Назарбаева: Артур и Ярмарка": "«Второй центр» по числу арендаторов, но о «Гулливере» и «Артуре» пишут, что они пустеют",
    "Вокзал, Телецентр, Северный": "Транзитный поток у вокзала; для офисов слабо",
    "Сарыарка и Batyr Mall": "Batyr Mall — главный ТРЦ города; новые дома строят без коммерции, магазинов не хватает",
    "Затон": "Частный сектор решили сохранить, бараки сносит частный инвестор; неопределённость",
    "Усольский": "Лучший рейтинг среди районов в 2ГИС (4,4); плотная застройка, заходят сети; жители против крупного ТРЦ",
    "пр. Назарбаева южнее Ломова (Айгуль)": "",
    "Горторг, Дачный, Достык": "Достык растёт (≈2 000 квартир, «всего два магазина»), но жильё социальное, чек низкий",
    "Восток, Второй Павлодар, Зеленстрой": "Частный сектор, подтопление, автобусный маршрут закрыли из-за пустых автобусов",
    "Химгородки и Лесозавод": "Спальный район у промзоны, жалобы на запах; Торайгырова ждёт реновации",
    "Промзоны (Северная, Центральная, Восточная)": "Склады и базы: спрос держат СЭЗ «Павлодар», ПНХЗ и подрядчики",
}
if AIG and AIG.get("web"):
    WEB["пр. Назарбаева южнее Ломова (Айгуль)"] = AIG["web"]

rank = {r["zone"]: r for r in RK["rows"]}
# our 6 typical listings gave 13%; a targeted web check and a skeptic pass of the avenue frontage give 8–10%
OVERRIDE = {"пр. Назарбаева южнее Ломова (Айгуль)": dict(y_list=0.09, y_list_lo=0.08, y_list_hi=0.10, corrected=True,
            note="пр. Назарбаева от Ломова до Макатаева. Наша выборка давала 13%, внешняя проверка первой линии — 8–10%")}
LABEL = {"пр. Назарбаева южнее Ломова (Айгуль)": [76.9725, 52.2545], "Усольский": [76.9440, 52.2500], "Затон": [76.9455, 52.2620]}
zones = []
for z in A["zones"]:
    zn = z["zone"]
    zones.append(dict(zone=zn, short=SHORT[zn], note=NOTE[zn], web=WEB[zn], polys=ZP[zn]["polys"], label=LABEL.get(zn, ZP[zn]["label"]),
                      n_rent=z["n_rent"], n_sale=z["n_sale"], rent=z["rent"],
                      y_list=z["yield_typ"], y_list_lo=z["yield_typ_lo"], y_list_hi=z["yield_typ_hi"], n_y=z["n_typ"],
                      y_all=z["yield_listing_med"], y_raw=z["yield_raw"], y_adj=z["yield_adj"], sale=z["sale_typ"] or z["sale"]))
    if zn in OVERRIDE:
        zones[-1].update(OVERRIDE[zn])


FIELD = re.compile(r"\s*\((?:[^()]*?)(?:com|estate|flat|house|office|indust)\.[a-z_.]+[^()]*\)|\s*(?:com|estate|flat|house|office|indust)\.[a-z_.]+\s*=?\s*(?:«[^»]*»|\"[^\"]*\"|[\w.]+)?")


def first_sentences(t, limit=230):
    t = FIELD.sub("", t or "")
    t = re.sub(r"\s+", " ", t).replace(" ,", ",").replace("( ", "(").strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[А-ЯA-ZЁ«])", t)
    out = ""
    for p in parts:
        if out and len(out) + len(p) + 1 > limit:
            break
        out = (out + " " + p).strip()
        if len(out) >= limit * 0.6:
            break
    return out


def kind_of(t):
    head = t.lower().strip()[:90]
    if "гараж" in head or head.startswith("отдельно стоящий дом") or "бокс" in head:
        return "другое"
    if head.startswith(("отдельно стоящ", "продаётся всё", "продается всё", "здание целиком", "продаётся отдельно",
                        "продается отдельно")) or "здание целиком" in head[:40]:
        return "здание целиком"
    return "встроенное помещение"


ZONE_OF = {s["id"]: s["zone"] for s in A["sales"]}
offers = []
for i, c in CHK.items():
    o, r = c.get("object"), c.get("rent")
    if not o or not r or o["verdict"] == "reject" or not r.get("gross_yield"):
        continue
    cd = CAND[i]
    offers.append(dict(id=i, address=cd["address"], zone=ZONE_OF.get(i, cd["zone"]), grp=cd["group"], area=cd["area_m2"], price=cd["price_tenge"],
                       ppm=cd["price_per_m2"], rent=r["realistic_rent_per_m2"], gross=r["gross_yield"], net=r["net_yield"],
                       verdict=o["verdict"], kind=kind_of(o["what_is_sold"]), nflags=len(o["red_flags"]), y0=cd["our_estimate"]["gross_yield"],
                       what=first_sentences(o["what_is_sold"], 240),
                       flags=[first_sentences(f, 200) for f in o["red_flags"][:2]]))
offers.sort(key=lambda o: -o["net"])
rejected = [i for i, c in CHK.items() if c.get("object") and c["object"]["verdict"] == "reject"]
pick_ids = {o["id"] for o in offers}

sales = []
for s in A["sales"]:
    c = CHK.get(s["id"])
    chk = None
    if c and c.get("rent") and c.get("object"):
        chk = dict(gross=c["rent"]["gross_yield"], net=c["rent"]["net_yield"], what=first_sentences(c["object"]["what_is_sold"], 200))
    sales.append(dict(id=s["id"], lat=s["lat"], lon=s["lon"], zone=s["zone"], grp=s["grp"], area=s["area"], price=s["price"],
                      ppm=s["ppm"], est_rent=s["est_rent"], y=s["yield_"], address=s["address"], pick=s["id"] in pick_ids, check=chk))
rents = [dict(id=r["id"], lat=r["lat"], lon=r["lon"], ppm=r["ppm"], area=r["area"], address=r["address"]) for r in A["rent_points"]]

# type / size table (listing-level)
S = [s for s in A["sales"] if s["comp_n"] >= 5 and s["yield_"] <= 0.35]
med = lambda v: float(np.median(v)) if v else None


def trow(k, sel, note):
    v = [s for s in S if sel(s)]
    return dict(k=k, n=len(v), sale=med([s["ppm"] for s in v]), rent=med([s["est_rent"] for s in v]), y=med([s["yield_"] for s in v]), note=note)


types = [
    trow("Офисы", lambda s: s["grp"] == "офис", "Почти все в Центре; спрос дробный: кабинеты 12–50 м² для юристов, медицины, бьюти-мастеров"),
    trow("Торговля и услуги", lambda s: s["grp"] == "торговля и услуги", "Самый большой сегмент; дорогие входы в новых домах снижают доходность"),
    trow("Свободное назначение", lambda s: s["grp"] == "свободное назначение", "Часто старые отдельные здания: дешевле за м², больше риск простоя"),
    trow("Площадь до 50 м²", lambda s: s["area"] < 50, "Легко сдать, но за метр дороже всего"),
    trow("50–150 м²", lambda s: 50 <= s["area"] < 150, "Основной формат стрит-ритейла и офисов на первом этаже"),
    trow("150–500 м²", lambda s: 150 <= s["area"] < 500, ""),
    trow("Больше 500 м²", lambda s: s["area"] >= 500, "Высокая доходность на бумаге, но нужны несколько арендаторов"),
    trow("В бизнес-центре", lambda s: s["loc"] == "бизнес-центр", "Мало продаж (покупают редко), зато аренда держится"),
    trow("В жилом доме / ЖК", lambda s: s["loc"] == "жилой дом/ЖК", "Первые этажи жилых домов: самые ликвидные"),
    trow("Отдельное здание", lambda s: s["loc"] == "отдельное здание", ""),
]
wh = [r for r in ROWS if not r["excluded"] and not r["nonstd"] and r["seg"] == "склад/производство"]
whr = med([r["ppm"] for r in wh if r["deal"] == "rent"]); whs = med([r["ppm"] for r in wh if r["deal"] == "sale"])
types.append(dict(k="Склады и производство (отдельный рынок)", n=sum(1 for r in wh if r["deal"] == "sale"), sale=whs, rent=whr, y=whr * 12 / whs,
                  note="По отношению медиан; арендаторы — подрядчики ПНХЗ, СЭЗ, логистика"))

# web themes: curated finding indexes (confirmed or partly confirmed by an independent check)
def item(i, text):
    f = F[i]
    assert f["vstatus"] in ("confirmed", "partly"), (i, f["vstatus"])
    return dict(text=text, url=f["source_url"], src=urlparse(f["source_url"]).netloc.replace("www.", ""))


themes = [
    dict(title="Рынок в целом", items=[
        item(0, "Аренда нежилых помещений в Павлодарской области за год выросла на 4,2% (III кв. 2026, БНС) — третье место в стране."),
        item(2, "По Казахстану офисы (+4,8%) и склады (+4,3%) дорожают быстрее магазинов (+1,4%)."),
        item(5, "Аренда жилья в области за год подорожала на 38,9% — максимум по стране: людей и денег в городе прибавилось."),
        item(127, "Инвестиции в основной капитал за 9 месяцев 2026 года выросли на 13,8%, розница — на 3,8%."),
        item(22, "Область теряет жителей: −5,7 тыс. за 9 месяцев 2025 года, больше половины уезжают в Астану."),
        item(115, "После налоговой реформы 2026 года по стране массово закрываются ИП — риск для спроса на маленькие кабинеты."),
    ]),
    dict(title="Офисы и бизнес-центры", items=[
        item(230, "В 2ГИС 23–32 бизнес-центра, почти все в Центре: Торайгырова, Сатпаева, Бектурова, площадь Победы."),
        item(233, "Altyn на площади Победы сдаёт офисы от 3 300 ₸/м² с интернетом, охраной и парковкой."),
        item(232, "«Бизнес Холл» на Дюсенова рекламирует кабинеты от 4 000 ₸/м²."),
        item(254, "Спрос мелкий и сервисный: кабинеты и «места» для косметологов, психологов, юристов, а не этажи для корпораций."),
        item(276, "Capital на Сатпаева, 65 — 66 организаций и лучшие отзывы, управляющая отвечает на отзывы."),
        item(183, "В советском БЦ «8 марта» живы первые этажи, верхние пустуют и требуют ремонта."),
        item(182, "Арендатор БЦ Tabys пишет, что за 7 месяцев аренду подняли дважды — спрос на хорошие офисы есть."),
    ]),
    dict(title="Торговые центры и торговые дома", items=[
        item(258, "Batyr Mall — 26 тыс. оценок в 2ГИС, в 4 раза больше любого ТЦ; с 2025 года парковка платная."),
        item(269, "«Квазар» держится на продуктовом якоре Kazak Market, хвалят парковку."),
        item(263, "О «Гулливере» пишут, что большая часть бутиков закрыта и центр «потихоньку умирает»."),
        item(267, "В «Артуре» мало людей, не работает эскалатор, давно не было ремонта."),
        item(265, "Старый ЦУМ посетители называют «вечно пустым»."),
        item(285, "1 сентября 2026 года в торговом доме сгорели шесть бутиков: пожарный риск старых ТД остаётся."),
    ]),
    dict(title="Районы глазами жителей", items=[
        item(47, "Усольский — лучший рейтинг районов в 2ГИС (4,4), его благоустраивают: экопарк, набережная."),
        item(45, "В Сарыарке, по отзывам, не хватает магазинов и банкоматов, а новые дома строят без коммерческих первых этажей."),
        item(302, "В Достыке «всего два магазина маленькие» при ≈2 000 квартир; жильё в основном социальное."),
        item(224, "Больше всего цветочных магазинов — на Торайгырова, у Бектурова–Назарбаева и на Назарбаева–Ломова: там концентрируется стрит-ритейл."),
        item(304, "Во Втором Павлодаре закрыли автобусный маршрут: автобусы ходили полупустыми."),
        item(48, "В Затоне акимат решил сохранить частный сектор вместо многоэтажек."),
    ]),
    dict(title="Город меняет центр: плюсы и риски", items=[
        item(209, "Улицу Лермонтова сделали пешеходной: плитка, велодорожки, фонтаны."),
        item(288, "Но бизнес на Лермонтова жаловался: парковки убрали, клиентов стало меньше."),
        item(293, "Следующие на реновацию — Естая, затем Торайгырова: возможны перекрытия."),
        item(294, "Ремонт теплотрассы четыре месяца перекрывал подъезд: убытки до 16–18 млн ₸, трое арендаторов съехали."),
        item(104, "На углу Сатпаева и Естая строят Novotel с конференц-залами, открытие в 2027 году."),
        item(105, "Новый мост через Иртыш планируют открыть в декабре 2026 года, старый снесут."),
        item(286, "Под второй крупный ТРЦ оставлено место у Радиозавода, но сроков и инвестора нет."),
    ]),
]
if AIG and AIG.get("items"):
    themes.insert(4, dict(title="пр. Назарбаева южнее Ломова (Айгуль)", items=AIG["items"]))

prem_r = [r["ppm"] for r in A["rent_points"]]
prem_s = [s["ppm"] for s in A["sales"]]
n_clean = sum(1 for r in ROWS if not r["excluded"])
city_y = RK["city_yield"]
top = RK["rows"][0]
D = dict(
    zones=zones, rank=RK["rows"], city=dict(yield_=city_y, **{"yield": city_y}), sales=sales, rents=rents, offers=offers, types=types,
    themes=themes, basemap=dict(footprint=B["footprint"], water=B["water"], parks=B["parks"], roads=B["roads"]),
)
OUTTXT = json.load(open(f"{W}/texts.json"))
D.update(OUTTXT)
D["tiles"] = [
    dict(v=f"{med(prem_r):,.0f}".replace(",", " "), u="₸/м² в месяц", k="медиана аренды офисов и торговых помещений"),
    dict(v=f"{med(prem_s)/1000:,.0f}".replace(",", " "), u="тыс. ₸/м²", k="медиана цены продажи тех же помещений"),
    dict(v=f"{city_y*100:.1f}".replace(".", ","), u="% годовых", k="типичная валовая доходность до налогов и простоя"),
    dict(v=f"{1/city_y:.1f}".replace(".", ","), u="лет", k="окупаемость при такой доходности"),
    dict(v=f"{len(ROWS):,}".replace(",", " "), u="объявлений", k=f"собрано с krisha.kz, {n_clean:,} после очистки".replace(",", " ")),
]
html = open(TPL).read().replace("/*__LEAFLET_CSS__*/", open(f"{W}/leaflet.css").read()).replace("/*__DATA__*/", json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
open(OUT, "w").write(html)
print("offers", len(offers), "rejected", rejected, "size", round(len(html) / 1e6, 2), "MB")
