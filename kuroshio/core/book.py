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
  A name whose screen close is at or below its rating's `stop_loss` is dropped too: the
  thesis that rating priced is invalidated until a newer rating resets the stop. With a
  price history (`closes`) that holds for any close since the rating date, not just today's:
  a name that broke its stop and closed back above it the next day stays out until it is
  re-rated (on S&P names 2014-2026, ~2/3 of stop-outs close back above within 5 sessions,
  and re-entry timing did not change forward returns — waiting only removes the churn).
* **Weight** — `min(base, caps.position_pct, percent-risk)` where percent-risk is
  `caps.risk_budget_pct` of NAV spread over the entry-to-invalidation distance, times the PM
  size multiplier for that name.
* **Attack** — names the theme cap pushed out of the core go into an attack sleeve at twice base
  and twice the risk budget, subject to the IPS position cap and PM size multiplier,
  provided the rating is at or above `attack_floor` (default `overweight`); a name
  below the floor is skipped and the next qualifying overflow name by rank takes the slot.
  Overflow weights shrink to the remaining attack and theme budgets (skipped under 1% room).
  Whatever is left of `attack_budget_pct` (default 30%) raises the highest-ranked core names
  at or above the same `attack_floor` to twice their own weight, capped at twice base —
  so an attack name risks at most 2 x `caps.risk_budget_pct`
  of NAV, and a wide stop shrinks the weight smoothly instead of forbidding it. Unused budget stays in cash.
  Concentration by default; with a leverage map, attack rows buy 2x ETFs at unchanged
  capital weight. Exposure and loss-at-stop are then about twice what the caps charge;
  daily-reset leveraged ETFs drift from 2x over multi-day holds.
  Hysteresis (`prev_book`): a name in yesterday's attack sleeve
  keeps its slot — overflow or doubling — while it still qualifies and ranks inside
  `attack_buffer` x the slot count (2 by default: top 6 for 3 slots); newcomers only take
  free slots. Without it the sleeve changed on 14 of 16 days on rank noise; on S&P names
  2014-2026 the buffer cut attack changes ~5x for 0-2 points of annual return.
  Hold (`attack_hold_rank`, off by default): the sleeve follows the research, not the day's
  rank. A name in yesterday's sleeve stays in it for as long as its rating lives — until the
  TTL or an earnings date voids it, a stop is hit, a new rating falls below `attack_floor`, or
  its rank drops outside `attack_hold_rank` — whatever the ranking and the per-theme count do
  around it. Held names are placed first, so their attack and theme budget is not handed to
  a newcomer; rank only decides who fills a free slot. On S&P names 2015-2026 a 30-trading-day
  rating life (about the 45-day TTL) halved sleeve entries against the buffer alone at no
  cost in return or drawdown; 45 trading days cost ~3 points a year.
* **Theme budget** — every placement and every doubling spends the IPS theme budget
  (`caps.theme_caps` for a named theme, else `caps.theme_pct`), locked positions counted
  first, in rank order: a name is shrunk to the room left, or skipped under 1%. A theme is
  the owner's `themes` label for the ticker (`--themes`), else its industry.
* **Tier** (`tier_n`, off by default) — the top N core names are sized on `tier_base_pct` and
  `tier_risk_pct` instead of base and `caps.risk_budget_pct`, so the weight the caps leave
  unspent goes to the head of the ranking rather than to more names (on S&P names the top 5
  of a 15-name momentum book out-returned ranks 6-15 in every period tested). Same hysteresis
  as the attack sleeve. Every other cap still applies.
* **Gross cap** — weights never sum past 100% of NAV; the excess comes off the lowest ranks.
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
MIN_THEME_ROOM = 0.01  # less theme budget than this left -> the name is skipped, not shrunk


