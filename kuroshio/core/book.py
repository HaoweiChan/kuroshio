"""The mechanical book: a screen ranking + research ratings + an IPS -> weights.

Pure functions over files the user already has. Nothing is read from a fixed location —
every path is an argument — and nothing is written outside the output directory the caller
names, so the whole thing runs on any user's own screen, ledger and broker export.

The rules, in the order they apply (all of them options on `BookRules`):

* **Core** — walk the screen ranking, `theme = industry`, at most `core_per_theme` names per
  theme, `core_n` names in total.
* **Veto** — a name needs the newest rating within `ttl_days` of the screen date; `Sell` /
  `Underweight` and unrated names are dropped. With a scores ledger (`scores_rows`) a rating
  also dies at the first `fundamentals.next_earnings_date` that falls after it: the print the
  rating did not see. Without one, only the day TTL applies.
* **Weight** — `min(base, caps.position_pct, percent-risk)` where percent-risk is
  `caps.risk_budget_pct` of NAV spread over the entry-to-invalidation distance, times the PM
  size multiplier for that name.
* **Attack** — names the theme cap pushed out of the core go into an attack sleeve at base
  weight, provided the rating is at or above `attack_floor` (default `overweight`); a name
  below the floor is skipped and the next qualifying overflow name by rank takes the slot.
  Whatever is left of `attack_budget_pct` raises the highest-ranked core names to twice base.
  Concentration, not leverage.
* **Locked** — positions the owner marked as not-the-book's-business ride along at their live
  weight, so `propose` sees the real concentration.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from kuroshio.core.ips import verdict_at_least
from kuroshio.site.labels import labels

VETO = {"sell", "underweight"}


@dataclass(frozen=True)
class BookRules:
    """The numbers. Defaults are the owner's daily book; every one is a CLI option."""

    core_n: int = 15
    core_per_theme: int = 3
    attack_n: int = 3
    base_pct: float = 5.0
    attack_budget_pct: float = 15.0
    attack_floor: str = "overweight"
    ttl_days: int = 45
    review_days: int = 21
    earnings_warn_days: int = 7


# --- inputs ------------------------------------------------------------------


def load_screen(path: str | Path) -> list[dict]:
    """`kuroshio screen --json` output: rows with ticker/date/rank/factors.close."""
    rows = json.loads(Path(path).read_text())
    if not rows:
        raise ValueError(f"{path}: no screen rows")
    return rows


def load_jsonl(path: str | Path | None) -> list[dict]:
    if path is None:
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def load_json(path: str | Path | None) -> dict:
    return json.loads(Path(path).read_text()) if path else {}


_POSITION_FIELDS = ("symbol", "quantity", "market_value", "average_price", "asset_type")


def load_positions(path: str | Path | None) -> list[dict]:
    """A plain `symbol,quantity,market_value,average_price[,asset_type]` table — CSV or the
    same rows as JSON — so any broker export fits after a spreadsheet save-as."""
    if path is None:
        return []
    path = Path(path)
    text = path.read_text()
    raw = json.loads(text) if path.suffix == ".json" else list(csv.DictReader(text.splitlines()))
    rows = []
    for r in raw:
        missing = [f for f in _POSITION_FIELDS[:3] if r.get(f) in (None, "")]
        if missing:
            raise ValueError(f"{path}: a position row is missing {', '.join(missing)}: {r!r}")
        rows.append({
            "symbol": str(r["symbol"]).strip(),
            "quantity": float(r["quantity"]),
            "market_value": float(r["market_value"]),
            "average_price": float(r["average_price"]) if r.get("average_price") not in (None, "") else None,
            "asset_type": (r.get("asset_type") or "").strip() or None,
        })
    return rows


# --- the rules ---------------------------------------------------------------


