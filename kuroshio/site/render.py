"""`kuroshio site` — a static tree for one book directory and one report tree.

Four page types, all in the design system `docs/index.html` uses (`style.css`, shipped as
package data next to this module and asserted byte-identical to the docs copy by
tests/test_site.py, plus `site.css` for what only the generated pages need):

* `index.html`    — the book: stats, holdings, concentration + IPS, propose cards, the cuts
* `alloc.html`    — the book in money on the NAV the positions file carried
* `reports.html`  — every research report, newest first
* `reports/<TICKER>/<date>.html` — one report

Relative links only, so the tree works over `file://`, any static server, or a mount. The
build happens in a sibling `<out>.new` directory and is swapped in at the end, so a server
never sees a half-written tree. No user data is read from anywhere but the two input
directories, and nothing is written outside `out_dir`.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import shutil
from importlib import resources
from pathlib import Path

from kuroshio.site.labels import labels

GITHUB = "https://github.com/HaoweiChan/kuroshio"
RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
JS = """
<script>
function sortTable(th){
  const t = th.closest('table'), i = [...th.parentNode.children].indexOf(th);
  const asc = th.dataset.asc !== '1';
  th.parentNode.querySelectorAll('th').forEach(h => delete h.dataset.asc);
  th.dataset.asc = asc ? '1' : '0';
  const rows = [...t.tBodies[0].rows];
  rows.sort((a, b) => {
    const x = a.cells[i].dataset.v ?? a.cells[i].innerText;
    const y = b.cells[i].dataset.v ?? b.cells[i].innerText;
    const nx = parseFloat(x), ny = parseFloat(y);
    const c = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : String(x).localeCompare(String(y));
    return asc ? c : -c;
  });
  rows.forEach(r => t.tBodies[0].appendChild(r));
}
function chipFilter(btn, attr){
  const bar = btn.parentNode;
  bar.querySelectorAll('.chip').forEach(c => c.setAttribute('aria-pressed', 'false'));
  btn.setAttribute('aria-pressed', 'true');
  const v = btn.dataset.v, box = bar.closest('.panel');
  box.querySelectorAll('tbody tr').forEach(r => {
    r.classList.toggle('hide', !(v === 'all' || r.dataset[attr] === v));
  });
}
document.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => sortTable(th)));
</script>"""

REPORT_JS = """
<script>
function showTab(btn, id){
  const page = btn.closest('.report');
  page.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));
  page.querySelectorAll('.tab-body').forEach(s => s.classList.toggle('on', s.dataset.tab === id));
}
function toggleCard(btn){
  const off = btn.closest('.report-card').classList.toggle('collapsed');
  btn.querySelector('.chev').textContent = off ? '\u2192' : '\u2193';
}
</script>"""
# the report tree `kuroshio research` writes, in reading order: the coverage grid is this list
ROLES = (
    ("market", "1_analysts/market.md"),
    ("sentiment", "1_analysts/sentiment.md"),
    ("news", "1_analysts/news.md"),
    ("fundamentals", "1_analysts/fundamentals.md"),
    ("bull", "2_research/bull.md"),
    ("bear", "2_research/bear.md"),
    ("manager", "2_research/manager.md"),
    ("trader", "3_trading/trader.md"),
    ("aggressive", "4_risk/aggressive.md"),
    ("neutral", "4_risk/neutral.md"),
    ("conservative", "4_risk/conservative.md"),
    ("decision", "5_portfolio/decision.md"),
)
TONE = {"Buy": "tone-buy", "Overweight": "tone-buy", "Hold": "tone-hold",
        "Underweight": "tone-sell", "Sell": "tone-sell"}

esc = html.escape


def _css() -> str:
    files = resources.files("kuroshio.site")
    return files.joinpath("style.css").read_text() + files.joinpath("site.css").read_text()


def _markdown(text: str) -> str:
    try:
        import markdown
    except ImportError as exc:  # one optional dependency, one clear hint
        raise SystemExit(
            'error: `kuroshio site` renders markdown reports. Run: pip install "kuroshio[site]"'
        ) from exc
    return markdown.markdown(text, extensions=["tables", "fenced_code"])


def _pct(x, sign: bool = False, na: str = "n/a") -> str:
    if x is None:
        return na
    return f"{x:+.0%}" if sign else f"{x:.1%}"


def _money(x, na: str = "n/a") -> str:
    return f"{x:,.2f}" if x is not None else na


def _flag(rating: str) -> str:
    cls = rating if rating in RATINGS else "na"
    return f"<span class='flag {esc(cls)}'>{esc(rating)}</span>"


def _kv_panel(title: str, items: list[tuple[str, str]]) -> str:
    rows = "".join(f"<div class='kv'><span>{esc(k)}</span><span>{v}</span></div>" for k, v in items)
    return f"<div class='panel'><h4>{esc(title)}</h4>{rows}</div>"


def _chips(values: list[tuple[str, str]], attr: str) -> str:
    return "".join(
        f"<button class='chip tab' aria-pressed='{'true' if v == 'all' else 'false'}' "
        f"data-v='{esc(v)}' onclick=\"chipFilter(this,'{attr}')\">{esc(label)}</button>"
        for v, label in values
    )


def _section(kicker: str, title: str, lede: str, inner: str) -> str:
    return (
        f"<section><div class='sec-head'><div class='kicker'>{esc(kicker)}</div>"
        f"<h2>{esc(title)}</h2><p>{esc(lede)}</p></div>{inner}</section>"
    )


def _shell(title: str, body: str, css: str, lb: dict, depth: int = 0, active: str = "") -> str:
    up = "../" * depth
    nav = "".join(
        f"<a href='{up}{href}' class='{'on' if key == active else ''}'>{esc(lb[label])}</a>"
        for key, href, label in (
            ("book", "index.html", "book_page_title"),
            ("alloc", "alloc.html", "nav_page_title"),
            ("reports", "reports.html", "reports_page_title"),
        )
    )
    when = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{css}</style></head><body>"
        f"<header><div class='wrap'><div class='brand'>Kuro<span>shio</span></div>"
        f"<nav>{nav}<a href='{GITHUB}'>GitHub</a></nav></div></header>"
        f"<div class='wrap'>{body}</div>"
        f"<footer><div class='wrap'><p>{esc(lb['disclaimer'])}</p>"
        f"<p class='disc'>{esc(lb['generated'].format(when=when))}</p></div></footer>{JS}</body></html>"
    )


# --- reports ------------------------------------------------------------------


def _decision_meta(report_dir: Path) -> dict:
    """The PM decision fields `kuroshio research` writes, or {} when there is no decision."""
    path = report_dir / "5_portfolio" / "decision.md"
    if not path.exists():
        return {}
    text = path.read_text()

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None

    return {
        "rating": grab(r"\*\*Rating\*\*:\s*(\w+)"),
        "stop": grab(r"\*\*Stop Loss\*\*:\s*([\d.]+)"),
        "target": grab(r"\*\*Price Target\*\*:\s*([\d.]+)"),
        "market": grab(r"\*\*Market:\*\*\s*([^·\n]+)"),
        "close": grab(r"Last close:\*\*\s*\$([\d.,]+)"),
        "earnings": grab(r"Next earnings:\*\*\s*([^·\n]+)"),
        "summary": grab(r"\*\*Executive Summary\*\*:\s*(.+)"),
    }


def _collect_reports(reports_dir: Path | None) -> dict[str, list[tuple[str, dict]]]:
    """{ticker: [(date, meta), ...]} newest first, over `<reports>/<TICKER>/<date>/`."""
    found: dict[str, list[tuple[str, dict]]] = {}
    for complete in sorted((reports_dir or Path("/nonexistent")).glob("*/*/complete_report.md")):
        ticker, date = complete.parent.parent.name, complete.parent.name
        found.setdefault(ticker, []).append((date, _decision_meta(complete.parent)))
    for lst in found.values():
        lst.sort(reverse=True)
    return found


# --- pages --------------------------------------------------------------------


def _book_page(book: dict, propose: str, reports: dict, lb: dict, link) -> str:
    holdings = [dict(x, sleeve=x.get("sleeve", "core")) for x in book["core"]]
    holdings += [dict(x, sleeve="attack") for x in book["attack"]]
    alloc = book.get("alloc") or {}
    lock_w = sum(x["weight"] for x in book["locked"])
    stats = [
        (f"{alloc['nav']:,.0f}" if alloc.get("nav") else lb["na"], lb["nav"]),
        (f"{book['gross']:.1%}", lb["gross"]),
        (f"{book['cash']:.1%}", lb["cash"]),
        (str(len(holdings) + len(book["locked"])), lb["book_names"]),
        (f"{lock_w:.1%}", lb["locked_weight"]),
    ]

    rows = []
    for x in holdings:
        e, s, tg = x["entry"], x.get("stop"), x.get("target")
        stop_d = (s - e) / e if s else None
        rr = (tg - e) / (e - s) if s and tg and e > s else None
        cls = "flag hi" if x["sleeve"] == "attack" else "flag"
        rows.append(
            f"<tr data-sleeve='{esc(x['sleeve'])}'><td>{x['rank']}</td>"
            f"<td class='tk'>{link(x['ticker'])}</td>"
            f"<td><span class='{cls}'>{esc(lb[x['sleeve']])}</span></td>"
            f"<td style='text-align:left'>{esc(x['industry'] or '')}</td><td>{_flag(x['rating'])}</td>"
            f"<td class='bar' data-v='{x['weight']}'><i style='width:{x['weight'] * 600:.0f}%'></i>"
            f"<span>{x['weight']:.1%}</span></td>"
            f"<td style='text-align:left'><span class='meta'>{esc(x['cap'])}</span></td>"
            f"<td>{e:,.2f}</td><td>{s if s else lb['na']}</td>"
            f"<td class='{'neg' if stop_d else ''}'>{_pct(stop_d, True, lb['na'])}</td>"
            f"<td>{tg if tg else lb['na']}</td><td>{f'{rr:.1f}' if rr else lb['na']}</td>"
            f"<td>{_pct(x.get('mom'), True, lb['na'])}</td><td>{_pct(x.get('vol'), na=lb['na'])}</td></tr>"
        )
    for x in book["locked"]:
        rows.append(
            f"<tr data-sleeve='locked'><td>—</td><td class='tk'>{esc(x['ticker'])}</td>"
            f"<td><span class='flag wa'>{esc(lb['locked'])}</span></td>"
            f"<td style='text-align:left'>{esc(x['theme'])}</td>"
            f"<td><span class='flag na'>{esc(lb['owner'])}</span></td>"
            f"<td class='bar' data-v='{x['weight']}'><i style='width:{x['weight'] * 600:.0f}%'></i>"
            f"<span>{x['weight']:.1%}</span></td>"
            f"<td style='text-align:left'><span class='meta'>{esc(lb['locked_not_resized'])}</span></td>"
            f"<td>{_money(x['avg_cost'], lb['na'])}</td>" + f"<td>{lb['na']}</td>" * 6 + "</tr>"
        )
    heads = ["rank", "ticker", "sleeve", "industry", "rating", "weight", "cap", "entry", "stop",
             "stop_dist", "target", "rr", "mom", "vol"]
    th = "".join(f"<th data-sort>{esc(lb[h])}</th>" for h in heads)
    holdings_panel = (
        "<div class='panel'><div class='toolbar'>"
        + _chips([("all", lb["all"]), ("core", lb["core"]), ("attack", lb["attack"]),
                  ("locked", lb["locked"])], "sleeve")
        + f"<span class='spacer'></span><span class='meta'>"
        f"{esc(lb['sort_hint'].format(asof=book['asof']))}</span></div>"
        f"<div class='tablebox'><table><thead><tr>{th}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></div>"
    )

    by_sector, by_industry = _concentration(book)
    conc = _kv_panel(lb["sector"], [(k, f"{v:.1%}") for k, v in by_sector])
    conc += _kv_panel(lb["industry"], [(k, f"{v:.1%}") for k, v in by_industry])
    ips = book.get("ips") or {}
    ips_items = [
        (lb["position_cap"], f"{ips.get('position_pct', 10)}%"),
        (lb["hard_cap"], f"{ips.get('position_hard_pct', 25)}%"),
        (lb["theme_budget"], f"{ips.get('theme_pct', 20)}%"),
    ]
    ips_items += [
        (lb["theme_cap"].format(theme=k), f"{v}%") for k, v in (ips.get("theme_caps") or {}).items()
    ]
    ips_items += [
        (lb["risk_budget"], f"{ips.get('risk_budget_pct', 1)}%"),
        (lb["forced_decision"], f"{ips.get('max_adverse_excursion_pct', -15)}%"),
        (lb["turnover_hurdle"], f"{ips.get('hurdle', 0.15)}"),
        (lb["verdict_floor"], str(ips.get("verdict_floor", "neutral"))),
        (lb["max_swaps"], str(ips.get("max_swaps_per_week", 2))),
    ]
    ips_panel = _kv_panel(lb["ips_head"].format(name=ips.get("name") or "IPS"), ips_items)

    cards = []
    for block in re.split(r"^### ", propose, flags=re.M):
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        bullets = [ln[2:] for ln in rest.splitlines() if ln.startswith("- ")]
        text = " ".join(ln for ln in rest.splitlines() if ln.strip() and not ln.startswith("- "))
        cards.append(
            f"<div class='card {esc(head.split()[0])}'><div class='act'>{esc(head)}</div>"
            f"<p>{esc(text)}</p>"
            + (f"<ul>{''.join(f'<li>{esc(b)}</li>' for b in bullets)}</ul>" if bullets else "")
            + "</div>"
        )
    if not cards:
        cards = [f"<div class='card ALERT'><div class='act'>{esc(lb['no_proposals'])}</div></div>"]

    def kind(reason: str) -> str:
        if reason in ("Underweight", "Sell"):
            return "veto"
        return "unrated" if "not researched" in reason else "cut"

    skipped_rows = "".join(
        f"<tr data-kind='{kind(str(r[3]))}'><td>{r[0]}</td><td class='tk'>{link(r[1])}</td>"
        f"<td style='text-align:left'>{esc(str(r[2]))}</td>"
        f"<td style='text-align:left'><span class='meta'>{esc(str(r[3]))}</span></td></tr>"
        for r in book["skipped"]
    )
    skipped_heads = "".join(
        f"<th data-sort>{esc(lb[h])}</th>" for h in ("rank", "ticker", "industry", "rating")
    )
    skipped_panel = (
        "<div class='panel'><div class='toolbar'>"
        + _chips([("all", lb["all"]), ("veto", lb["filter_veto"]),
                  ("unrated", lb["filter_unrated"]), ("cut", lb["filter_cut"])], "kind")
        + f"<span class='spacer'></span></div><div class='tablebox'><table><thead><tr>"
        f"{skipped_heads}</tr></thead><tbody>{skipped_rows}</tbody></table></div></div>"
    )

    return (
        f"<div class='hero small'><h1>{esc(lb['book_page_title'])}</h1>"
        f"<p class='lede'>{esc(lb['book_lede'])}</p><div class='badges'>"
        f"<span class='badge on'>{esc(book['asof'])}</span>"
        f"<span class='badge'>{len(holdings) + len(book['locked'])} {esc(lb['book_names'])}</span>"
        f"<span class='badge'>{len(reports)} {esc(lb['reports_page_title'])}</span></div></div>"
        "<div class='panel'><div class='stats'>"
        + "".join(f"<div class=stat><b>{v}</b><span>{esc(label)}</span></div>" for v, label in stats)
        + "</div></div>"
        + _section(lb["step_holdings"], lb["holdings_head"], lb["holdings_lede"], holdings_panel)
        + _section(lb["step_policy"], lb["policy_head"], lb["policy_lede"],
                   f"<div class='two'><div>{conc}{ips_panel}</div>"
                   f"<div class='cards'>{''.join(cards)}</div></div>")
        + _section(lb["step_vetoes"], lb["skipped_head"], lb["skipped_lede"], skipped_panel)
    )


def _concentration(book: dict) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    by_sector: dict[str, float] = {}
    by_industry: dict[str, float] = {}
    for x in book["core"] + book["attack"]:
        by_sector[x["sector"] or "?"] = by_sector.get(x["sector"] or "?", 0) + x["weight"]
        by_industry[x["industry"]] = by_industry.get(x["industry"], 0) + x["weight"]
    for x in book["locked"]:
        key = f"{'locked'} · {x['theme']}"
        by_sector[key] = by_sector.get(key, 0) + x["weight"]
        by_industry[key] = by_industry.get(key, 0) + x["weight"]
    order = lambda d: sorted(d.items(), key=lambda kv: -kv[1])  # noqa: E731
    return order(by_sector), order(by_industry)


def _chip_list(title: str, items: list[str], lb: dict) -> str:
    chips = ("".join(f"<span class='chip'>{esc(n)}</span>" for n in items)
             or f"<span class='meta'>{esc(lb['none'])}</span>")
    return f"<h4>{esc(title)}</h4><div class='chips'>{chips}</div>"


def _alloc_page(book: dict, lb: dict, link) -> str | None:
    alloc = book.get("alloc")
    if not alloc:
        return None
    nav = alloc["nav"]
    rows = "".join(
        f"<tr><td><span class='flag {'hi' if r['sleeve'] == 'attack' else ''}'>"
        f"{esc(lb[r['sleeve']])}</span></td><td class='tk'>{link(r['ticker'])}</td>"
        f"<td class='bar' data-v='{r['weight']}'><i style='width:{r['weight'] * 600:.0f}%'></i>"
        f"<span>{r['weight']:.1%}</span></td><td>{nav * r['weight']:,.0f}</td><td>{r['shares']}</td>"
        f"<td>{r['usd']:,.0f}</td><td>{r['have']:,.0f}</td>"
        f"<td class='{'pos' if r['usd'] - r['have'] >= 0 else 'neg'}'>{r['usd'] - r['have']:+,.0f}</td></tr>"
        for r in alloc["rows"]
    )
    lock_mv = sum(x["market_value"] for x in book["locked"])
    stats = [
        (f"{nav:,.0f}", lb["nav"]),
        (f"{alloc['cash']:,.0f}" if alloc["cash"] is not None else lb["na"], lb["cash_now"]),
        (f"{alloc['invested']:,.0f}", lb["invested"]), (f"{lock_mv:,.0f}", lb["locked_weight"]),
        (f"{nav - alloc['invested'] - lock_mv:,.0f}", lb["cash_after"]),
    ]
    heads = ["sleeve", "ticker", "weight", "target_usd", "shares", "actual_usd", "held_usd", "delta_usd"]
    locked_rows = "".join(
        f"<tr><td class='tk'>{esc(x['ticker'])}</td><td style='text-align:left'>{esc(x['theme'])}</td>"
        f"<td>{x['qty']:.0f}</td><td>{x['market_value']:,.0f}</td><td>{x['weight']:.1%}</td>"
        f"<td>{_money(x['avg_cost'], lb['na'])}</td></tr>"
        for x in book["locked"]
    )
    lheads = ["symbol", "theme", "qty", "market_value", "weight", "avg_cost"]
    sells = "".join(
        f"<tr><td class='tk'>{esc(s)}</td><td style='text-align:left'>{esc(a or '')}</td>"
        f"<td>{v:,.0f}</td></tr>"
        for s, v, a in alloc["sells"]
    )
    unrated = [f"{r[0]} {r[1]}" for r in book["skipped"] if str(r[3]).startswith("not researched")]
    review = [
        f"{x['ticker']} ({x['rating_date']}, {x['age']}d)" for x in book["review"]
    ]
    rules = book["rules"]
    return (
        f"<div class='hero small'><h1>{esc(lb['nav_page_title'])}</h1>"
        f"<p class='lede'>{esc(lb['alloc_lede'].format(nav=nav, asof=book['asof']))}</p></div>"
        "<div class='panel'><div class='stats'>"
        + "".join(f"<div class=stat><b>{v}</b><span>{esc(label)}</span></div>" for v, label in stats)
        + "</div></div>"
        + _section("ALLOCATION", lb["alloc_title"].format(asof=book["asof"]), "",
                   "<div class='panel'><div class='tablebox'><table><thead><tr>"
                   + "".join(f"<th data-sort>{esc(lb[h])}</th>" for h in heads)
                   + f"</tr></thead><tbody>{rows}</tbody></table></div></div>")
        + _section("LOCKED", lb["locked_head"], lb["locked_lede"],
                   "<div class='panel'><div class='tablebox'><table><thead><tr>"
                   + "".join(f"<th>{esc(lb[h])}</th>" for h in lheads)
                   + "</tr></thead><tbody>"
                   + (locked_rows or f"<tr><td colspan=6>{esc(lb['none'])}</td></tr>")
                   + "</tbody></table></div></div>")
        + _section("DISPOSALS", lb["disposals_head"],
                   lb["disposals_lede"].format(total=sum(v for _, v, _ in alloc["sells"])),
                   "<div class='panel'><div class='tablebox'><table><thead><tr>"
                   + "".join(f"<th data-sort>{esc(lb[h])}</th>"
                             for h in ("symbol", "asset_type", "market_value"))
                   + "</tr></thead><tbody>"
                   + (sells or f"<tr><td colspan=3>{esc(lb['none'])}</td></tr>")
                   + "</tbody></table></div></div>")
        + _section("RESEARCH QUEUE", lb["queue_head"], "",
                   "<div class='panel'>"
                   + _chip_list(lb["unrated_head"], unrated, lb)
                   + _chip_list(
                       lb["review_head"].format(days=rules["review_days"],
                                                warn=rules["earnings_warn_days"]),
                       review, lb)
                   + "</div>")
    )


# --- one report page ----------------------------------------------------------


def _rr(close, stop, target) -> float | None:
    """Reward-to-risk measured from the reference close; None when a leg is missing."""
    try:
        ref = float(str(close).replace(",", ""))
        return (float(target) - ref) / (ref - float(stop))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _strip_leading_h1(text: str) -> str:
    """Drop a role file's own `# Title` line (and any blank lines right after it) — the card
    header already shows the eyebrow and role title, so the body repeating it as an h1 is
    redundant. A body with no leading `# ` line is returned unchanged."""
    lines = text.split("\n")
    if not lines or not lines[0].startswith("# "):
        return text
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return "\n".join(lines[i:])


def _is_wide(part: str) -> bool:
    """A markdown table or fenced code block runs wider than a 260px grid column."""
    return bool(re.search(r"^\s*\|.*\|\s*$", part, re.M)) or "```" in part


def _panelized(text: str) -> str:
    """The viewer's PanelizedMarkdown: two or more `## ` sections become a grid of blocks."""
    text = _strip_leading_h1(text)
    parts = [p for p in re.split(r"^(?=## )", text, flags=re.M) if p.strip()]
    if len(parts) > 1 and not parts[0].startswith("## "):
        parts[:2] = [parts[0] + parts[1]]  # a lead-in rides along with the first section
    if len(parts) > 1:
        blocks = "".join(
            f"<div class='content-block{' wide' if _is_wide(p) else ''} md'>{_markdown(p)}</div>"
            for p in parts
        )
        return f"<div class='report-body-grid'>{blocks}</div>"
    return f"<div class='report-body-single md'>{_markdown(text)}</div>"