@dataclass(frozen=True)
class BookRules:
    """The numbers. Defaults are the owner's daily book; every one is a CLI option."""

    core_n: int = 15
    core_per_theme: int = 3
    attack_n: int = 3
    base_pct: float = 5.0
    attack_budget_pct: float = 30.0
    attack_floor: str = "overweight"
    attack_buffer: int = 2       # an incumbent attack name keeps its slot inside attack slots x this
    attack_hold_rank: int = 0    # an incumbent ranked inside this is held for its rating's life (0 = off)
    tier_n: int = 0              # the top N core names get the tier base and risk budget (0 = off)
    tier_base_pct: float = 7.5
    tier_risk_pct: float = 1.35
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


def previous_book(root: Path, asof: str) -> dict | None:
    """The newest saved book (`<root>/<date>/book.json`) dated before `asof`, for hysteresis."""
    dirs = sorted(d for d in root.iterdir() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)
                  and d.name < asof and (d / "book.json").exists()) if root.is_dir() else []
    return json.loads((dirs[-1] / "book.json").read_text()) if dirs else None


def stopped_out(history: dict | None, rating_date: str, asof: str, stop: float) -> str | None:
    """The first session after `rating_date` (through `asof`) that closed at or below `stop`,
    from a {date: close} history; None when there was none or no history was given."""
    return next((d for d, c in sorted((history or {}).items())
                 if rating_date < d <= asof and c is not None and c <= stop), None)


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
    themes: dict | None = None,
    leverage_map: dict | None = None,
    closes: dict | None = None,
    prev_book: dict | None = None,
    market: str = "us",
    ips_name: str = "",
    rules: BookRules = BookRules(),
) -> dict:
    """Everything the outputs are rendered from: core/attack/locked/skipped + the alloc."""
    meta, pm_size, locked, themes = meta or {}, pm_size or {}, locked or {}, themes or {}
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

    def target_weight(
        entry: float, stop: float | None, tier: bool = False, attack: bool = False,
    ) -> tuple[float, str]:
        # a tier name is sized on its own base and risk budget; every cap below still applies
        b, rb = (rules.tier_base_pct / 100, rules.tier_risk_pct / 100) if tier else (base, risk_budget)
        if attack:
            b, rb = 2 * base, 2 * risk_budget
        w, cap = b, f"{'attack' if attack else 'tier' if tier else 'base'} {b:.1%}".replace(".0%", "%")
        if position_pct < w:
            w, cap = position_pct, "caps.position_pct"
        if stop is not None and 0 < stop < entry:
            pr = rb * entry / (entry - stop)
            if pr < w:
                dist = (entry - stop) / entry
                w, cap = pr, f"percent-risk ({rb:.2%} NAV / {dist:.0%} stop)".replace(".00%", "%")
        return round(w, 4), cap

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

    # IPS theme budget: effective weight per theme, locked positions included, spent in rank
    # order. A theme is the owner's `themes` label for the ticker, else its industry.
    theme_used: dict[str, float] = {}

    def theme_room(theme: str) -> float:
        return ips.caps.theme_caps.get(theme, ips.caps.theme_pct) / 100 - theme_used.get(theme, 0)

    # yesterday's attack sleeve: overflow slots and doubled core names (hysteresis, see Attack)
    held_overflow = {x["ticker"] for x in (prev_book or {}).get("attack", [])}
    held_doubled = {x["ticker"] for x in (prev_book or {}).get("core", []) if x.get("sleeve") == "attack"}
    def cap_blocks_top_up(rec: dict) -> bool:
        return rec["cap"].startswith("theme budget") or "PM size" in rec["cap"]

    def top_up(rec: dict, room: float) -> float:
        """Raise a core name to twice its own weight (capped at twice base and the position
        cap) as far as `room` allows; returns the weight added."""
        new = round(min(2 * base, position_pct, 2 * rec["weight"], rec["weight"] + room), 4)
        if new <= rec["weight"]:
            return 0.0
        add = new - rec["weight"]
        theme_used[rec["budget_theme"]] += add
        rec.update(weight=new, cap=f"attack {new:.1%}".replace(".0%", "%"), sleeve="attack", topped=add)
        return add

    # hold: yesterday's sleeve goes down the walk first (the vetoes still apply) and keeps its
    # kind — an overflow name stays overflow even when a core slot opens in its theme, a
    # doubled name keeps its core slot and its top-up
    def held_rating(t: str) -> str:
        return (ratings.get(t) or {}).get("rating") or "n/a"

    pinned = {r["ticker"] for r in screen_rows
              if r["ticker"] in held_overflow | held_doubled and r["rank"] <= rules.attack_hold_rank
              and verdict_at_least(held_rating(r["ticker"]), rules.attack_floor)}
    walk_rows = ([r for r in screen_rows if r["ticker"] in pinned]
                 + [r for r in screen_rows if r["ticker"] not in pinned])

    def walk(tier: frozenset) -> tuple[list[dict], list[dict], list[tuple]]:
        """One pass down the ranking: (core, attack, skipped). `tier` names are sized on the
        tier base and risk budget; the theme budget is reset and spent again from the top."""
        theme_used.clear()
        for x in locked_recs:
            theme_used[x["theme"]] = theme_used.get(x["theme"], 0) + x["weight"]
        core: list[dict] = []
        attack: list[dict] = []
        overflow_seen = 0
        skipped: list[tuple] = []
        per_theme: dict[str, int] = {}
        for row in walk_rows:
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
            if stop is not None and entry <= stop:
                # the rating's own invalidation is breached: its thesis is dead until a new
                # rating says otherwise. Before this, target_weight read stop >= entry as "no
                # stop" and gave the name full base weight.
                skipped.append((row["rank"], t, ind, f"{rating} below its stop {stop:.2f}"))
                continue
            if stop is not None and (hit := stopped_out((closes or {}).get(t), rat["date"], asof, stop)):
                skipped.append((row["rank"], t, ind, f"{rating} stopped out {hit}; needs a new rating"))
                continue
            w, cap = target_weight(entry, stop, t in tier, t in pinned & held_overflow
                                   or per_theme.get(ind, 0) >= rules.core_per_theme)
            if pm_size.get(t, 1.0) < 1.0:
                w, cap = round(w * pm_size[t], 4), f"{cap} x {pm_size[t]:g} (PM size)"
            rec = {
                "rank": row["rank"], "ticker": t, "sector": m.get("sector"), "industry": ind,
                "rating": rating, "rating_date": rat["date"], "entry": entry, "stop": stop,
                "target": rat.get("price_target"), "weight": w, "cap": cap,
                "mom": row["factors"].get("mom_12_1_raw"), "vol": m.get("vol"),
                "final_score": row.get("final_score"),
            }
            if t in tier:
                rec["tier"] = True
            evict = None
            overflow = per_theme.get(ind, 0) >= rules.core_per_theme
            if t in pinned and (overflow or t in held_overflow):
                slot = "attack"  # held: its slot is not up for the day's ranking
            elif not overflow:
                slot = "core" if len(core) < rules.core_n else None
            elif not verdict_at_least(rating, rules.attack_floor):
                # the veto above is the core rule; the floor is an attack-only conviction gate —
                # a name below it does not take the slot, so the next overflow name by rank does.
                if len(attack) < rules.attack_n:
                    skipped.append((row["rank"], t, ind, f"below the attack floor ({rating})"))
                    continue
                slot = None
            else:
                in_buffer = overflow_seen < rules.attack_n * rules.attack_buffer
                overflow_seen += 1
                if len(attack) < rules.attack_n:
                    slot = "attack"
                elif t in held_overflow and in_buffer:
                    # hysteresis: yesterday's overflow name, still inside the buffer, takes its slot
                    # back from the lowest-ranked newcomer instead of losing it to rank noise
                    evict = next((x for x in reversed(attack) if x["ticker"] not in held_overflow), None)
                    slot = "attack" if evict else None
                else:
                    slot = None
            if slot:
                if slot == "attack":
                    attack_room = (budget - sum(x["weight"] for x in attack if x is not evict)
                                   - sum(x["topped"] for x in core if "topped" in x))
                    if attack_room < MIN_THEME_ROOM:
                        skipped.append((row["rank"], t, ind, "attack budget full"))
                        continue
                    if rec["weight"] > attack_room:
                        rec["weight"] = math.floor(attack_room * 10000 + 1e-9) / 10000
                        rec["cap"] = "attack budget"
                theme = themes.get(t) or ind
                if evict:
                    theme_used[evict["budget_theme"]] -= evict["weight"]
                room = theme_room(theme)
                if room < MIN_THEME_ROOM and evict:
                    theme_used[evict["budget_theme"]] += evict["weight"]  # no room even so: keep the newcomer
                    continue
                if evict:
                    attack.remove(evict)
                    skipped.append((evict["rank"], evict["ticker"], evict["industry"],
                                    f"{evict['rating']} attack slot kept by {t} (hysteresis)"))
                if room < MIN_THEME_ROOM:
                    cap_pct = ips.caps.theme_caps.get(theme, ips.caps.theme_pct)
                    skipped.append((row["rank"], t, ind, f"theme budget full ({theme} {cap_pct:g}%)"))
                    continue
                if rec["weight"] > room:
                    rec["weight"], rec["cap"] = round(room, 4), f"theme budget ({theme})"
                rec["budget_theme"] = theme
                if t in themes:
                    rec["ips_theme"] = theme  # the owner's vocabulary, safe to hand to propose
                theme_used[theme] = theme_used.get(theme, 0) + rec["weight"]
                if slot == "core":
                    per_theme[ind] = per_theme.get(ind, 0) + 1
                    core.append(rec)
                    if t in pinned and not cap_blocks_top_up(rec):
                        # a held name that sits in the core keeps its top-up, taken now so the
                        # attack and theme budget it needs is not spent further down the walk
                        spent = sum(x["weight"] for x in attack) + sum(x.get("topped", 0) for x in core)
                        top_up(rec, min(budget - spent, theme_room(theme)))
                else:
                    attack.append({**rec, "theme": "attack"})
            if len(core) >= rules.core_n and len(attack) >= rules.attack_n and (
                overflow_seen >= rules.attack_n * rules.attack_buffer
                or not held_overflow - {x["ticker"] for x in attack}
            ):
                break

        core.sort(key=lambda r: r["rank"])  # held names were placed first
        attack.sort(key=lambda r: r["rank"])
        seen = {x["ticker"] for x in core + attack} | {s[1] for s in skipped}
        for row in screen_rows:
            if row["ticker"] not in seen:
                rat = ratings.get(row["ticker"])
                ind = meta.get(row["ticker"], {}).get("industry") or row.get("industry") or row["ticker"]
                skipped.append((
                    row["rank"], row["ticker"], ind,
                    (rat["rating"] if rat else "not researched") + " (below cut)",
                ))

        return core, attack, skipped

    core, attack, skipped = walk(frozenset())
    if rules.tier_n:
        # Tiered sizing: the residual cash the caps leave goes to the head of the ranking, not
        # to more names. The tier is the top `tier_n` core names of a plain pass, with the same
        # hysteresis as the attack sleeve — yesterday's tier names keep it inside tier_n x
        # attack_buffer — then the walk runs again so the theme budget is spent on the new sizes.
        held_tier = {x["ticker"] for x in (prev_book or {}).get("core", []) if x.get("tier")}
        keep_t = [r["ticker"] for r in core[: rules.tier_n * rules.attack_buffer]
                  if r["ticker"] in held_tier][: rules.tier_n]
        fill_t = [r["ticker"] for r in core if r["ticker"] not in keep_t][: rules.tier_n - len(keep_t)]
        core, attack, skipped = walk(frozenset(keep_t + fill_t))

    # attack budget: the overflow names are already in it, the rest raises core names
    used = sum(x["weight"] for x in attack) + sum(x.get("topped", 0) for x in core)
    # a percent-risk name is eligible too: its doubling is 2 x its own risk-sized weight, so a
    # name whose stop sits 24% away tops up to 8.3% instead of flipping between 10% and 4.2%
    # as the price crosses the 20% line (that cliff, not rank noise, drove most daily changes)
    eligible = [r for r in core if not cap_blocks_top_up(r) and "topped" not in r
                and verdict_at_least(r["rating"], rules.attack_floor)]
    slots = max(int((budget - used) / base + 1e-9), 0)
    # hysteresis: yesterday's doubled names inside the buffer go first, the rest by rank
    keep = [r for r in eligible[: slots * rules.attack_buffer] if r["ticker"] in held_doubled]
    for rec in keep + [r for r in eligible if r not in keep]:
        if used + base > budget + 1e-9:
            break
        # doubling spends theme budget too: raise only as far as the theme has room
        used += top_up(rec, theme_room(rec["budget_theme"]))
    for rec in core:
        rec.pop("topped", None)

    # Hard cap: the book never asks for more than 100% of NAV. Loosened caps (a higher risk
    # budget, more names, the tier) could otherwise sum past it — implicit margin. The excess
    # comes off the lowest-ranked names first; locked positions are the owner's and stay.
    over = sum(x["weight"] for x in core + attack + locked_recs) - 1.0
    for rec in sorted(core + attack, key=lambda r: -r["rank"]):
        if over <= 1e-9:
            break
        cut = min(rec["weight"], over)
        rec["weight"], over = round(rec["weight"] - cut, 4), over - cut
        rec["cap"] = "gross cap 100%"
        if rec["weight"] <= 0:
            (core if rec in core else attack).remove(rec)
            skipped.append((rec["rank"], rec["ticker"], rec["industry"], f"{rec['rating']} gross cap 100%"))
    gross = sum(x["weight"] for x in core + attack + locked_recs)
    # Apply vehicles only after every capital-weight cap and hysteresis decision.
    for x in core + attack:
        if (x in attack or x.get("sleeve") == "attack") and x["ticker"] in (leverage_map or {}):
            x.update(vehicle=leverage_map[x["ticker"]], leverage=2, exposure=2 * x["weight"])

    # NAV alone is enough to size the book in money; positions only add the "held now" diff
    alloc = None
    if nav:
        held = {p["symbol"]: p for p in positions}
        rows, invested = [], 0.0
        for sleeve, lst in (("core", core), ("attack", attack)):
            for x in lst:
                vehicle = x.get("vehicle", x["ticker"])
                price = x["entry"]
                if x.get("vehicle"):
                    price = (closes or {}).get(vehicle, {}).get(asof)
                    if price is None:
                        price = next((r["factors"]["close"] for r in screen_rows
                                      if r["ticker"] == vehicle and r["date"] == asof), None)
                    if price is not None and (not math.isfinite(price) or price <= 0):
                        price = None
                shares = math.floor(nav * x["weight"] / price) if price else None
                # Without a vehicle quote, reserve target capital; no invented share count.
                usd = shares * price if shares is not None else nav * x["weight"]
                invested += usd
                rows.append({
                    "ticker": x["ticker"], "sleeve": x.get("sleeve", sleeve), "weight": x["weight"],
                    "rating": x["rating"], "entry": x["entry"], "shares": shares, "usd": round(usd),
                    "have": round(held.get(vehicle, {}).get("market_value", 0) or 0),
                    **({"vehicle": vehicle, "leverage": 2, "exposure": x["exposure"],
                        "vehicle_price": price} if x.get("vehicle") else {}),
                })
        book_tickers = {x.get("vehicle", x["ticker"]) for x in core + attack} | set(locked)
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
        **({"exposure": sum(x.get("exposure", x["weight"]) for x in core + attack + locked_recs),
            "unmapped_attack": [x["ticker"] for x in sorted(core + attack, key=lambda r: r["rank"])
                                if (x in attack or x.get("sleeve") == "attack")
                                and x["ticker"] not in leverage_map]}
           if leverage_map is not None else {}),
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
    warn = book["rules"]["earnings_warn_days"]
    for x in sorted(book["review"], key=lambda x: rank_of[x["ticker"]]):
        days = (dt.date.fromisoformat(x["earnings"]) - asof_d).days if x["earnings"] else None
        # the row carries any known print date; only one inside the warn window is the reason
        if days is not None and 0 <= days <= warn:
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
        elif " stopped out " in why:
            research.append({"ticker": ticker, "rank": rank, "reason": why.split(" ", 1)[1],
                             "rating_date": None})
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
            "ticker": x["ticker"], "weight": x["weight"],
            "theme": x.get("ips_theme") or x.get("theme", x["industry"]),
            "entry_price": round(x["entry"], 2), "entry_date": book["asof"],
            "setup_type": "pullback_add",
            "thesis": f"screen rank {x['rank']} on {book['asof']}; "
                      f"rating {x['rating']} ({x['rating_date']})",
            **({"invalidation_price": round(x["stop"], 2)} if x["stop"] else {}),
            # `leverage` already charges propose's caps; keep this handoff capital-based.
            **({"vehicle": x["vehicle"], "exposure": x["exposure"]} if x.get("vehicle") else {}),
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


