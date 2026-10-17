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

# BI app catalog card -> (levels on the card, parking price "from", mln ₸)
CARD = {"Turan Tower": ("нет в каталоге", None), "Greenline. Velora": ("1", 8.5), "Capital Park. Art": ("1", 6.6),
        "GreenLine. Verda": ("1", 6.0), "GreenLine. Garden": ("1", 6.3), "ÜIA.DARYN": ("1", 6.8), "Capital Park Vector": ("1", 6.5),
        "Family Gardens": ("1", 8.5), "Atlant": ("1–2", 6.4), "Akbulak Riviera": ("1", 10.9), "Family Balance": ("1–2", 6.5),
        "MOD Ultra": ("1", 6.5), "TAMGA HILLS": ("1", 6.5), "Qasteev": ("1–2", 7.4), "ALEM": ("1", 6.3), "Auez Park": ("1", 5.8),
        "GreenLine. Prima": ("1–2", 9.0), "Greenline. Tiara": ("1", 11.0), "Atlant Unique": ("1–2", 6.3), "MOD Urban": ("1", 6.0),
        "Nexpo Aura": ("1–2", 8.0), "GreenLine.4YOU": ("1–2", 4.8), "MOD Fusion": ("1", 6.7), "Nexpo Grand": ("-1…1", 9.0),
        "UIA DARYN": ("1", 6.2)}

rows = [
    # card name, label, district, apts, apts_src, sheet_places (full parking per the user's sheets), registry_places, confidence, note
    ("Turan Tower", "Turan Tower", "Нура", reg_apts([899]), "реестр", 32, None, "средняя",
     "Карточки нет в каталоге: места, видимо, уже распроданы застройщиком. На krisha место просят 15,5 млн."),
    ("Greenline. Velora", "Greenline. Velora", "Нура", reg_apts([1165]), "реестр", 72, reg_pl([1165]), "высокая", ""),
    ("ÜIA.DARYN", "ÜIA.DARYN (блок F)", "Нура", reg_apts([1263]), "реестр, блок F", 100, reg_pl([1263]), "средняя",
     "Листок — паркинг под блоком F (подъезды 1–4); окраина ÜIA."),
    ("Capital Park. Art", "Capital Park. Art", "Есиль", reg_apts([1122]), "реестр", 221, reg_pl([1122]), "высокая", ""),
    ("GreenLine. Verda", "GreenLine. Verda", "Нура", reg_apts([1068]), "реестр", 124, reg_pl([1068]), "высокая", ""),
    ("GreenLine. Garden", "GreenLine. Garden (1-1 + 1-2)", "Нура", reg_apts([1084, 1120]), "реестр", 215, reg_pl([1084, 1120]), "высокая", ""),
    ("Capital Park Vector", "Capital Park Vector", "Есиль", reg_apts([1276]), "реестр", 174, reg_pl([1276]), "высокая", ""),
    ("Atlant", "Atlant (6-1 + 6-2)", "Есиль", 246 + reg_apts([1013]), "krisha 246 + реестр 20", 254, None, "средняя",
     "Оба уровня: -1 и 1 этаж."),
    ("Family Gardens", "Family Gardens (2 очередь)", "Есиль", reg_apts([1426]), "реестр", 163, None, "высокая", "Ещё 7 мотомест."),
    ("Akbulak Riviera", "Akbulak Riviera", "Алматы", 157, "korter/kapster", 234, None, "высокая",
     "234 места жильцам + 22 гостевых + 10 фитнесу; сдан в 2024, свободно ещё 49."),
    # no sheet — registry only
    ("Family Balance", "Family Balance (= Family Nest G)", "Есиль", reg_apts([1480]), "реестр", None, reg_pl([1480]), "средняя", ""),
    ("MOD Ultra", "MOD Ultra", "Есиль", reg_apts([1155]), "реестр", None, reg_pl([1155]), "средняя", ""),
    ("TAMGA HILLS", "TAMGA HILLS", "Есиль", reg_apts([1489]), "реестр", None, reg_pl([1489]), "средняя", ""),
    ("Qasteev", "Qasteev (очереди 1–3)", "Нура", reg_apts([1053, 1061, 1220]), "реестр", None, reg_pl([1053, 1061, 1220]), "средняя", ""),
    ("ALEM", "ALEM (Alem Zerde A)", "Нура", reg_apts([1421]), "реестр", None, reg_pl([1421]), "низкая",
     "Какой блок на карточке, не ясно: Alem Sana A+D+E — 1,60, Alem Dara C — 1,27."),
    ("Auez Park", "Auez Park (1 + 2)", "Сарайшык", reg_apts([1193, 1427]), "реестр", None, reg_pl([1193, 1427]), "средняя", "Правый берег."),
    ("GreenLine. Prima", "GreenLine. Prima", "Нура", reg_apts([1297]), "реестр", None, reg_pl([1297]), "средняя", ""),
    ("Greenline. Tiara", "Greenline. Tiara", "Нура", reg_apts([1373]), "реестр", None, reg_pl([1373]), "средняя", ""),
    ("Atlant Unique", "Atlant Unique (5-1 + 5-2)", "Есиль", reg_apts([875, 1298]), "реестр", None, 301, "низкая",
     "Мест в реестре нет; 301 — по экологической экспертизе."),
    ("MOD Urban", "MOD Urban (очереди 1–4)", "Есиль", reg_apts([967, 1034, 1143, 1211]), "реестр", None, reg_pl([967, 1034, 1143, 1211]), "средняя", ""),
    ("Nexpo Aura", "Nexpo Aura", "Есиль", reg_apts([1041]), "реестр", None, reg_pl([1041]), "средняя", ""),
    ("GreenLine.4YOU", "GreenLine.4YOU (1 + 2)", "Нура", reg_apts([977, 1066]), "реестр", None, max(R[977]["places"], R[1066]["places"]), "низкая",
     "Две записи реестра (392 и 407), похоже, один паркинг."),
    ("MOD Fusion", "MOD Fusion 1", "Есиль", reg_apts([1367]), "реестр, только очередь 1", None, reg_pl([1367]), "низкая",
     "Если 313 мест на весь MOD Fusion (500 кв. по krisha) — 1,60."),
    ("Nexpo Grand", "Nexpo Grand", "Есиль", reg_apts([1470]), "реестр, только 1-я очередь", None, reg_pl([1470]), "низкая",
     "682 места на весь квартал; при 300–550 квартирах — 0,4–0,8."),
    ("UIA DARYN", "UIA DARYN (комфорт-блоки A, B, C)", "Нура", reg_apts([1313, 1136, 1361]), "реестр", None, reg_pl([1313, 1136, 1361]), "низкая",
     "У H, K, M места в реестре не заполнены."),
]