def build_book(
    screen_rows: list[dict],
    ratings_rows: list[dict],
    ips,
    *,
    meta: dict | None = None,
    scores_rows: list[dict] | None = None,
    positions: list[dict] | None = None,
    nav: float | None = None,
    pm_size: dict | None = None,
    locked: dict | None = None,
    market: str = "us",
    ips_name: str = "",
    rules: BookRules = BookRules(),
) -> dict:
    """Everything the outputs are rendered from: core/attack/locked/skipped + the alloc."""
    meta, pm_size, locked = meta or {}, pm_size or {}, locked or {}
    positions = positions or []
    base, budget = rules.base_pct / 100, rules.attack_budget_pct / 100
    asof = screen_rows[0]["date"]
    asof_d = dt.date.fromisoformat(asof)
    min_date = (asof_d - dt.timedelta(days=rules.ttl_days)).isoformat()

    # ratings are written after the close they judge, so there is no upper date bound
    ratings: dict[str, dict] = {}
    for r in sorted(ratings_rows, key=lambda r: r.get("date", "")):
        if r.get("market", market) == market and r.get("rating") and r.get("date", "") >= min_date:
            ratings[r["ticker"]] = r

    next_earnings: dict[str, str] = {}
    for r in scores_rows or []:
        f = r.get("fundamentals") or {}
        if r.get("market", market) == market and f.get("next_earnings_date"):
            next_earnings[r["ticker"]] = str(f["next_earnings_date"])[:10]

    def voided_by_earnings(ticker: str, rating: dict) -> str:
        """The reason this rating is void, or "" — the first print after the rating's date."""
        ne = next_earnings.get(ticker)
        if ne and rating["date"] < ne <= asof:
            return f"earnings {ne} after rating {rating['date']}"
        return ""

    position_pct = ips.caps.position_pct / 100
    risk_budget = ips.caps.risk_budget_pct / 100

    def target_weight(entry: float, stop: float | None) -> tuple[float, str]:
        w, cap = base, f"base {base:.0%}"
        if position_pct < w:
            w, cap = position_pct, "caps.position_pct"
        if stop is not None and 0 < stop < entry:
            pr = risk_budget * entry / (entry - stop)
            if pr < w:
                w, cap = pr, f"percent-risk ({risk_budget:.0%} NAV / {(entry - stop) / entry:.0%} stop)"
        return round(w, 4), cap

    core: list[dict] = []
    attack: list[dict] = []
    skipped: list[tuple] = []
    per_theme: dict[str, int] = {}
    for row in screen_rows:
        t = row["ticker"]
        m = meta.get(t, {})
        # no industry known -> the name is its own theme, so an unlabelled screen does not
        # collapse into one bucket the per-theme cap would cut at `core_per_theme` names.
        ind = m.get("industry") or row.get("industry") or t
        rat = ratings.get(t)
        rating = (rat or {}).get("rating") or "n/a"
        if rat is not None and (void := voided_by_earnings(t, rat)):
            skipped.append((row["rank"], t, ind, f"not researched (rating {rat['date']} void: {void})"))
            continue
        if rat is None or rating.lower() in VETO:
            skipped.append((row["rank"], t, ind, rating if rat else "not researched"))
            continue
        entry, stop = row["factors"]["close"], rat.get("stop_loss")
        w, cap = target_weight(entry, stop)
        if pm_size.get(t, 1.0) < 1.0:
            w, cap = round(w * pm_size[t], 4), f"{cap} x {pm_size[t]:g} (PM size)"
        rec = {
            "rank": row["rank"], "ticker": t, "sector": m.get("sector"), "industry": ind,
            "rating": rating, "rating_date": rat["date"], "entry": entry, "stop": stop,
            "target": rat.get("price_target"), "weight": w, "cap": cap,
            "mom": row["factors"].get("mom_12_1_raw"), "vol": m.get("vol"),
        }
        if per_theme.get(ind, 0) < rules.core_per_theme and len(core) < rules.core_n:
            per_theme[ind] = per_theme.get(ind, 0) + 1
            core.append(rec)
        elif len(attack) < rules.attack_n and per_theme.get(ind, 0) >= rules.core_per_theme:
            # the veto above is the core rule; the floor is an attack-only conviction gate —
            # a name below it does not take the slot, so the next overflow name by rank does.
            if verdict_at_least(rating, rules.attack_floor):
                attack.append({**rec, "theme": "attack"})
            else:
                skipped.append((row["rank"], t, ind, f"below the attack floor ({rating})"))
                continue
        if len(core) >= rules.core_n and len(attack) >= rules.attack_n:
            break

    seen = {x["ticker"] for x in core + attack} | {s[1] for s in skipped}
    for row in screen_rows:
        if row["ticker"] not in seen:
            rat = ratings.get(row["ticker"])
            ind = meta.get(row["ticker"], {}).get("industry") or row.get("industry") or row["ticker"]
            skipped.append((
                row["rank"], row["ticker"], ind,
                (rat["rating"] if rat else "not researched") + " (below cut)",
            ))

    # attack budget: the overflow names are already in it, the rest raises core names
    used = sum(x["weight"] for x in attack)
    for rec in core:
        if used + base > budget + 1e-9:
            break
        if rec["cap"].startswith("percent") or "PM size" in rec["cap"]:
            continue
        rec["weight"] = round(min(2 * base, position_pct), 4)
        rec["cap"] = f"attack {min(2 * base, position_pct):.0%}"
        rec["sleeve"] = "attack"
        used += base

    locked_recs = []
    if locked and nav:
        for p in positions:
            if p["symbol"] in locked and p["market_value"]:
                spec = locked[p["symbol"]]
                theme = spec.get("theme", "locked") if isinstance(spec, dict) else str(spec)
                note = spec.get("note", "") if isinstance(spec, dict) else ""
                price = p["market_value"] / p["quantity"] if p["quantity"] else None
                locked_recs.append({
                    "ticker": p["symbol"], "weight": round(p["market_value"] / nav, 4),
                    "market_value": p["market_value"], "qty": p["quantity"], "price": price,
                    "avg_cost": p["average_price"], "theme": theme, "note": note,
                })
    gross = sum(x["weight"] for x in core + attack + locked_recs)

    # NAV alone is enough to size the book in money; positions only add the "held now" diff
    alloc = None
    if nav:
        held = {p["symbol"]: p for p in positions}
        rows, invested = [], 0.0
        for sleeve, lst in (("core", core), ("attack", attack)):
            for x in lst:
                shares = math.floor(nav * x["weight"] / x["entry"])
                usd = shares * x["entry"]
                invested += usd
                rows.append({
                    "ticker": x["ticker"], "sleeve": x.get("sleeve", sleeve), "weight": x["weight"],
                    "rating": x["rating"], "entry": x["entry"], "shares": shares, "usd": round(usd),
                    "have": round(held.get(x["ticker"], {}).get("market_value", 0) or 0),
                })
        book_tickers = {x["ticker"] for x in core + attack} | set(locked)
        sells = [
            (p["symbol"], p["market_value"], p["asset_type"])
            for p in positions if p["symbol"] not in book_tickers
        ]
        alloc = {
            "nav": nav,
            "cash": nav - sum(p["market_value"] for p in positions) if positions else None,
            "rows": rows, "invested": invested, "sells": sorted(sells, key=lambda z: -z[1]),
        }

    review = []
    for x in core + attack:
        age = (asof_d - dt.date.fromisoformat(x["rating_date"])).days
        ne = next_earnings.get(x["ticker"])
        soon = ne and 0 <= (dt.date.fromisoformat(ne) - asof_d).days <= rules.earnings_warn_days
        if age > rules.review_days or soon:
            review.append({
                "ticker": x["ticker"], "rating_date": x["rating_date"], "age": age, "earnings": ne,
            })

    return {
        "asof": asof, "market": market, "core": core, "attack": attack, "locked": locked_recs,
        "skipped": skipped, "gross": gross, "cash": 1 - gross, "alloc": alloc, "review": review,
        "rules": vars(rules), "lang": getattr(ips, "lang", "en"), "risk_budget": risk_budget,
        # what the site's IPS panel shows, so `kuroshio site` reads the book dir and nothing else
        "ips": {
            "name": ips_name, "position_pct": ips.caps.position_pct,
            "position_hard_pct": ips.caps.position_hard_pct, "theme_pct": ips.caps.theme_pct,
            "theme_caps": dict(ips.caps.theme_caps), "risk_budget_pct": ips.caps.risk_budget_pct,
            "max_adverse_excursion_pct": ips.caps.max_adverse_excursion_pct,
            "hurdle": ips.turnover.hurdle, "verdict_floor": ips.turnover.verdict_floor,
            "max_swaps_per_week": ips.turnover.max_swaps_per_week,
        },
    }


