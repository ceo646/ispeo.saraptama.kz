# Гайд «Как выбирать офис в Астане»: данные и расчёт

Документ: https://claude.ai/code/artifact/e5bf788a-6f13-4664-8d70-d0c162aeed11

Снимок krisha.kz 13–14.10.2026, Астана, коммерческая недвижимость.

- `data/list_rent.json.gz` — все 5 269 объявлений аренды (страницы выдачи).
- `data/list_sale.json.gz` — 2 524 объявления продажи до 100 млн ₸.
- `data/details_merged.jsonl.gz` — 3 312 карточек с параметрами (линия домов,
  вход, потолки, состояние, мощность, этаж, год, ЖК, описание, координаты).
  Источники: прямой сбор (`scripts/guide_collect.py`) и выборка через
  субагентов (WebFetch), объединены `scripts/guide_merge.py`.
- `data/rows.csv` — таблица признаков после очистки (2 077 аренда, 991 продажа).
- `analysis.md` / `analysis.json` — медианы по каждому фактору, премия первой
  линии по районам, регрессия log(₸/м²) с эффектами при прочих равных.

```
python3 scripts/guide_merge.py <data dir> <wf dir> merged/details.jsonl
python3 scripts/guide_analyze.py merged out     # нужны pandas, statsmodels
```