def _report_card(eyebrow: str, title: str, body: str, tone: str = "") -> str:
    return (
        f"<div class='report-card {tone}'><div class='card-header'>"
        "<button class='card-toggle' onclick='toggleCard(this)'>"
        f"<span class='eyebrow'>{esc(eyebrow)}</span><strong>{esc(title)}</strong>"
        "<span class='chev'>↓</span></button></div>"
        f"<div class='card-body'>{body}</div></div>"
    )


def _role_card(files: dict, key: str, eyebrow: str, lb: dict, tone: str = "") -> str:
    return _report_card(eyebrow, lb[f"role_{key}"], _panelized(files[key]), tone)


def _intro(num: str, title: str, lede: str) -> str:
    return (f"<div class='section-intro'><span class='badge-num'>{esc(num)}</span>"
            f"<div><h2>{esc(title)}</h2><p>{esc(lede)}</p></div></div>")


def _empty(lb: dict) -> str:
    return ("<div class='panel empty-panel'><div class='glyph'>◇</div>"
            f"<h3>{esc(lb['empty_head'])}</h3><p>{esc(lb['empty_lede'])}</p></div>")


def _overview_tab(ticker: str, date: str, meta: dict, files: dict, held: set[str],
                  lb: dict, extra: str) -> str:
    rating = meta.get("rating") or "?"
    close, stop, target = meta.get("close"), meta.get("stop"), meta.get("target")
    rr = _rr(close, stop, target)
    summary = meta.get("summary")
    thesis = (f"<div class='md'>{_markdown(summary)}</div>" if summary
              else f"<p class='no-summary'>{esc(lb['no_summary'])}</p>")
    tiles = "".join(
        f"<div class='coverage-tile{' on' if key in files else ''}'>"
        f"<span class='idx mono'>{i:02d}</span><strong>{esc(lb[f'role_{key}'])}</strong>"
        f"<small>{esc(lb['included'] if key in files else lb['not_included'])}</small></div>"
        for i, (key, _) in enumerate(ROLES, 1)
    )
    main = (
        f"<div class='panel thesis-card'><div class='kicker'>{esc(lb['executive_thesis'])}</div>"
        f"{thesis}</div>"
        f"<div class='panel coverage-panel'><div class='kicker'>{esc(lb['coverage'])}</div>"
        f"<div class='coverage-grid'>{tiles}</div></div>"
    )
    cells = "".join(
        f"<div class='cell'><strong>{esc(value)}</strong><small>{esc(label)}</small></div>"
        for label, value in ((lb["stop"], stop or lb["na"]), (lb["target"], target or lb["na"]),
                             (lb["rr_from_close"], f"{rr:.1f}" if rr else lb["na"]))
    )
    rail = (
        f"<div class='verdict-card'><small>{esc(lb['final_posture'])}</small>"
        f"<strong class='{TONE.get(rating, '')}'>{esc(rating)}</strong>"
        f"<span class='mono'>{esc(ticker)} · {esc(date)}</span>"
        f"<span class='mono'>{esc(lb['reference_close'])}: {esc(close or lb['na'])}</span></div>"
        f"<div class='signal-strip'>{cells}</div>"
        + _kv_panel(lb["sizing_dates"], [
            (lb["next_earnings"], esc(meta.get("earnings") or lb["na"])),
            (lb["rating_date"], esc(date)),
            (lb["in_book"], "✔" if ticker in held else "—"),
        ])
        + extra
    )
    return f"<div class='overview-layout'><div>{main}</div><div>{rail}</div></div>"