out = []
for card, label, dist, apts, asrc, sheet, reg, conf, note in rows:
    lv, price = CARD[card]
    main = apts / sheet if sheet else (apts / reg if reg else None)
    out.append(dict(card=card, name=label, district=dist, levels_on_card=lv, price_from_mln=price, apartments=apts,
                    apartments_source=asrc, sheet_places=sheet, registry_places=reg,
                    ratio=round(main, 2) if main else None, ratio_registry=round(apts / reg, 2) if reg else None,
                    basis="листок" if sheet else "реестр", confidence=conf, note=note))
order = {"листок": 0, "реестр": 1}
out.sort(key=lambda o: (order[o["basis"]], o["confidence"] == "низкая", -(o["ratio"] or 0)))
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)

fmt = lambda v: "—" if v is None else ((f"{v:.1f}" if v >= 4.5 else f"{v:.2f}").replace(".", ",") if isinstance(v, float) else f"{v}")
lines = ["| № | ЖК | Район | Уровней (карточка) | Место от, млн ₸ | Квартир | Мест (листок) | Мест (реестр) | Квартир на место | Основа | Уверенность | Комментарий |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for k, o in enumerate(out, 1):
    lines.append(f"| {k} | {o['name']} | {o['district']} | {o['levels_on_card']} | {fmt(o['price_from_mln']) if o['price_from_mln'] else '—'} | "
                 f"{o['apartments']} ({o['apartments_source']}) | {fmt(o['sheet_places'])} | {fmt(o['registry_places'])} | "
                 f"**{fmt(o['ratio'])}** | {o['basis']} | {o['confidence']} | {o['note']} |")
open(sys.argv[3], "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