_VOID_RE = re.compile(r"^not researched \(rating (?P<date>\S+) void: (?P<void>.+)\)$")


def needs_research(book: dict) -> dict:
    """The desk's to-research list: held names due for re-review, then unrated screen
    names by rank — `render_alloc_md`'s unrated/review blocks render from this same list,
    so the JSON and the prose cannot disagree."""
    asof_d = dt.date.fromisoformat(book["asof"])
    rank_of = {x["ticker"]: x["rank"] for x in book["core"] + book["attack"]}
    research = []
    for x in sorted(book["review"], key=lambda x: rank_of[x["ticker"]]):
        if x["earnings"]:
            days = (dt.date.fromisoformat(x["earnings"]) - asof_d).days
            reason = f"earnings in {days} days"
        else:
            reason = f"rating {x['age']} days old"
        research.append({
            "ticker": x["ticker"], "rank": rank_of[x["ticker"]], "reason": reason,
            "rating_date": x["rating_date"],
        })
    for rank, ticker, _ind, why in sorted(book["skipped"], key=lambda s: s[0]):
        if why == "not researched":
            research.append({"ticker": ticker, "rank": rank, "reason": why, "rating_date": None})
        elif m := _VOID_RE.match(why):
            research.append({
                "ticker": ticker, "rank": rank, "reason": f"rating void: {m['void']}",
                "rating_date": m["date"],
            })
        # "(below cut)" and "below the attack floor (...)" are not research gaps — excluded
    return {"asof": book["asof"], "research": research}