def _research_tab(files: dict, lb: dict) -> str:
    keys = [k for k in ("market", "sentiment", "news", "fundamentals") if k in files]
    if not keys:
        return _empty(lb)
    cards = "".join(_role_card(files, k, f"{lb['lens']} {i:02d}", lb)
                    for i, k in enumerate(keys, 1))
    return (_intro("01", lb["analyst_lenses"], lb["lenses_lede"])
            + f"<div class='report-stack'>{cards}</div>")


def _debates_tab(files: dict, lb: dict) -> str:
    groups = ""
    for num, kicker, title, members in (
        ("01", lb["research_desk"], lb["bull_vs_bear"],
         (("bull", "tone-bull"), ("bear", "tone-bear"), ("manager", "tone-decision"))),
        ("02", lb["risk_committee"], lb["risk_postures"],
         (("aggressive", "tone-bull"), ("neutral", "tone-neutral"),
          ("conservative", "tone-bear"), ("decision", "tone-decision"))),
    ):
        cards = "".join(_role_card(files, key, f"{kicker} {i:02d}", lb, tone)
                        for i, (key, tone) in enumerate(members, 1) if key in files)
        if not cards:
            continue
        groups += (
            f"<div><div class='group-heading'><span class='badge-num sm'>{esc(num)}</span>"
            f"<div><small>{esc(kicker)}</small><h2>{esc(title)}</h2></div></div>"
            f"<div class='report-stack'>{cards}</div></div>"
        )
    return f"<div class='debate-layout'>{groups}</div>" if groups else _empty(lb)


