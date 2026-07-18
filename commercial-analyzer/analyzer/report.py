"""HTML report generation for the top-N ranked commercial deals."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone

from .config import Config
from .models import ScoredDeal

_CITY_TITLE = {
    "astana": "Астана", "almaty": "Алматы", "shymkent": "Шымкент",
    "karaganda": "Караганда", "aktobe": "Актобе", "atyrau": "Атырау",
}


def _fmt_money(v: float | int | None) -> str:
    if v is None:
        return "—"
    return f"{int(round(v)):,}".replace(",", " ") + " ₸"


def _fmt_num(v, suffix=""):
    return "—" if v is None else f"{v}{suffix}"


def _rows(deals: list[ScoredDeal]) -> str:
    cells = []
    for i, d in enumerate(deals, 1):
        r = d.to_row()
        score_hue = 120 * min(1.0, r["score"] / 100)
        badge = ('<span class="flag" title="Доходность/дисконт выше обычного — '
                 'обязательно проверьте объект вручную">⚠ проверить</span>'
                 if r["verify"] else "")
        cells.append(f"""
        <tr>
          <td class="rank">{i}</td>
          <td><span class="score" style="--hue:{score_hue:.0f}">{r['score']}</span></td>
          <td class="title"><a href="{html.escape(r['url'])}" target="_blank" rel="noopener">{html.escape(r['title'])}</a>{badge}</td>
          <td>{html.escape(r['district'])}</td>
          <td class="num">{_fmt_num(r['area'], ' м²')}</td>
          <td class="num">{html.escape(str(r['floor']))}</td>
          <td class="num">{_fmt_money(r['price'])}</td>
          <td class="num">{_fmt_money(r['price_per_m2'])}</td>
          <td class="num">{_fmt_money(r['est_monthly_rent'])}<span class="sub">/мес</span></td>
          <td class="basis">{html.escape(r['rent_basis'] or '—')}</td>
          <td class="num pos">{r['gross_yield_pct']}%</td>
          <td class="num">{r['payback_years']} лет</td>
          <td class="num {'pos' if r['price_discount_pct'] > 0 else 'neg'}">{r['price_discount_pct']:+}%</td>
          <td class="num conf">{r['confidence']}</td>
        </tr>""")
    return "".join(cells)


def render_html(deals: list[ScoredDeal], cfg: Config,
                sale_count: int, rent_count: int) -> str:
    city = _CITY_TITLE.get(cfg.city.lower(), cfg.city.title())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    w = cfg.analysis.weights
    avg_yield = (sum(d.gross_yield for d in deals) / len(deals) * 100
                 if deals else 0)
    empty = "" if deals else (
        '<p class="empty">Нет объявлений, прошедших фильтры. '
        'Проверьте, что скрапинг вернул данные (krisha.kz доступен и не '
        'блокирует запросы), и ослабьте фильтры в config.yaml.</p>')

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Топ-{cfg.analysis.top_n} коммерческой недвижимости — {city}</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#fff; --ink:#1a1d21; --muted:#6b7280;
    --line:#e5e7eb; --accent:#2563eb; --pos:#059669; --neg:#dc2626;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0f1115; --card:#171a21; --ink:#e7e9ee; --muted:#9aa4b2;
             --line:#262b35; --accent:#4f8cff; --pos:#34d399; --neg:#f87171; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1200px; margin:0 auto; padding:32px 20px 64px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  .sub-title {{ color:var(--muted); margin:0 0 24px; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:24px; }}
  .stat {{ background:var(--card); border:1px solid var(--line);
    border-radius:12px; padding:14px 18px; min-width:150px; }}
  .stat b {{ display:block; font-size:22px; }}
  .stat span {{ color:var(--muted); font-size:13px; }}
  .table-wrap {{ overflow-x:auto; background:var(--card);
    border:1px solid var(--line); border-radius:14px; }}
  table {{ border-collapse:collapse; width:100%; min-width:1000px; font-size:13px; }}
  th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid var(--line);
    white-space:nowrap; }}
  th {{ position:sticky; top:0; background:var(--card); font-size:12px;
    text-transform:uppercase; letter-spacing:.03em; color:var(--muted); }}
  tr:hover td {{ background:rgba(127,127,127,.06); }}
  .rank {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .title a {{ color:var(--accent); text-decoration:none; }}
  .title a:hover {{ text-decoration:underline; }}
  .title {{ white-space:normal; min-width:220px; }}
  .sub {{ color:var(--muted); font-size:11px; }}
  .pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }}
  .conf {{ color:var(--muted); }}
  .basis {{ color:var(--muted); font-size:12px; white-space:nowrap; }}
  .score {{ display:inline-block; min-width:42px; text-align:center;
    padding:3px 8px; border-radius:8px; font-weight:700; color:#fff;
    background:hsl(var(--hue) 65% 42%); }}
  .flag {{ display:inline-block; margin-left:8px; padding:1px 7px;
    border-radius:6px; font-size:11px; font-weight:600; white-space:nowrap;
    color:#92400e; background:#fef3c7; border:1px solid #fbbf24; }}
  @media (prefers-color-scheme: dark) {{
    .flag {{ color:#fde68a; background:#3a2f10; border-color:#a16207; }}
  }}
  .method {{ margin-top:28px; color:var(--muted); font-size:13px;
    background:var(--card); border:1px solid var(--line);
    border-radius:12px; padding:16px 20px; }}
  .method code {{ background:rgba(127,127,127,.12); padding:1px 5px;
    border-radius:4px; }}
  .empty {{ padding:24px; color:var(--neg); }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Топ-{len(deals)} коммерческих помещений для сдачи в аренду — {city}</h1>
  <p class="sub-title">Источник: krisha.kz · сформировано {now} · фильтр цены
    ≤ {_fmt_money(cfg.deal.price_to)} · без цоколя/подвала</p>

  <div class="stats">
    <div class="stat"><b>{sale_count}</b><span>объявлений о продаже</span></div>
    <div class="stat"><b>{rent_count}</b><span>объявлений об аренде</span></div>
    <div class="stat"><b>{len(deals)}</b><span>в шортлисте</span></div>
    <div class="stat"><b>{avg_yield:.1f}%</b><span>средняя доходность топа</span></div>
  </div>

  {empty}
  <div class="table-wrap">
  <table>
    <thead><tr>
      <th>#</th><th>Скор</th><th>Объявление</th><th>Район</th><th>Площадь</th>
      <th>Этаж</th><th>Цена</th><th>Цена/м²</th><th>Аренда (оц.)</th>
      <th>База аренды</th><th>Доходность</th><th>Окупаемость</th>
      <th>Дисконт к рынку</th><th>Довер.</th>
    </tr></thead>
    <tbody>{_rows(deals)}</tbody>
  </table>
  </div>

  <div class="method">
    <b>Как считается композитный скор.</b>
    Ожидаемая аренда = площадь × медианная ставка аренды за м² по району
    <i>и близкому размеру</i> помещения (усечённая медиана по объявлениям
    аренды krisha.kz — крайние выбросы отброшены). Доходность = аренда×12 /
    цена; окупаемость = 1/доходности; дисконт к рынку = насколько цена за м²
    ниже медианы района. Скор нормализует три компонента с весами:
    доходность <code>{w.yield_}</code>, дисконт <code>{w.discount}</code>,
    надёжность <code>{w.confidence}</code>. «Надёжность» = объём данных по
    аренде района × правдоподобие (доходность, сильно превышающая типичную
    для района, считается менее достоверной и понижается в рейтинге).
    <br><br>
    <b>Фильтры:</b> цена ≤ {_fmt_money(cfg.deal.price_to)}; исключены
    цокольные/подвальные/полуподвальные; отброшены аномальные доходности
    (&gt;{round(cfg.analysis.max_plausible_yield*100)}%) и подозрительно
    дешёвые лоты (дисконт &gt;{round(cfg.analysis.max_discount*100)}% —
    почти всегда битые данные или неполноценный объект); дубли-переклейки
    объединены. Метка <span class="flag">⚠ проверить</span> — доходность или
    дисконт выше обычного: возможен реальный «алмаз», но чаще требует ручной
    проверки (тип/этаж/состояние/площадь).
    <br><br>
    Доходность <b>валовая</b> — без налогов, простоя, коммуналки и ремонта.
    Это инструмент отбора кандидатов, а не оценка; каждый объект проверяйте
    вручную перед сделкой.
  </div>
</div>
</body>
</html>"""


def write_report(deals: list[ScoredDeal], cfg: Config,
                 sale_count: int, rent_count: int,
                 path: str | None = None) -> str:
    out = path or cfg.report_path
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_html(deals, cfg, sale_count, rent_count))
    return out