def candidates_yaml(book: dict) -> str:
    """candidates.yml beside holdings.yml: every core+attack name (not locked — an
    owner-locked position is not a challenger) as a row `_candidates_from_yaml` reads,
    so the actual-portfolio `propose --candidates` pass gets the book's names as
    challengers. `final_score` is the screen row's own, on the incumbents' scale. `theme`
    only for a name the owner's `themes` map labels: the book's yfinance industries and
    the desk's holdings themes are different vocabularies."""
    import yaml

    candidates = [
        {"ticker": x["ticker"], "final_score": x["final_score"], "verdict": x["rating"],
         **({"theme": x["ips_theme"]} if x.get("ips_theme") else {})}
        for x in book["core"] + book["attack"]
    ]
    return yaml.safe_dump(candidates, sort_keys=False, allow_unicode=True)


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
        vehicle = f" (2x {rec['vehicle']})" if rec.get("vehicle") else ""
        exposure = f" ({lb['exposure']}: {rec['exposure']:.1%})" if rec.get("vehicle") else ""
        return (
            f"| {lb.get(sleeve, sleeve)} | {rec['ticker']}{vehicle} | {rec['rank']} | {rec['industry']} | "
            f"{rec['rating']} | {rec['weight']:.1%}{exposure} | {rec['cap']} | {e:,.2f} | {s if s else na} | "
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

    if "exposure" in book:
        out += [f"{lb['gross_capital']}: {book['gross']:.1%} · "
                f"{lb['exposure']}: {book['exposure']:.1%}", "", lb['rule_leverage'], ""]

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
        vehicle = f" (2x {r['vehicle']})" if r.get("vehicle") else ""
        exposure = f" ({lb['exposure']}: {r['exposure']:.1%})" if r.get("vehicle") else ""
        price = r.get("vehicle_price", r["entry"])
        close = f"{price:,.2f}" if price is not None else lb["na"]
        shares = r["shares"] if r["shares"] is not None else lb["na"]
        out.append(
            f"| {lb.get(r['sleeve'], r['sleeve'])} | {r['ticker']}{vehicle} | {r['rating']} | "
            f"{r['weight']:.1%}{exposure} | "
            f"{nav * r['weight']:,.0f} | {close} | {shares} | {r['usd']:,.0f} | "
            f"{r['have']:,.0f} | {r['usd'] - r['have']:+,.0f} |"
        )
    if any(r.get("vehicle") for r in alloc["rows"]):
        out += ["", lb["alloc_vehicle_note"], ""]
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
    if "unmapped_attack" in book:
        out += [f"### {lb['unmapped_attack_head']}", "",
                ", ".join(book["unmapped_attack"]) or lb["none"], ""]
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
    """Write the six book files into `out_dir` (created if needed); returns what was written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = [
        out / "holdings.yml", out / "candidates.yml", out / "book.json", out / "book.md",
        out / "propose.out", out / "needs_research.json",
    ]
    (out / "holdings.yml").write_text(holdings_yaml(book), encoding="utf-8")
    (out / "candidates.yml").write_text(candidates_yaml(book), encoding="utf-8")
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