def _decision_tab(files: dict, lb: dict) -> str:
    stages = (("manager", lb["research_plan"], ""), ("trader", lb["trader_decision"], ""),
              ("decision", lb["final_decision"], "tone-decision"))
    cards = "".join(
        _report_card(f"{lb['stage']} {i:02d}", title, _panelized(files[key]), tone)
        for i, (key, title, tone) in enumerate(stages, 1) if key in files
    )
    if not cards:
        return _empty(lb)
    return (_intro("01", lb["decision_trail"], lb["decision_lede"])
            + f"<div class='decision-layout'>{cards}</div>")


def _report_body(ticker: str, date: str, meta: dict, files: dict, complete: str,
                 held: set[str], lb: dict, extra: str) -> str:
    """The hero, the five tabs and their bodies — the whole page inside `_shell`'s wrap."""
    rating = meta.get("rating") or "?"
    kicker = " · ".join(x for x in (meta.get("market"), lb["synthesis"]) if x)
    hero = (
        f"<div class='report-hero'><div><div class='kicker'>{esc(kicker)}</div>"
        f"<h1>{esc(ticker)}</h1>"
        f"<div class='mono path'>reports/{esc(ticker)}/{esc(date)}</div></div>"
        f"<div class='hero-verdict'><small>{esc(lb['committee_rating'])}</small>"
        f"<strong class='{TONE.get(rating, '')}'>{esc(rating)}</strong>"
        f"<span class='mono'>{esc(date)}</span></div></div>"
    )
    tabs = (
        ("overview", lb["tab_overview"],
         _overview_tab(ticker, date, meta, files, held, lb, extra)),
        ("research", lb["tab_research"], _research_tab(files, lb)),
        ("debates", lb["tab_debates"], _debates_tab(files, lb)),
        ("decision", lb["tab_decision"], _decision_tab(files, lb)),
        ("raw", lb["tab_raw"],
         f"<div class='panel'><div class='md'>{_markdown(complete)}</div></div>"),
    )
    bar = "".join(
        f"<button class='tab-btn{' active' if i == 0 else ''}' "
        f"onclick=\"showTab(this,'{key}')\">{esc(label)}</button>"
        for i, (key, label, _) in enumerate(tabs)
    )
    bodies = "".join(
        f"<div class='tab-body{' on' if i == 0 else ''}' data-tab='{key}'>{inner}</div>"
        for i, (key, _, inner) in enumerate(tabs)
    )
    return f"<div class='report'>{hero}<div class='tabs'>{bar}</div>{bodies}</div>{REPORT_JS}"