# --- outputs -----------------------------------------------------------------


def holdings_yaml(book: dict) -> str:
    import yaml

    holdings = [
        {
            "ticker": x["ticker"], "weight": x["weight"], "theme": x.get("theme", x["industry"]),
            "entry_price": round(x["entry"], 2), "entry_date": book["asof"],
            "setup_type": "pullback_add",
            "thesis": f"screen rank {x['rank']} on {book['asof']}; "
                      f"rating {x['rating']} ({x['rating_date']})",
            **({"invalidation_price": round(x["stop"], 2)} if x["stop"] else {}),
        }
        for x in book["core"] + book["attack"]
    ] + [
        {
            "ticker": x["ticker"], "weight": x["weight"], "theme": x["theme"],
            **({"entry_price": round(x["avg_cost"], 2)} if x["avg_cost"] else {}),
            "setup_type": "other",
            "thesis": f"owner-locked position, not resized by the book ({x['note']})",
        }
        for x in book["locked"]
    ]
    return yaml.safe_dump(holdings, sort_keys=False, allow_unicode=True)


def _pct(x, sign: bool = False, na: str = "n/a") -> str:
    if x is None:
        return na
    return f"{x:+.0%}" if sign else f"{x:.1%}"


def sleeve_weights(book: dict) -> tuple[float, float, float]:
    """(core, attack, locked) weight — attack is the overflow sleeve plus the topped-up names."""
    att = sum(x["weight"] for x in book["attack"])
    att += sum(x["weight"] for x in book["core"] if x.get("sleeve") == "attack")
    lock = sum(x["weight"] for x in book["locked"])
    return book["gross"] - att - lock, att, lock


def concentration(book: dict) -> tuple[dict[str, float], dict[str, float]]:
    by_sector: dict[str, float] = {}
    by_industry: dict[str, float] = {}
    for x in book["core"] + book["attack"]:
        by_sector[x["sector"] or "?"] = by_sector.get(x["sector"] or "?", 0) + x["weight"]
        by_industry[x["industry"]] = by_industry.get(x["industry"], 0) + x["weight"]
    for x in book["locked"]:
        key = f"locked · {x['theme']}"
        by_sector[key] = by_sector.get(key, 0) + x["weight"]
        by_industry[key] = by_industry.get(key, 0) + x["weight"]
    return by_sector, by_industry


