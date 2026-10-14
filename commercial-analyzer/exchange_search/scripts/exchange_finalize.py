"""Merge the 288-listing verification run into the final ranking and rewrite the report.

usage: exchange_finalize.py <workflow_output.json> <exch_dir> <repo_readme.md>

Inputs in <exch_dir>: verify_candidates.json/verified.json (round 1), verify_candidates2.json/verified2.json
(round 2), judges.json (rounds 1–2), verify_candidates3.json + not_verified3.json (candidates of run 3).
Writes verified3.json, judges_all.json, final_all.json and the README.
"""
import json, os, subprocess, sys

wf_path, d, readme = sys.argv[1], sys.argv[2], sys.argv[3]
o = json.load(open(wf_path))
res = o.get("result", o)
v3 = (res.get("full") or []) + (res.get("promoted_full") or [])
json.dump(v3, open(f"{d}/verified3.json", "w"), ensure_ascii=False, indent=1)
json.dump(res.get("triage") or [], open(f"{d}/triage3.json", "w"), ensure_ascii=False, indent=1)
c3 = json.load(open(f"{d}/verify_candidates3.json")) + json.load(open(f"{d}/not_verified3.json"))
json.dump(c3, open(f"{d}/cand3_all.json", "w"), ensure_ascii=False, indent=1)
judges = json.load(open(f"{d}/judges.json"))
seen = {str(j["id"]) for j in judges}
judges += [j for j in (res.get("judges") or []) if str(j["id"]) not in seen]
json.dump(judges, open(f"{d}/judges_all.json", "w"), ensure_ascii=False, indent=1)
here = os.path.dirname(os.path.abspath(__file__))
print(subprocess.run([sys.executable, "-E", f"{here}/exchange_final.py", f"{d}/final_all.json", f"{d}/judges_all.json",
                      f"{d}/verify_candidates.json", f"{d}/verified.json", f"{d}/verify_candidates2.json", f"{d}/verified2.json",
                      f"{d}/cand3_all.json", f"{d}/verified3.json"], capture_output=True, text=True).stdout)

F = json.load(open(f"{d}/final_all.json"))
new_ids = {str(v["id"]) for v in v3}


def tbl(lst, n):
    L = sorted([r for r in F if r["list"] == lst and r["ok"]], key=lambda r: -r["score"])[:n]
    out = ["| № | Объект | м² | Цена, млн | ₸/м² | Улица · район | Аренда ₸/м² · доходн. | Обмен | Главный риск |",
           "|---|---|---|---|---|---|---|---|---|"]
    for k, r in enumerate(L, 1):
        ex = (r.get("exchange_quote") or "—").replace("|", "/")[:90] if lst == "A" else "молчит"
        new = " 🆕" if r["id"] in new_ids else ""
        out.append(f"| {k} | [{(r.get('address') or '').replace('|', '/')[:45]}]({r['url']}){new} — {(r.get('complex') or '')[:40]} | "
                   f"{r['area']:.0f} | {r['price'] / 1e6:.1f} | {r['ppm'] / 1000:.0f} тыс | {r['frontage']} · {r['maturity']} | "
                   f"{r['rent']} · {r['yield_']}% | {ex} | {(r.get('risk_ru') or '').replace('|', '/')[:150]} |")
    return "\n".join(out), L


ta, LA = tbl("A", 20)
tb, LB = tbl("B", 20)
tri = res.get("triage") or []
md = f"""# Офисы на первой линии в Есиле и Нуре под обмен на квартиру BI (обновлено 15.10.2026)

**Условия.** Есильский и Нура районы, цена до 140 млн ₸, 1 этаж (без цоколя, паркинга и галерей), настоящая первая линия с витриной на улицу, дом сдан или ключи в ближайшие 6 месяцев. Продавец получает квартиру BI Group на свой выбор, равноценно.

**Охват.**
- **Все объявления.** Прочитаны все 1 249 объявлений Есиля и Нуры до 140 млн.
- **Упоминание обмена.** Ещё 364 объявления по всей Астане с «обмен», «бартер», «обменяю».
- **Карточки.** Открыты все карточки подходящего типа и размера: 841 в первом прогоне и ещё 288 ранее пропущенных во втором, с номерными и внутренними адресами.
- **Глубокая проверка.** Карточка заново, точное здание и улица витрины, живые ставки аренды рядом, риски:
  - 89 кандидатов первого прогона;
  - {len(v3)} из второго прогона: 57 сразу, остальные после быстрой проверки локации, где из {len(tri)} отобрано {sum(1 for t in tri if t.get('promote'))}.
- **Разметка.** Два независимых судьи по единым правилам и третий агент для спорных случаев.
- 🆕 — объект из второго прогона.

**Доходность** — чистая: торг 10 %, простой и ОСИ 15 %, налог 4 %, налог на имущество 0,5 %, соцплатежи. Считается по медиане живых запросов аренды рядом; это запросы, а не сделки.

**Ранжирование.** Сначала локация (тип улицы × обжитость × витрина), затем доходность, затем оценка проверяющего.

## A. Продавец сам пишет про обмен ({len(LA)} прошли все фильтры)
{ta}

## B. Про обмен молчат (отказавшиеся убраны) — топ-20
{tb}

## Ограничения
- **Обмен ищется только по тексту.** Список A — только продавцы, которые сами написали об обмене. Список B — им можно предложить обмен по телефону.
- **Аренда — это запросы.** Ставки взяты из объявлений, реальные сделки обычно на 5–15 % ниже.
- **Перед сделкой — осмотр.** Нужно проверить на месте витрину и вход, документы (собственность, залог) и договор с арендатором.
"""
open(readme, "w").write(md)
print("A", len(LA), "B", len(LB), "new in A", sum(r["id"] in new_ids for r in LA), "new in B", sum(r["id"] in new_ids for r in LB))
