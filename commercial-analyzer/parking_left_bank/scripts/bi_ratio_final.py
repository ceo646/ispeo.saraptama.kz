"""Final apartments-per-parking-place table for the BI Group complexes in the app's parking catalog.
usage: bi_ratio_final.py <registry_rows.json> <out.json> <out.md>

Unit = one physical parking (stylobate/building) and all apartments it serves.
Apartments: registry homeportal.kz (sum of queues) unless noted.
Places: (1) BI sale sheet with numbered places = what is on sale on that level;
        (2) project number = registry amount_of_parking_places (or ecoportal OVOS for Atlant).
"""
import json, sys

R = {r["id"]: r for r in json.load(open(sys.argv[1]))}
reg_apts = lambda ids: sum(R[i]["apts"] or 0 for i in ids)
reg_pl = lambda ids: sum(R[i]["places"] or 0 for i in ids)

rows = [
    # name, district, apts, apts_src, sheet_places, project_places, project_src, confidence, note
    ("Turan Tower", "Нура", reg_apts([899]), "реестр", 32, None, "в реестре не заполнено", "средняя",
     "Башня 27 эт. На листке 1 уровень на 32 места; проверить, нет ли других уровней. На krisha место продают за 15,5 млн."),
    ("Greenline. Velora", "Нура", reg_apts([1165]), "реестр", 72, reg_pl([1165]), "реестр", "средняя",
     "Листок 72 места против 138 по проекту: судя по DARYN F и Atlant, на листке один уровень из двух."),
    ("Capital Park. Art", "Есиль", reg_apts([1122]), "реестр", 221, reg_pl([1122]), "реестр", "средняя",
     "Листок 221 против 410 по проекту: судя по DARYN F и Atlant, на листке один уровень из двух."),
    ("GreenLine. Verda", "Нура", reg_apts([1068]), "реестр", 124, reg_pl([1068]), "реестр", "высокая",
     "Листок и проект почти совпадают (124 и 134)."),
    ("GreenLine. Garden (1-1 + 1-2)", "Нура", reg_apts([1084, 1120]), "реестр", 215, reg_pl([1084, 1120]), "реестр", "средняя",
     "Листок 215 против 326 по проекту. Garden 2 — отдельный объект: 390 кв. на 237 мест (1,65)."),
    ("ÜIA.DARYN (бизнес-блоки D, E, F, G)", "Нура", reg_apts([1176, 1233, 1263, 1292]), "реестр", None,
     reg_pl([1176, 1233, 1263, 1292]), "реестр", "средняя", "Привязка карточки к блокам D–G — по классу и срокам. Листок блока F показывает только -1 этаж (100 мест), а в реестре у F 194: реестр считает все уровни."),
    ("Capital Park Vector", "Есиль", reg_apts([1276]), "реестр", 174, reg_pl([1276]), "реестр", "высокая",
     "Листок и проект почти совпадают (174 и 185)."),
    ("Family Balance (= Family Nest G)", "Есиль", reg_apts([1480]), "реестр", None, reg_pl([1480]), "реестр", "средняя",
     "Сопоставление по сроку сдачи (01.2028) и описанию metry."),
    ("MOD Ultra", "Есиль", reg_apts([1155]), "реестр", None, reg_pl([1155]), "реестр", "высокая", ""),
    ("TAMGA HILLS", "Есиль", reg_apts([1489]), "реестр", None, reg_pl([1489]), "реестр", "высокая", "Крупные квартиры, 5 этажей."),
    ("Qasteev (очереди 1–3)", "Нура", reg_apts([1053, 1061, 1220]), "реестр", None, reg_pl([1053, 1061, 1220]), "реестр", "высокая",
     "Паркинг двухуровневый."),
    ("ALEM (Alem Zerde A)", "Нура", reg_apts([1421]), "реестр", None, reg_pl([1421]), "реестр", "низкая",
     "Какой блок бигвилля на карточке, не ясно: Alem Sana A+D+E — 711/443 (1,60), Alem Dara C — 366/288 (1,27)."),
    ("Auez Park (1 + 2)", "Сарайшык", reg_apts([1193, 1427]), "реестр", None, reg_pl([1193, 1427]), "реестр", "высокая", "Правый берег."),
    ("GreenLine. Prima", "Нура", reg_apts([1297]), "реестр", None, reg_pl([1297]), "реестр", "высокая", ""),
    ("Greenline. Tiara", "Нура", reg_apts([1373]), "реестр", None, reg_pl([1373]), "реестр", "высокая", ""),
    ("Atlant Unique (5-1 + 5-2)", "Есиль", reg_apts([875, 1298]), "реестр", None, 301, "ООС ecoportal", "средняя",
     "В реестре места не заполнены; 301 место по экологической экспертизе."),
    ("MOD Urban (очереди 1–4)", "Есиль", reg_apts([967, 1034, 1143, 1211]), "реестр", None, reg_pl([967, 1034, 1143, 1211]), "реестр", "высокая", ""),
    ("Nexpo Aura", "Есиль", reg_apts([1041]), "реестр", None, reg_pl([1041]), "реестр", "высокая", ""),
    ("GreenLine.4YOU (1 + 2)", "Нура", reg_apts([977, 1066]), "реестр", None, max(R[977]["places"], R[1066]["places"]), "реестр (одна запись паркинга)", "средняя",
     "Две записи реестра (392 и 407) описывают один двухуровневый паркинг."),
    ("Atlant (6 + 6-2)", "Есиль", 246 + reg_apts([1013]), "krisha 246 + реестр 20", 254, 254, "листок BI, оба уровня", "средняя",
     "Листок 6.2 показывает оба уровня: -1 этаж (места 1–104 и 224–254) и 1 этаж (105–223). Квартиры 6-й очереди в реестре не заполнены."),
    ("MOD Fusion 1", "Есиль", reg_apts([1367]), "реестр (только очередь 1)", None, reg_pl([1367]), "реестр", "низкая",
     "Если паркинг на весь MOD Fusion (500 кв. по krisha) — 1,60."),
    ("Nexpo Grand", "Есиль", reg_apts([1470]), "реестр (только 1-я очередь)", None, reg_pl([1470]), "реестр", "низкая",
     "682 места на весь квартал; всех квартир по оценке 300–550, то есть 0,4–0,8."),
    ("Family Gardens (1 + 2)", "Есиль", reg_apts([1142, 1426]), "реестр", None, reg_pl([1142]) + 163, "реестр (1 очередь) + листок (2 очередь)", "высокая",
     "2 очередь: 163 места для машин (+7 мото) на 165 квартир; 1 очередь: 164 места на 150 квартир."),
    ("UIA DARYN (комфорт-блоки A, B, C)", "Нура", reg_apts([1313, 1136, 1361]), "реестр", None,
     reg_pl([1313, 1136, 1361]), "реестр", "низкая",
     "Блоки H, K, M (978 кв.) — места в реестре не заполнены; рядом строят отдельное здание паркинга. Если H, K, M без своего паркинга, по всем шести блокам 2190/1020 = 2,15."),
    ("Akbulak Riviera", "Алматы", 157, "korter/kapster", 234, 266, "листок BI (всего 266, из них 22 гостевых и 10 фитнес)", "высокая",
     "Сдан в 2024, а свободно ещё 49 мест: мест явно больше, чем нужно жильцам."),
]