def render_book_md(
    book: dict,
    lang: str | None = None,
    *,
    propose_text: str = "",
    ma50: dict[str, str] | None = None,
    book_vol: float | None = None,
    vol_window: int | None = None,
) -> str:
    """book.md — the rules, the holdings table, concentration, the propose cards, the cuts."""
    lb = labels(lang or book.get("lang"))
    rules = BookRules(**book["rules"])
    ma50 = ma50 or {}
    base = rules.base_pct / 100
    na = lb["na"]
    rule_attack = lb["rule_attack"].format(
        budget=rules.attack_budget_pct / 100, double=2 * base, floor=rules.attack_floor.capitalize(),
    )

    def row(rec: dict, sleeve: str) -> str:
        sleeve = rec.get("sleeve", sleeve)
        e, s, tg = rec["entry"], rec.get("stop"), rec.get("target")
        stop_d = _pct((s - e) / e, sign=True, na=na) if s else na
        rr = f"{(tg - e) / (e - s):.1f}" if s and tg and e > s else na
        return (
            f"| {lb.get(sleeve, sleeve)} | {rec['ticker']} | {rec['rank']} | {rec['industry']} | "
            f"{rec['rating']} | {rec['weight']:.1%} | {rec['cap']} | {e:,.2f} | {s if s else na} | "
            f"{stop_d} | {tg if tg else na} | {rr} | {_pct(rec['mom'], sign=True, na=na)} | "
            f"{_pct(rec['vol'], na=na)} | {ma50.get(rec['ticker'], na)} |"
        )

    heads = ["sleeve", "ticker", "rank", "industry", "rating", "weight", "cap", "entry", "stop",
             "stop_dist", "target", "rr", "mom", "vol", "vs_ma50"]
    out = [
        f"# {lb['book_title'].format(asof=book['asof'])}", "",
        f"**{lb['disclaimer']}**", "",
        f"## {lb['rules_head']}", "",
        f"1. {lb['rule_core'].format(core_n=rules.core_n, per_theme=rules.core_per_theme)}",
        f"2. {lb['rule_veto'].format(ttl=rules.ttl_days)}",
        f"3. {lb['rule_weight'].format(base=base, risk=book.get('risk_budget', 0.01))}",
        f"4. {rule_attack}",
        f"5. {lb['rule_cash']}", "",
        f"## {lb['holdings_head']}", "",
        "| " + " | ".join(lb[h] for h in heads) + " |",
        "|" + "---|" * len(heads),
    ]
    out += [row(rec, "core") for rec in book["core"]]
    out += [row(rec, "attack") for rec in book["attack"]]
    for x in book["locked"]:
        cells = [lb["locked"], x["ticker"], "—", x["theme"], lb["owner"], f"{x['weight']:.1%}",
                 lb["locked_not_resized"], f"{x['avg_cost']:,.2f}" if x["avg_cost"] else na]
        out.append("| " + " | ".join(cells + [na] * 7) + " |")
    core_w, att_w, lock_w = sleeve_weights(book)
    out += ["", lb["sleeve_totals"].format(core=core_w, attack=att_w, locked=lock_w, cash=book["cash"]), ""]

    by_sector, by_industry = concentration(book)
    out += [f"## {lb['concentration_head']}", "", f"| {lb['sector']} | {lb['weight']} |", "|---|---|"]
    out += [f"| {k} | {v:.1%} |" for k, v in sorted(by_sector.items(), key=lambda kv: -kv[1])]
    out += ["", f"| {lb['industry']} | {lb['weight']} |", "|---|---|"]
    out += [f"| {k} | {v:.1%} |" for k, v in sorted(by_industry.items(), key=lambda kv: -kv[1])]

    if book_vol is not None:
        out += ["", f"## {lb['book_vol_head']}", "",
                lb["book_vol_line"].format(window=vol_window or 20, vol=book_vol)]

    out += ["", f"## {lb['proposals_head']}", "", "```",
            propose_text.strip() or lb["no_proposals"], "```", ""]

    out += [f"## {lb['skipped_head']}", "",
            f"| {lb['rank']} | {lb['ticker']} | {lb['industry']} | {lb['rating']} |", "|---|---|---|---|"]
    out += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in book["skipped"]]

    n = len(book["core"]) + len(book["attack"])
    out += ["", f"## {lb['risks_head']}", "",
            f"- {lb['risk_factor'].format(n=n)}",
            f"- {lb['risk_stops']}",
            f"- {lb['risk_entry'].format(asof=book['asof'])}", ""]
    return "\n".join(out)