def _report_pages(reports: dict, reports_dir: Path, held: set[str], lb: dict, out: Path, css: str) -> str:
    """Write one page per report and return the rows of the report index."""
    rows = []
    for ticker, dated in sorted(reports.items()):
        for date, meta in dated:
            rating = meta.get("rating") or "?"
            close, stop, target = meta.get("close"), meta.get("stop"), meta.get("target")
            report_dir = reports_dir / ticker / date
            files = {key: (report_dir / rel).read_text()
                     for key, rel in ROLES if (report_dir / rel).exists()}
            others = "".join(
                f"<div class='kv'><span>{esc(other)}</span>"
                f"<span><a href='{esc(other)}.html'>{_flag(m.get('rating') or '?')}</a></span></div>"
                for other, m in dated if other != date
            )
            extra = (f"<div class='panel'><h4>{esc(lb['other_dates'])}</h4>{others}</div>"
                     if others else "")
            body = _report_body(ticker, date, meta, files,
                                (report_dir / "complete_report.md").read_text(),
                                held, lb, extra)
            page = out / "reports" / ticker / f"{date}.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                _shell(f"{ticker} {date} — {rating}", body, css, lb, depth=2, active="reports"),
                encoding="utf-8",
            )
            rows.append(
                f"<tr data-r='{esc(rating)}'><td class='tk'>"
                f"<a href='reports/{esc(ticker)}/{esc(date)}.html'>{esc(ticker)}</a></td>"
                f"<td>{esc(date)}</td><td>{_flag(rating)}</td><td>{esc(close or '')}</td>"
                f"<td>{esc(stop or '')}</td><td>{esc(target or '')}</td>"
                f"<td>{'✔' if ticker in held else ''}</td></tr>"
            )
    return "".join(rows)