order = {"высокая": 0, "средняя": 0, "низкая": 1, "нет": 2}
# rank by the project number (all levels) when known; the sale sheets often show one level only
rows.sort(key=lambda r: (order[r[7]], -(r[2] / r[5] if r[5] else r[2] / r[4] if r[4] else 0)))
out = []
for name, dist, apts, asrc, sheet, proj, psrc, conf, note in rows:
    out.append(dict(name=name, district=dist, apartments=apts, apartments_source=asrc, sheet_places=sheet, project_places=proj,
                    project_source=psrc, ratio_sheet=round(apts / sheet, 2) if sheet else None,
                    ratio_project=round(apts / proj, 2) if proj else None, confidence=conf, note=note))
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)

fmt = lambda v: "—" if v is None else (f"{v:,.2f}".replace(",", " ").replace(".", ",") if isinstance(v, float) else f"{v}")
lines = ["| № | ЖК | Район | Квартир | Мест по листку | Мест по проекту | Квартир на место (листок / проект) | Уверенность | Комментарий |",
         "|---|---|---|---|---|---|---|---|---|"]
for k, o in enumerate(out, 1):
    r = " / ".join(x for x in [fmt(o["ratio_sheet"]) if o["sheet_places"] else None, fmt(o["ratio_project"]) if o["project_places"] else None] if x) or "—"
    lines.append(f"| {k} | {o['name']} | {o['district']} | {o['apartments']} ({o['apartments_source']}) | {fmt(o['sheet_places'])} | "
                 f"{fmt(o['project_places'])} ({o['project_source']}) | **{r}** | {o['confidence']} | {o['note']} |")
open(sys.argv[3], "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