def render_alloc_md(book: dict, lang: str | None = None) -> str:
    """alloc.md — the book in money on the NAV the user passed, diffed against what is held."""
    lb = labels(lang or book.get("lang"))
    rules = BookRules(**book["rules"])
    alloc = book["alloc"]
    if not alloc:
        return ""
    nav = alloc["nav"]
    heads = ["sleeve", "ticker", "rating", "weight", "target_usd", "close", "shares",
             "actual_usd", "held_usd", "delta_usd"]
    out = [
        f"# {lb['alloc_title'].format(asof=book['asof'])}", "",
        lb["alloc_lede"].format(nav=nav, asof=book["asof"]), "",
        "| " + " | ".join(lb[h] for h in heads) + " |", "|" + "---|" * len(heads),
    ]
    for r in alloc["rows"]:
        out.append(
            f"| {lb.get(r['sleeve'], r['sleeve'])} | {r['ticker']} | {r['rating']} | {r['weight']:.1%} | "
            f"{nav * r['weight']:,.0f} | {r['entry']:,.2f} | {r['shares']} | {r['usd']:,.0f} | "
            f"{r['have']:,.0f} | {r['usd'] - r['have']:+,.0f} |"
        )
    lock_mv = sum(x["market_value"] for x in book["locked"])
    invested = alloc["invested"]
    out += ["", f"{lb['invested']} **{invested:,.0f}** ({invested / nav:.1%}) · "
                f"{lb['locked_head']} **{lock_mv:,.0f}** ({lock_mv / nav:.1%}) · "
                f"{lb['cash_after']} **{nav - invested - lock_mv:,.0f}** "
                f"({(nav - invested - lock_mv) / nav:.1%})", ""]

    if book["locked"]:
        lheads = ["symbol", "theme", "qty", "market_value", "weight", "avg_cost"]
        out += [f"## {lb['locked_head']}", "", lb["locked_lede"], "",
                "| " + " | ".join(lb[h] for h in lheads) + " |", "|" + "---|" * len(lheads)]
        out += [
            f"| {x['ticker']} | {x['theme']} | {x['qty']:.0f} | {x['market_value']:,.0f} | "
            f"{x['weight']:.1%} | {x['avg_cost']:,.2f} |" if x["avg_cost"] else
            f"| {x['ticker']} | {x['theme']} | {x['qty']:.0f} | {x['market_value']:,.0f} | "
            f"{x['weight']:.1%} | {lb['na']} |"
            for x in book["locked"]
        ]
        out.append("")

    total = sum(v for _, v, _ in alloc["sells"])
    out += [f"## {lb['disposals_head']}", "", lb["disposals_lede"].format(total=total), "",
            f"| {lb['symbol']} | {lb['asset_type']} | {lb['market_value']} |", "|---|---|---|"]
    out += [f"| {s} | {a or ''} | {v:,.0f} |" for s, v, a in alloc["sells"]] or [f"| {lb['none']} |  |  |"]

    research = needs_research(book)["research"]
    unrated = [
        f"{r['rank']} {r['ticker']}" for r in research
        if r["reason"] == "not researched" or r["reason"].startswith("rating void:")
    ]
    review = [
        f"{r['ticker']} ({r['rating_date']}, {r['reason']})" for r in research
        if r["reason"] not in ("not researched",) and not r["reason"].startswith("rating void:")
    ]
    out += ["", f"## {lb['queue_head']}", "", f"### {lb['unrated_head']}", "",
            ", ".join(unrated) or lb["none"], "",
            f"### {lb['review_head'].format(days=rules.review_days, warn=rules.earnings_warn_days)}", "",
            ", ".join(review) or lb["none"], ""]
    return "\n".join(out)


def write_book(
    book: dict,
    out_dir: str | Path,
    *,
    propose_text: str = "",
    lang: str | None = None,
    ma50: dict[str, str] | None = None,
    book_vol: float | None = None,
    vol_window: int | None = None,
) -> list[Path]:
    """Write the five book files into `out_dir` (created if needed); returns what was written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = [
        out / "holdings.yml", out / "book.json", out / "book.md", out / "propose.out",
        out / "needs_research.json",
    ]
    (out / "holdings.yml").write_text(holdings_yaml(book), encoding="utf-8")
    (out / "book.json").write_text(json.dumps(book, indent=1, default=str), encoding="utf-8")
    (out / "book.md").write_text(
        render_book_md(book, lang, propose_text=propose_text, ma50=ma50,
                       book_vol=book_vol, vol_window=vol_window),
        encoding="utf-8",
    )
    (out / "propose.out").write_text(propose_text, encoding="utf-8")
    (out / "needs_research.json").write_text(
        json.dumps(needs_research(book), indent=1, default=str), encoding="utf-8",
    )
    if book["alloc"]:
        (out / "alloc.md").write_text(render_alloc_md(book, lang), encoding="utf-8")
        written.append(out / "alloc.md")
    return written