def render_site(
    book_dir: str | Path,
    reports_dir: str | Path | None,
    out_dir: str | Path,
    lang: str | None = None,
) -> list[Path]:
    """Render `book_dir` (+ an optional report tree) into `out_dir`; returns the pages written."""
    book_dir, out_dir = Path(book_dir), Path(out_dir)
    reports_dir = Path(reports_dir) if reports_dir else None
    book = json.loads((book_dir / "book.json").read_text())
    lb = labels(lang or book.get("lang"))
    css = _css()
    propose_path = book_dir / "propose.out"
    propose = propose_path.read_text().strip() if propose_path.exists() else ""

    reports = _collect_reports(reports_dir)

    def link(ticker: str, depth: int = 0) -> str:
        if ticker not in reports:
            return esc(ticker)
        href = f"{'../' * depth}reports/{esc(ticker)}/{esc(reports[ticker][0][0])}.html"
        return f"<a href='{href}'>{esc(ticker)}</a>"

    build = out_dir.with_name(out_dir.name + ".new")
    shutil.rmtree(build, ignore_errors=True)
    (build / "reports").mkdir(parents=True)

    # a failure anywhere in here must not leave `<out>.new` behind
    try:
        (build / "index.html").write_text(
            _shell(f"{lb['book_page_title']} {book['asof']}",
                   _book_page(book, propose, reports, lb, link), css, lb, active="book"),
            encoding="utf-8",
        )
        alloc_body = _alloc_page(book, lb, link)
        if alloc_body:
            (build / "alloc.html").write_text(
                _shell(f"{lb['nav_page_title']} {book['asof']}", alloc_body, css, lb, active="alloc"),
                encoding="utf-8",
            )
        held = {x["ticker"] for x in book["core"] + book["attack"] + book["locked"]}
        rows = _report_pages(reports, reports_dir, held, lb, build, css)
        heads = ("ticker", "date", "rating", "last_close", "stop", "target", "in_book")
        panel = (
            "<div class='panel'><div class='toolbar'>"
            + _chips([("all", lb["all"])] + [(r, r) for r in RATINGS], "r")
            + f"<span class='spacer'></span><span class='meta'>"
            f"{esc(lb['reports_count'].format(reports=rows.count('<tr'), names=len(reports)))}</span></div>"
            "<div class='tablebox'><table><thead><tr>"
            + "".join(f"<th data-sort>{esc(lb[h])}</th>" for h in heads)
            + f"</tr></thead><tbody>{rows}</tbody></table></div></div>"
        )
        (build / "reports.html").write_text(
            _shell(lb["reports_page_title"],
                   f"<div class='hero small'><h1>{esc(lb['reports_page_title'])}</h1>"
                   f"<p class='lede'>{esc(lb['reports_lede'])}</p></div>{panel}",
                   css, lb, active="reports"),
            encoding="utf-8",
        )

        # swap: a server or a mount never sees a half-written tree
        old = out_dir.with_name(out_dir.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        if out_dir.exists():
            out_dir.rename(old)
        build.rename(out_dir)
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(build, ignore_errors=True)  # no-op once build.rename(out_dir) succeeded
    return sorted(out_dir.rglob("*.html"))
