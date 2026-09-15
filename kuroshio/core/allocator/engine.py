"""core/allocator — challenger-vs-incumbent swap PROPOSALS.

ARCHITECTURE.md design rule #1: the engine never executes trades. Every path
through `propose()` ends in a ProposalCard (SWAP / TRIM / SCALE / DECIDE / ALERT) for a
human to act on — that's both the product position ("proposals, not a bot") and the
regulatory line (advice, not discretionary execution).

v1 logic, in order: theme-budget alerts, hard-cap trims, a book-wide vol-target SCALE,
per-setup_type thesis monitoring, the forced decision at max adverse excursion, then
challenger vs weakest-same-or-any-theme incumbent swaps (gated by verdict floor + score
hurdle, capped at max_swaps_per_week). See
docs/ARCHITECTURE.md `core/allocator`.
"""

from __future__ import annotations

from decimal import Decimal

from kuroshio.core.allocator.signals import BOOK_VOL_WINDOW, MA_TREND
from kuroshio.types import Candidate, Holding, ProposalCard

# setup_types that carry a monitoring rule. "other" (and a missing setup_type) carry
# none — see the dispatch in `propose` step 3 and `signals.monitor_inputs`.
MONITORED_SETUPS = ("value_dip", "pullback_add", "trend_add")
# setup_types whose invalidation price ratchets up behind the tape — see `propose` step
# 3a. A value_dip is not one: its level is a valuation thesis the user wrote down, not a
# distance from a high the position has not made yet.
TRAILED_SETUPS = ("trend_add", "pullback_add")

# TASK-22: every `reason` string `propose()` builds, by language — one table per
# language rather than `if lang` branches scattered through the rule logic above. Keys
# are format-string names threaded through `.format(...)`; a language's table need only
# override the English entries it translates (`_text()` merges over English, same
# fallback shape as `kuroshio/site/labels.py`'s `labels()`). The `### ` head line,
# tickers, theme names, setup_type values, IPS clause keys, dates and numbers are never
# in here — they stay in the f-strings/`.format()` calls below, verbatim in every
# language.
CARD_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "at_plain": "at {price:.2f}",
        "at_session": "at {price:.2f} ({asof} session)",
        "theme_alert": (
            "Theme '{theme}' effective exposure is {exp:.1%}, above your IPS theme "
            "budget of {cap:.1%}. Challengers tagged to this theme may only "
            "swap against incumbents in the same theme until it's back under budget."
        ),
        "tw_base_no_stop": (
            "your IPS base position cap of {position_pct:.1f}% of NAV — without "
            "an entry price and an invalidation price below it, the percent-risk cap has "
            "no distance to size against"
        ),
        "tw_risk_binds": (
            "the percent-risk cap binds: {risk_budget_pct:.2f}% of NAV risked "
            "over the {entry:.2f} entry to {invalidation:.2f} invalidation distance is "
            "tighter than your {position_pct:.1f}% base position cap"
        ),
        "tw_base_binds": (
            "your IPS base position cap of {position_pct:.1f}% of NAV, tighter than "
            "the {risk:.1%} the percent-risk cap allows"
        ),
        "trim_reason": (
            "{ticker} is {weight:.1%} of NAV, above your IPS hard cap of "
            "{hard_cap:.1%} per name. Trim it to {target:.1%} of NAV — {why}."
        ),
        "scale_reason": (
            "The book's trailing {window}-session realized volatility is "
            "{book_vol:.1f}% (annualized), above your IPS book vol target of "
            "{target:.1f}%. Scale gross exposure to {scale:.0%} (sell "
            "{inv_scale:.0%} of every position pro rata) to bring the book back "
            "to target."
        ),
        "ratchet_alert": (
            "{ticker}'s stop ratchets up to {trail:.2f}: its running high since "
            "{entry_date} is {peak:.2f}, and {mult:g}x its ATR14 "
            "of {atr:.2f} below that sits above {was_clause} Monitoring watches "
            "{trail:.2f} from here, and a ratcheted stop never "
            "moves back down — later runs read this level back from the stop ledger."
        ),
        "ratchet_was_known": "the {was:.2f} it was already watching.",
        "ratchet_was_none": "the level it had — you recorded none.",
        "setup_named": "setup_type '{setup_type}'",
        "setup_missing": "no setup_type",
        "no_price_session": "no price for this session",
        "entry_recorded": "entry price {entry_price:.2f}, now {chg:+.1%} from entry",
        "entry_missing": "entry price not recorded",
        "no_ma50": "no MA50 for its trend_add — fewer than {ma_trend} traded sessions",
        "trend_intact": (
            "its trend is intact — {at}, at or above its 50-day moving "
            "average of {ma:.2f}"
        ),
        "trend_broken": (
            "{ticker} was opened as a trend_add and the trend has broken: {at}, "
            "below its 50-day moving average of {ma:.2f} ({entry}). "
            "The setup that justified the position no longer holds."
        ),
        "trail_known": "{stop:.2f} its stop has ratcheted up to (see the ALERT above)",
        "trail_earlier": "{stop:.2f} its stop had already ratcheted up to on an earlier run",
        "trail_recorded": "{stop:.2f} you recorded as the level that ends the thesis",
        "trail_breached": (
            "{ticker} was opened as a trend_add and its trailing stop is breached: "
            "{at}, at or below the {level} ({entry}). "
            "The setup that justified the position no longer holds."
        ),
        "no_invalidation": "no invalidation_price for its {setup_type} — nothing to breach",
        "invalidation_intact": "its invalidation price of {stop:.2f} is not breached — {at}",
        "invalidation_breached": (
            "{ticker} was opened as a {setup_type} and its invalidation price is "
            "breached: {at}, at or below the {level} ({entry})."
        ),
        "thesis_broke_note": "its thesis broke this run — see the ALERT above",
        "mae_lead_recovered": (
            "{ticker} fell to {chg:+.1%} from your entry price of "
            "{entry_price:.2f} — its lowest close since {entry_date} was {worst:.2f}, "
            "and it is back {at}"
        ),
        "mae_lead_current": (
            "{ticker} is {chg:+.1%} from your entry price of "
            "{entry_price:.2f}, {at}"
        ),
        "mae_reason": (
            "{lead} — at or past your IPS max "
            "adverse excursion of {mae_pct:.1f}%. "
            "Decide: kill it, add to it per the plan you opened it with, or "
            "rewrite the thesis and record the new one. Holding it unchanged is not "
            "one of the three."
        ),
        "mae_monitor_note": " Monitoring checked {ticker} this run: it is a {setup_type} and {note}.",
        "mae_gap_no_entry": "no entry_price, so the loss from entry is not watched",
        "mae_gap_bad_entry": (
            "entry_price {entry_price} is not a price, so the loss from entry is not watched"
        ),
        "entry_date_note": "entry date is a tracking start, not a fill",
        "missing_price_alert": (
            "Price data missing for {n} of {total} positions "
            "this session — no stop, trend or loss rule was compared for: "
            "{names}. Their last ratcheted stops stay in force "
            "but were not checked today."
        ),
        "coverage_summary": "{n} position(s) are not fully monitored.",
        "coverage_unmonitored": (
            "Nothing is watching {names}: the thesis rule dispatches "
            "on setup_type and the loss-from-entry rule needs an entry price, and a "
            "position missing what a rule reads gets no check from it — this run says "
            "nothing about those either way."
        ),
        "coverage_partial": (
            "Partly watched: one of the two rules ran on each of these this session "
            "and the other could not — {names}."
        ),
        "rating_stop_missing": "not recorded",
        "rating_source_missing": "unrecorded source",
        "rating_model_missing": "unrecorded model",
        "rating_decide": (
            "{ticker}'s newest rating is {rating} ({date}, "
            "{src}/{model}): decide — kill it, rewrite the thesis, or hold with a "
            "written reason. The report's stop was {stop}."
        ),
        "no_score_alert": (
            "No current holding has a screener score, so no incumbent can be "
            "objectively ranked weakest — run the screener before evaluating swaps."
        ),
        "pool_own": "your own files",
        "pool_universe": "the universe in {file}",
        "swap_main": (
            "Challenger {challenger} scores {c_score:.3f} vs incumbent "
            "{incumbent}'s {i_score:.3f} — a gap of {gap:.3f}, above "
            "your IPS turnover hurdle of {hurdle:.3f} plus estimated "
            "round-trip friction of {friction:.3f}%. {challenger}'s verdict is "
            "'{verdict}', at or above your floor of '{floor}'."
        ),
        "swap_sizing": (
            " Sizing is {incumbent}'s: its target weight is {target:.1%} of "
            "NAV — {why}. {challenger} has no entry or invalidation price on file, so "
            "nothing here sizes the buy — record them and it gets the same caps."
        ),
        "swap_bridge": " Monitoring checked {incumbent} this run: it is a {setup_type} and {note}.",
        "swap_decided_addendum": (
            " {incumbent} is also {loss} from its "
            "entry price and has a DECIDE card above: this SWAP is the 'kill it' "
            "option on that card, not a fourth one."
        ),
        "disclosure_both": (
            " Auto-filled score(s): {names} — a percentile rank among "
            "the {n} names in {pool}, so this gap is a "
            "rank distance within that pool, not a difference in screener scores."
        ),
        "disclosure_one": (
            " Auto-filled score(s): {auto} — a percentile rank among the "
            "{n} names in {pool}. {hand}'s score is "
            "hand-typed and not on that scale, so this gap subtracts two different "
            "scales: it is not a rank distance, and {hand}'s own rank in that pool "
            "would give a different number."
        ),
        "suppressed_alert": (
            "{n} additional swap(s) cleared the hurdle but were suppressed "
            "by your IPS turnover limit of {limit} swaps/week "
            "({made} already made this week)."
        ),
    },
    "zh": {
        "at_plain": "現價 {price:.2f}",
        "at_session": "現價 {price:.2f}（{asof} 交易日）",
        "theme_alert": (
            "「{theme}」主題的有效曝險是 {exp:.1%}，超過你 IPS 的主題預算 {cap:.1%}。"
            "曝險回到預算內之前，掛在這個主題的候選標的只能跟同主題的持股換倉。"
        ),
        # pr46 R1: picked whenever the (entry, invalidation-below-entry) PAIR is
        # incomplete — entry is None OR invalidation is None OR invalidation >= entry —
        # not only when entry itself is missing. "沒有一組進場價與低於進場價的失效價"
        # negates the pair as a unit ("no [entry + invalidation-below-entry] pair"),
        # never independently asserting the entry price is the one that's absent — the
        # same genericness as the English "without an entry price and an invalidation
        # price below it".
        "tw_base_no_stop": (
            "你 IPS 的基礎單一部位上限 {position_pct:.1f}%（佔 NAV）— 沒有一組進場價"
            "與低於進場價的失效價可以拿來算距離，風險比例上限沒有距離可以計算"
        ),
        "tw_risk_binds": (
            "風險比例上限生效：以 {entry:.2f} 進場到 {invalidation:.2f} 失效價的距離"
            "承擔 {risk_budget_pct:.2f}% NAV 的風險，比你 {position_pct:.1f}% 的"
            "基礎單一部位上限更緊"
        ),
        "tw_base_binds": (
            "你 IPS 的基礎單一部位上限 {position_pct:.1f}%（佔 NAV），"
            "比風險比例上限允許的 {risk:.1%} 更緊"
        ),
        "trim_reason": (
            "{ticker} 目前佔 NAV 的 {weight:.1%}，超過你 IPS 單一部位硬上限 "
            "{hard_cap:.1%}。減碼到 NAV 的 {target:.1%} — {why}。"
        ),
        "scale_reason": (
            "整個組合近 {window} 個交易日的已實現波動是 {book_vol:.1f}%（年化），"
            "超過你 IPS 的組合波動目標 {target:.1f}%。把總曝險縮到 {scale:.0%}"
            "（每個部位依比例賣出 {inv_scale:.0%}）讓組合回到目標。"
        ),
        "ratchet_alert": (
            "{ticker} 的停損上調到 {trail:.2f}：自 {entry_date} 以來的最高價是 "
            "{peak:.2f}，扣掉 {mult:g} 倍 ATR14（{atr:.2f}）之後高於{was_clause}"
            "目前起監控 {trail:.2f}，停損只會往上調，不會往下調 — 之後的檢查會從"
            "停損帳本讀回這個水位。"
        ),
        "ratchet_was_known": "原本在看的 {was:.2f}。",
        "ratchet_was_none": "原本記錄的水位 — 你沒有記過。",
        "setup_named": "進場型態為「{setup_type}」",
        "setup_missing": "沒有進場型態",
        "no_price_session": "這個交易日沒有價格",
        "entry_recorded": "進場價 {entry_price:.2f}，目前距進場 {chg:+.1%}",
        "entry_missing": "沒有記錄進場價",
        "no_ma50": "這檔趨勢加碼沒有 MA50 — 交易日數不到 {ma_trend} 天",
        "trend_intact": "趨勢仍然成立 — {at}，現價在 50 日均線 {ma:.2f} 之上或持平",
        "trend_broken": (
            "{ticker} 當初以趨勢加碼進場，趨勢已經走壞：{at}，低於 50 日均線 "
            "{ma:.2f}（{entry}）。當初進場的理由已經不成立。"
        ),
        "trail_known": "{stop:.2f}（這次檢查剛把停損上調到這裡，見上方警示）",
        "trail_earlier": "{stop:.2f}（之前的檢查已經把停損上調到這裡）",
        "trail_recorded": "{stop:.2f}（你記錄的、會讓投資論點失效的水位）",
        "trail_breached": (
            "{ticker} 當初以趨勢加碼進場，移動停損已經跌破：{at}，跌到或跌破 "
            "{level}（{entry}）。當初進場的理由已經不成立。"
        ),
        "no_invalidation": "這檔 {setup_type} 沒有失效價 — 無從判斷是否跌破",
        "invalidation_intact": "失效價 {stop:.2f} 尚未跌破 — {at}",
        "invalidation_breached": (
            "{ticker} 當初以 {setup_type} 進場，失效價已經跌破：{at}，跌到或跌破 "
            "{level}（{entry}）。"
        ),
        "thesis_broke_note": "這次檢查判定投資論點已經失效 — 見上方警示",
        "mae_lead_recovered": (
            "{ticker} 曾經跌到距進場價 {entry_price:.2f} 的 {chg:+.1%} — 自 "
            "{entry_date} 以來最低收在 {worst:.2f}，目前已經回到{at}"
        ),
        "mae_lead_current": "{ticker} 距進場價 {entry_price:.2f} 為 {chg:+.1%}，{at}",
        "mae_reason": (
            "{lead} — 已經到達或超過你 IPS 的最大不利偏移 (MAE) {mae_pct:.1f}%。"
            "該做決定了：出清、依照當初計畫加碼，或重寫投資論點並記錄下來。"
            "維持不動不是這三個選項之一。"
        ),
        "mae_monitor_note": " 這次檢查了 {ticker}：它是 {setup_type}，{note}。",
        "mae_gap_no_entry": "沒有進場價，所以不追蹤從進場以來的虧損",
        "mae_gap_bad_entry": "進場價 {entry_price} 不是一個價格，所以不追蹤從進場以來的虧損",
        "entry_date_note": "進場日期只是追蹤起點，不是成交",
        "missing_price_alert": (
            "這個交易日有 {n}/{total} 個部位缺價 — 沒有比對停損、趨勢或虧損規則："
            "{names}。它們上次調整的停損仍然有效，只是今天沒有檢查。"
        ),
        "coverage_summary": "有 {n} 個部位沒有被完整監控。",
        "coverage_unmonitored": (
            "沒有任何規則在看 {names}：投資論點規則靠進場型態派工，虧損規則"
            "需要進場價，缺少規則要讀的東西就不會被檢查 — 這次檢查對它們沒有任何結論。"
        ),
        "coverage_partial": (
            "部分監控：這幾檔這次檢查有一條規則能跑、另一條不能 — {names}。"
        ),
        "rating_stop_missing": "沒有記錄",
        "rating_source_missing": "來源未記錄",
        "rating_model_missing": "模型未記錄",
        "rating_decide": (
            "{ticker} 最新評級是 {rating}（{date}，{src}/{model}）：該做決定了 — "
            "出清、重寫投資論點，或寫下理由後續抱。報告裡的停損是 {stop}。"
        ),
        "no_score_alert": (
            "目前沒有任何持股有篩選分數，無法客觀排出最弱的持股 — 先跑篩選，再評估換倉。"
        ),
        "pool_own": "你自己的檔案",
        "pool_universe": "{file} 這份股池名單",
        "swap_main": (
            "候選 {challenger} 分數 {c_score:.3f}，對比持股 {incumbent} 的 "
            "{i_score:.3f} — 差距 {gap:.3f}，超過你 IPS 的換倉門檻 {hurdle:.3f} "
            "加上預估來回摩擦成本 {friction:.3f}%。{challenger} 的評級是 "
            "'{verdict}'，達到或高於你的下限 '{floor}'。"
        ),
        "swap_sizing": (
            " 倉位大小照 {incumbent} 算：目標權重是 NAV 的 {target:.1%} — {why}。"
            "{challenger} 沒有記錄進場價或失效價，這裡沒有東西能拿來算買進的倉位 — "
            "補上之後就會套用同樣的上限。"
        ),
        "swap_bridge": " 這次檢查了 {incumbent}：它是 {setup_type}，{note}。",
        "swap_decided_addendum": (
            " {incumbent} 距進場價也已經 {loss}，上面有一張決策卡：這張換倉"
            "是那張卡的「出清」選項，不是第四個選項。"
        ),
        "disclosure_both": (
            " 自動帶入的分數：{names} — 是在{pool}的 {n} 檔裡的百分位排名，"
            "所以這個差距是同一個池子裡的排名距離，不是篩選分數本身的差異。"
        ),
        "disclosure_one": (
            " 自動帶入的分數：{auto} — 是在{pool}的 {n} 檔裡的百分位排名。"
            "{hand} 的分數是手動輸入，不在同一個量尺上，所以這個差距是兩個不同量尺"
            "相減：不是排名距離，{hand} 在同一個池子裡的排名會給出不同的數字。"
        ),
        "suppressed_alert": (
            "還有 {n} 筆換倉過了門檻，但被你 IPS 的換倉上限擋下來：每週最多 "
            "{limit} 筆（這週已經換了 {made} 筆）。"
        ),
    },
}


def _resolve_lang(lang: str | None, ips) -> str:
    """`zh`, `zh-TW`, `zh_TW` (any case) -> Chinese; anything else, including an
    explicit `en`, an unknown value, or nothing at all (falls back to `ips.lang`,
    itself IPS-schema-defaulted to `en`) -> English. Mirrors the normalize-then-fall-
    back shape of `kuroshio/site/labels.py`'s `labels()`."""
    effective = lang if lang is not None else getattr(ips, "lang", None)
    effective = (effective or "en").lower().replace("_", "-")
    return "zh" if effective.split("-")[0] == "zh" else "en"


def _text(lang_key: str) -> dict[str, str]:
    """The template table for `lang_key`, English-backed like `labels()`: a key a
    translation has not filled in yet falls through to English rather than KeyError."""
    return {**CARD_TEXT["en"], **CARD_TEXT.get(lang_key, {})}


# TASK-23: setup_type and rating/verdict values are data interpolated into a reason
# string, not template text — CARD_TEXT above only covers the words around them. Same
# fallback shape as `_text()`: a value this table doesn't know renders as itself, so an
# unrecognized setup_type or rating never disappears or KeyErrors.
SETUP_NAMES: dict[str, dict[str, str]] = {
    "zh": {
        "trend_add": "趨勢加碼",
        "pullback_add": "回檔加碼",
        "value_dip": "價值低接",
        "other": "其他",
    },
}
# ips/schema.py's VERDICT_ORDER plus "hold" (the LLM agents' name for "neutral", see
# `_rank`) — `verdict_at_least` compares case-insensitively, so this table does too.
RATING_NAMES: dict[str, dict[str, str]] = {
    "zh": {
        "buy": "買進",
        "overweight": "增持",
        "hold": "中立",
        "neutral": "中立",
        "underweight": "減持",
        "sell": "賣出",
    },
}


def _setup_name(setup_type: str | None, lang_key: str) -> str | None:
    """`setup_type` rendered in `lang_key`, or itself when there's no entry for it (an
    unknown setup_type, or `lang_key == "en"`)."""
    if setup_type is None:
        return setup_type
    return SETUP_NAMES.get(lang_key, {}).get(setup_type, setup_type)


def _rating_name(value: str | None, lang_key: str) -> str | None:
    """`value` (a rating or verdict) rendered in `lang_key`, case-insensitively, or
    itself when there's no entry for it."""
    if value is None:
        return value
    return RATING_NAMES.get(lang_key, {}).get(value.lower(), value)


def _price_phrase(price: float, asof: str | None, T: dict[str, str] | None = None) -> str:
    """How the card names the last print: the price and the session label it came from,
    and no claim about whether that session is open or closed. The panel's final row is
    a *close* only once the session is over, and nothing here knows that — it takes the
    market's close time in the market's own timezone, which no profile encodes. The
    local machine clock is not a substitute: 01:00 Taipei with `--market us` is
    mid-NYSE-session under *yesterday's* local date, and 21:00 Taipei with `--market tw`
    is 7.5h past the close under today's. So the card says neither, and the number is
    reported against the session it was read from."""
    T = T or _text("en")
    if asof is None:
        return T["at_plain"].format(price=price)
    return T["at_session"].format(price=price, asof=asof)


def _entry_price(h) -> float | None:
    """The holding's entry price, or None when there isn't a usable one.

    One gate for both rules that read it: 0.0 and negatives are not prices — the
    loss-from-entry rule would divide by one and the reason string would report a move
    from a number the user never paid (tasks/TODO.md T43)."""
    return h.entry_price if h.entry_price and h.entry_price > 0 else None


def _past_threshold(price: float, entry_price: float, mae_pct: float) -> bool:
    """Is `price` at or past `mae_pct` from `entry_price`?

    Exact decimal arithmetic, and no rounding of any operand. The binary product is not
    the level — `6.60 * 0.85` is 5.609999999999999, which holds a position sitting exactly
    on the user's own threshold — and snapping that level to the cent grid trades the miss
    for the opposite error: `propose` is handed the panel's float64 closes, not prices a
    market printed (`allocator/signals.py`, and `providers/yf.py` fetches with
    auto_adjust=True), so any price between two cents is misjudged in whichever direction
    the level was snapped.

    `Decimal(str(x))` on all three, never `Decimal(x)`: str gives the shortest decimal that
    round-trips the float, i.e. the number as written and as printed, while the binary
    expansion of 6.6 is 6.5999999999999996447... and reintroduces the artifact above.
    """
    return Decimal(str(price)) <= Decimal(str(entry_price)) * (1 + Decimal(str(mae_pct)) / 100)


def swap_hurdle(ips, market: str) -> tuple[float, float, str]:
    """The bar a swap's score gap must clear, in score space: the IPS turnover hurdle
    plus round-trip friction. friction_pct is a percentage (0.585 == 0.585%) while the
    hurdle and the gap live in score space (0..1), so /100 converts it to the
    score-equivalent ARCHITECTURE.md asks for. Returns (bar, friction_pct, ips field).

    cli.py's auto-fill guard keys off the same number — a percentile pool too coarse to
    ever produce a gap under this bar cannot be ranked honestly — so the friction math
    stays in one place."""
    field = "tw_roundtrip_pct" if market.lower() == "tw" else "us_roundtrip_pct"
    friction_pct = getattr(ips.friction, field)
    return ips.turnover.hurdle + friction_pct / 100, friction_pct, field


def target_weight(ips, h, T: dict[str, str] | None = None) -> tuple[float, str, str]:
    """The size policy allows one position: the weight as a fraction of NAV, the IPS
    clause that set it, and why in words for the card to quote.

    Two caps, and the smaller binds. (a) `caps.position_pct`, the flat base every
    position starts from. (b) percent-risk: `caps.risk_budget_pct` of NAV risked over the
    distance from the entry price to the invalidation price the user recorded. Shares are
    risk x NAV / (entry - invalidation), so the weight is risk x entry / (entry -
    invalidation) — NAV cancels, which is why `propose` needs no portfolio value to size
    anything. (c), inverse-vol parity, is not here: it needs a vol estimate and `propose`
    takes no panel (docs/PORTFOLIO-PLAN.md phase 3).

    An invalidation at or above the entry price is not a stop, and is treated as absent
    rather than sized on: its distance is zero or negative, which would divide by zero or
    cap the position at a negative weight.

    `position_hard_pct` is deliberately not in the min. `validate` holds `position_pct` at
    or under it, so it could only bind on an IPS that was never validated — and the hard
    cap is the ceiling the TRIM card is already about, not a sizing input.
    """
    T = T or _text("en")
    base = ips.caps.position_pct / 100
    entry, invalidation = _entry_price(h), h.invalidation_price
    if entry is None or invalidation is None or invalidation >= entry:
        return base, "caps.position_pct", T["tw_base_no_stop"].format(
            position_pct=ips.caps.position_pct,
        )
    risk = ips.caps.risk_budget_pct / 100 * entry / (entry - invalidation)
    if risk < base:
        return risk, "caps.risk_budget_pct", T["tw_risk_binds"].format(
            risk_budget_pct=ips.caps.risk_budget_pct, entry=entry, invalidation=invalidation,
            position_pct=ips.caps.position_pct,
        )
    return base, "caps.position_pct", T["tw_base_binds"].format(
        position_pct=ips.caps.position_pct, risk=risk,
    )


def propose(
    holdings: list[Holding],
    challengers: list[Candidate],
    ips,
    market: str,
    verdicts: dict[str, str] | None = None,
    swaps_this_week: int = 0,
    themes: dict[str, str] | None = None,
    auto_scored: dict[str, int] | None = None,
    prices: dict[str, float] | None = None,
    ma50: dict[str, float] | None = None,
    asof: str | None = None,
    pool_source: str | None = None,
    book_vol: float | None = None,
    *,
    running_high: dict[str, float] | None = None,
    atr14: dict[str, float] | None = None,
    min_close: dict[str, float] | None = None,
    last_stop: dict[str, float] | None = None,
    ratings_held: dict[str, dict] | None = None,
    lang: str | None = None,
) -> list[ProposalCard]:
    # lazy: kuroshio.core.ips is a sibling module developed in parallel — importing
    # here (not at module load) keeps this package importable regardless of ordering.
    from kuroshio.core.ips.schema import verdict_at_least

    # TASK-22: None -> ips.lang (IPS-schema-defaulted to "en"); zh/zh-TW/zh_TW -> "zh";
    # anything else, including an explicit "en" or an unknown value, -> "en" byte-for-
    # byte with what this function has always printed. T is every reason-building
    # f-string below, now a `.format()` template looked up in one place per language.
    lang_key = _resolve_lang(lang, ips)
    T = _text(lang_key)
    # the auto-filled-score disclosure's pool phrase (step 4): `pool_source` is the
    # universe file's basename, or None for "your own files" — never a pre-rendered
    # English phrase, so it can render in either language (cli.py used to build the
    # whole phrase; it now passes just the name).
    pool_name = T["pool_own"] if pool_source is None else T["pool_universe"].format(file=pool_source)

    verdicts = verdicts or {}
    themes = themes or {}
    # ticker -> size of the pctrank pool its score was auto-filled from. pctrank pins
    # its extremes to 0.000/1.000 however tightly the factors cluster, so such a gap is
    # a rank distance inside the user's own files, not a `kuroshio screen` difference —
    # the card says so rather than printing the number bare (see cli.py:_score_missing).
    auto_scored = auto_scored or {}
    # last close and 50-day mean close per ticker, computed by the caller from a panel
    # (allocator.signals.monitor_inputs) — core/allocator takes no panel and no provider.
    # None means no panel was fetched this run (cli.py's need_scores/monitored/
    # vol_targeted gate decided nothing needed one) — no price monitoring was even
    # attempted, so a missing key here is not a gap. A dict (possibly empty) means a
    # panel WAS fetched, so a holding absent from it really did go unpriced. Capture
    # that distinction before collapsing both to a dict below.
    prices_attempted = prices is not None
    prices = prices or {}
    ma50 = ma50 or {}
    # the same seam, for the stop ratchet and the max-adverse-excursion rule: running high
    # and minimum close since each holding's entry_date, and ATR14, from
    # allocator.signals.trail_inputs. Empty = those rules degrade to what they did before
    # TASK-11 (the recorded level, and this session's price).
    running_high = running_high or {}
    atr14 = atr14 or {}
    min_close = min_close or {}
    # the newest stop an earlier run's ratchet logged per ticker (cli reads it back from
    # ledger.STOPS — core/allocator imports no ledger, same rule as the panel). Empty =
    # the ratchet only knows the recorded level, which is a run with no history yet.
    last_stop = last_stop or {}
    # the newest ledger rating per held ticker (cli.py's `_held_ratings`, from
    # ledger.RATINGS, market-matched and already dropped when a later earnings print
    # voided it — core/allocator imports no ledger, same rule as the panel and the stop
    # ledger). Read only in step 3d: a Sell/Underweight rating here is a veto that
    # forces a DECIDE, never a ranking input, so step 4's swap hurdle never reads it.
    # Empty = no rating ledger has anything for a held ticker this run.
    ratings_held = ratings_held or {}
    # `asof` is the session `prices` was read from (signals.monitor_inputs), so a card can
    # name it instead of calling a still-forming bar a close — see _price_phrase.
    theme_cap = ips.caps.theme_pct / 100
    hard_cap = ips.caps.position_hard_pct / 100
    exempt = {(e.ticker, e.cap) for e in ips.caps.exemptions}
    theme_pct_exempt = {e.ticker for e in ips.caps.exemptions if e.cap == "theme_pct"}

    alerts: list[ProposalCard] = []
    trims: list[ProposalCard] = []

    # 1. theme budgets — effective exposure = weight x leverage, summed per theme.
    # Fix 4: a `theme_pct` exemption (e.g. RULES AM4d's 群創/面板 carve-out) removes
    # that ticker's exposure from its theme's total, same as the hard-cap TRIM step
    # already does for `position_hard_pct` exemptions below.
    exposures: dict[str, float] = {}
    for h in holdings:
        if h.theme is None or h.ticker in theme_pct_exempt:
            continue
        exposures[h.theme] = exposures.get(h.theme, 0.0) + h.weight * h.leverage
    # a theme named in caps.theme_caps lives under its own budget; the rest under theme_pct
    def cap_for(theme: str) -> tuple[float, str]:
        if theme in ips.caps.theme_caps:
            return ips.caps.theme_caps[theme] / 100, f"caps.theme_caps.{theme}"
        return theme_cap, "caps.theme_pct"
    breached = {t for t, exp in exposures.items() if exp > cap_for(t)[0]}
    for theme in sorted(breached):
        exp = exposures[theme]
        cap, clause = cap_for(theme)
        alerts.append(ProposalCard(
            action="ALERT",
            reason=T["theme_alert"].format(theme=theme, exp=exp, cap=cap),
            ips_clauses=[clause],
            details={"theme": theme, "exposure": exp, "cap": cap},
        ))

    # 2. hard-cap breaches -> TRIM, unless explicitly exempted.
    for h in holdings:
        if h.weight <= hard_cap or (h.ticker, "position_hard_pct") in exempt:
            continue
        # "back under the ceiling" is not a number: the hard cap says where the position
        # stops being allowed, and target_weight says where policy wanted it in the first
        # place, which is the one the user can act on.
        target, cap_clause, why = target_weight(ips, h, T)
        trims.append(ProposalCard(
            action="TRIM",
            sell=h.ticker,
            reason=T["trim_reason"].format(
                ticker=h.ticker, weight=h.weight, hard_cap=hard_cap, target=target, why=why,
            ),
            ips_clauses=["caps.position_hard_pct", cap_clause],
            details={
                "weight": h.weight, "cap": hard_cap,
                "target_weight": target, "binding_cap": cap_clause,
            },
        ))

    # 2b. book vol target — one book-wide SCALE, never a card that levers up (scale is
    # clamped to at most 1.0 by signals.book_vol/simulate's own arithmetic, but the target
    # check below (book_vol > target) already means this branch only ever cuts).
    scale_cards: list[ProposalCard] = []
    target = ips.caps.book_vol_target_pct
    if target is not None and book_vol is not None and book_vol > target:
        scale = target / book_vol
        scale_cards.append(ProposalCard(
            action="SCALE",
            reason=T["scale_reason"].format(
                window=BOOK_VOL_WINDOW, book_vol=book_vol, target=target,
                scale=scale, inv_scale=1 - scale,
            ),
            ips_clauses=["caps.book_vol_target_pct"],
            details={
                "book_vol_pct": book_vol, "target_pct": target,
                "window": BOOK_VOL_WINDOW, "scale": scale,
            },
        ))

    # 3. thesis monitoring — dispatch on setup_type. A value_dip is *supposed* to look
    # weak against its moving averages: that is the setup, not a broken thesis, so only
    # the invalidation_price the user recorded ends it. A trend_add is the opposite —
    # the trend is the thesis, so a close under the 50-day mean is the exit signal.
    #
    # 3a. the stop ratchet (TASK-11), run before the dispatch that reads the level it
    # sets. A trend_add trails always — the trend is the thesis, so the tape draws the
    # only level it ever had. A pullback_add trails only once the running high has cleared
    # entry + 2R: before that the position is still inside the pullback it was bought in,
    # and a trail there stops it out on the setup itself. The level never moves down,
    # which is what makes this a ratchet and not a recomputation.
    # "Never down" is a claim across runs, so the level a run has to beat is the higher of
    # what the user recorded and what an earlier run already ratcheted to (`last_stop`,
    # read back from the stop ledger by the caller). Comparing only against the recorded
    # level let a widening ATR14 under an unchanged high walk the stop back down.
    live_stop: dict[str, float] = {}   # ticker -> the invalidation price this run watches
    for h in holdings:
        levels = [x for x in (h.invalidation_price, last_stop.get(h.ticker)) if x is not None]
        if levels:
            live_stop[h.ticker] = max(levels)
    moved: set[str] = set()   # tickers this run's ratchet actually raised
    for h in holdings:
        if h.setup_type not in TRAILED_SETUPS:
            continue
        # TASK-20: running_high/atr14 can outlive a session with no price for this
        # ticker (they are read off the panel's whole lookback, not just today's row) —
        # without this check a rate-limit gap would still ratchet the stop on a stale
        # high, contradicting the missing-price ALERT's own "stops stay in force".
        if prices.get(h.ticker) is None:
            continue
        peak, atr = running_high.get(h.ticker), atr14.get(h.ticker)
        if peak is None or atr is None:
            # no entry_date to measure a running high from, or a panel with no high/low
            # and so no true range: nothing to trail from, and the recorded level stands.
            continue
        was, entry_price = live_stop.get(h.ticker), _entry_price(h)
        if h.setup_type == "pullback_add":
            # R is the entry-to-invalidation distance, so without both there is no 2R gate
            # to clear and the pullback keeps the level the user recorded.
            recorded = h.invalidation_price
            if entry_price is None or recorded is None or recorded >= entry_price:
                continue
            if peak < entry_price + 2 * (entry_price - recorded):
                continue
        trail = peak - ips.caps.trail_atr_mult * atr
        if was is not None and trail <= was:
            continue
        live_stop[h.ticker] = trail
        moved.add(h.ticker)
        was_clause = (
            T["ratchet_was_known"].format(was=was)
            if was is not None
            else T["ratchet_was_none"]
        )
        alerts.append(ProposalCard(
            action="ALERT",
            reason=T["ratchet_alert"].format(
                ticker=h.ticker, trail=trail, entry_date=h.entry_date, peak=peak,
                mult=ips.caps.trail_atr_mult, atr=atr, was_clause=was_clause,
            ),
            ips_clauses=["caps.trail_atr_mult"],
            details={
                "ticker": h.ticker, "setup_type": h.setup_type, "ratchet": True,
                "old_invalidation": was, "new_invalidation": trail,
                "running_high": peak, "atr14": atr, "asof": asof,
            },
        ))

    thesis_gap: dict[str, str] = {}   # ticker -> why its setup_type's rule could not run
    # ticker -> what monitoring concluded, for the SWAP card in step 4 to quote.
    thesis_note: dict[str, str] = {}
    for h in holdings:
        if h.setup_type not in MONITORED_SETUPS:
            thesis_gap[h.ticker] = (
                T["setup_named"].format(setup_type=_setup_name(h.setup_type, lang_key))
                if h.setup_type
                else T["setup_missing"]
            )
            continue
        price = prices.get(h.ticker)
        if price is None:
            # the one gap the loss-from-entry rule below shares, so it is worded the same
            thesis_gap[h.ticker] = T["no_price_session"]
            continue
        entry_price = _entry_price(h)
        entry = (
            T["entry_recorded"].format(entry_price=entry_price, chg=price / entry_price - 1)
            if entry_price
            else T["entry_missing"]
        )
        at = _price_phrase(price, asof, T)
        stop = live_stop.get(h.ticker)
        # how a card names the level: the user's own words for it, or the trail's — and
        # the ALERT is only "above" when this run is the one that moved it.
        level = "" if stop is None else (
            T["trail_known"].format(stop=stop)
            if h.ticker in moved
            else T["trail_earlier"].format(stop=stop)
            if stop != h.invalidation_price
            else T["trail_recorded"].format(stop=stop)
        )
        if h.setup_type == "trend_add" and (stop is None or price > stop):
            # the trend half of the rule; the trailed stop below is the drawdown half
            ma = ma50.get(h.ticker)
            if ma is None:
                thesis_gap[h.ticker] = T["no_ma50"].format(ma_trend=MA_TREND)
                continue
            if price >= ma:
                thesis_note[h.ticker] = T["trend_intact"].format(at=at, ma=ma)
                continue
            reason = T["trend_broken"].format(ticker=h.ticker, at=at, ma=ma, entry=entry)
            details = {"ma50": ma}
        elif h.setup_type == "trend_add":
            reason = T["trail_breached"].format(ticker=h.ticker, at=at, level=level, entry=entry)
            details = {"invalidation_price": stop}
        else:  # value_dip | pullback_add — the recorded level, never MA distance
            if stop is None:
                thesis_gap[h.ticker] = T["no_invalidation"].format(
                    setup_type=_setup_name(h.setup_type, lang_key),
                )
                continue
            if price > stop:
                thesis_note[h.ticker] = T["invalidation_intact"].format(stop=stop, at=at)
                continue
            reason = T["invalidation_breached"].format(
                ticker=h.ticker, setup_type=_setup_name(h.setup_type, lang_key),
                at=at, level=level, entry=entry,
            )
            details = {"invalidation_price": stop}
        thesis_note[h.ticker] = T["thesis_broke_note"]
        alerts.append(ProposalCard(
            action="ALERT",
            reason=reason,
            details={
                "ticker": h.ticker, "setup_type": h.setup_type,
                "entry_price": entry_price, "price": price, "asof": asof, **details,
            },
        ))

    # 3b. max adverse excursion (Freeman-Shor): a loss this size forces a decision, and
    # dispatches on nothing — any position with an entry price can be far enough under
    # water, whatever setup opened it, or none. Built after the loop above so it can quote
    # what that loop concluded about the same ticker instead of talking past it.
    # The excursion is the worst *close* since entry_date (signals.trail_inputs), not this
    # session's price: a position that fell to -25% and recovered to -5% made the decision
    # the key exists to force, and running propose weekly must not miss it (TASK-11 #4).
    # A holding with no entry_date has no such window, and falls back to today's price.
    mae_gap: dict[str, str] = {}   # ticker -> why the loss-from-entry rule could not run
    decided: dict[str, str] = {}   # ticker -> its loss, for the SWAP card in step 4 to quote
    mae_pct = ips.caps.max_adverse_excursion_pct
    decisions: list[ProposalCard] = []
    for h in holdings:
        price, entry_price = prices.get(h.ticker), _entry_price(h)
        if price is None:
            mae_gap[h.ticker] = T["no_price_session"]
            continue
        if entry_price is None:
            mae_gap[h.ticker] = (
                T["mae_gap_no_entry"] if h.entry_price is None
                else T["mae_gap_bad_entry"].format(entry_price=h.entry_price)
            )
            continue
        low = min_close.get(h.ticker)
        worst = price if low is None else min(price, low)
        if not _past_threshold(worst, entry_price, mae_pct):
            continue
        note = thesis_note.get(h.ticker)
        decided[h.ticker] = f"{worst / entry_price - 1:+.1%}"
        chg = worst / entry_price - 1
        # the card states what the rule read: the low when the position has recovered off
        # it, and this session's print when the low *is* this session's print.
        lead = (
            T["mae_lead_recovered"].format(
                ticker=h.ticker, chg=chg, entry_price=entry_price, entry_date=h.entry_date,
                worst=worst, at=_price_phrase(price, asof, T),
            )
            if worst < price else
            T["mae_lead_current"].format(
                ticker=h.ticker, chg=chg, entry_price=entry_price, at=_price_phrase(price, asof, T),
            )
        )
        monitor_note = (
            T["mae_monitor_note"].format(
                ticker=h.ticker, setup_type=_setup_name(h.setup_type, lang_key), note=note,
            )
            if note else ""
        )
        decisions.append(ProposalCard(
            action="DECIDE",
            reason=T["mae_reason"].format(lead=lead, mae_pct=mae_pct) + monitor_note,
            ips_clauses=["caps.max_adverse_excursion_pct"],
            details={
                "ticker": h.ticker, "entry_price": entry_price, "price": price, "asof": asof,
                "drawdown": worst / entry_price - 1, "threshold_pct": mae_pct,
                # only when the rule had one: the card's details are the numbers it read
                **({"min_close": worst} if low is not None else {}),
            },
        ))

    # 3b2. missing-price ALERT (TASK-20). Any holding with no price for this session got
    # nothing compared this run — not "unwatched by design" (a value_dip is supposed to
    # look weak; no setup_type has no rule to begin with), but a rate limit or a provider
    # gap this run could not see past. That is a different claim from the coverage line
    # below and gets its own card, ahead of it.
    # PR39 R1/R2/R3: price coverage is counted over ALL holdings, not only the ones a
    # rule could have run on (a "ruled" filter here read as "the run compared everything
    # it could" even when a whole unruled book went unpriced, and undercounted "of M").
    # task-20 R4 (probe pr40): gated on prices_attempted — a run that never fetched a
    # panel (a score-only book, no setup_type/entry_price/vol target anywhere) never
    # tried to price anything, so it is not "blind" and gets no card here at all.
    missing_price = (
        [h.ticker for h in holdings if prices.get(h.ticker) is None] if prices_attempted else []
    )
    if missing_price:
        alerts.append(ProposalCard(
            action="ALERT",
            reason=T["missing_price_alert"].format(
                n=len(missing_price), total=len(holdings), names=", ".join(missing_price),
            ),
            ips_clauses=[],
            details={"missing": missing_price, "total": len(holdings)},
        ))
    missing_price_set = set(missing_price)

    # 3c. coverage. Two rules watch a position — its setup_type's and the loss-from-entry
    # one — so a position is fully watched, partly watched, or watched by neither, and the
    # three say different things. A partially-monitored position is not an unwatched one:
    # the same run may well have alerted on it, and claiming "this run says nothing about
    # it either way" over both groups made two cards contradict each other about one
    # ticker. Emitted only when something is actually being watched, so a holdings file
    # with no setup_type and no entry_price anywhere gets its cards unchanged.
    # TASK-18: entry_date_source: snapshot_first_seen is a third, independent note — a
    # tracking start, not a fill, so the stop ratchet (step 3a) silently declines to
    # trail from it. It does not count toward the two-rule watched/unwatched split above
    # (both rules may still be running fine on this ticker), but the row still belongs
    # on the coverage line, so it is merged into the same why/item construction.
    unmonitored: list[str] = []   # nothing at all is watching these
    partial: list[str] = []       # watched, but not on every axis they have (or flagged)
    watching_anything = False
    entry_flagged = False
    for h in holdings:
        core = [g for g in (thesis_gap.get(h.ticker), mae_gap.get(h.ticker)) if g]
        watching_anything |= len(core) < 2
        entry_note = (
            T["entry_date_note"]
            if h.entry_date_source == "snapshot_first_seen" else None
        )
        entry_flagged |= entry_note is not None
        why = core + ([entry_note] if entry_note else [])
        if h.ticker in missing_price_set:
            # PR39 R1: the missing-price ALERT above already says "no price for this
            # session" for this ticker — repeating it here would say it twice in two
            # voices. Its OTHER gaps (a bad setup_type, a snapshot_first_seen entry
            # date) are independent of price and still belong on this line; only when
            # price was its one and only gap does it drop off this card entirely.
            why = [w for w in why if w != T["no_price_session"]]
        if not why:
            continue
        # dict.fromkeys: both rules read the session price, so a position without one
        # states that reason once.
        item = f"{h.ticker} ({'; '.join(dict.fromkeys(why))})"
        (partial if len(core) < 2 else unmonitored).append(item)
    if (unmonitored or partial) and (watching_anything or entry_flagged):
        said = [T["coverage_summary"].format(n=len(unmonitored) + len(partial))]
        if unmonitored:
            said.append(T["coverage_unmonitored"].format(names=", ".join(unmonitored)))
        if partial:
            said.append(T["coverage_partial"].format(names=", ".join(partial)))
        alerts.append(ProposalCard(
            action="ALERT",
            reason=" ".join(said),
            details={
                "unmonitored": [u.split(" (")[0] for u in unmonitored],
                "partially_monitored": [u.split(" (")[0] for u in partial],
            },
        ))

    # 3d. rating veto (TASK-16): the newest ledger rating on a held name is a veto, not
    # a ranking input — it never enters step 4's swap hurdle or verdict floor (rating
    # hit rate is unmeasured until `evaluate` has 60+ sessions). A rating at or below
    # Underweight forces the same three-way decision as MAE: kill it, rewrite the
    # thesis, or hold with a written reason. No price is read here, so a holding with
    # no session price still gets this card (TASK-20's missing-price gap is a price
    # problem, not a ratings one). Exactly one DECIDE per ticker: when MAE (3b) already
    # forced one this run, the rating sentence folds into that card instead of a second.
    for h in holdings:
        row = ratings_held.get(h.ticker)
        if row is None or not verdict_at_least("underweight", row.get("rating") or ""):
            continue
        src = row.get("source") or T["rating_source_missing"]
        model = row.get("model") or T["rating_model_missing"]
        stop = row.get("stop_loss")
        stop_str = f"{stop:.2f}" if stop is not None else T["rating_stop_missing"]
        sentence = T["rating_decide"].format(
            ticker=h.ticker, rating=_rating_name(row["rating"], lang_key), date=row.get("date"),
            src=src, model=model, stop=stop_str,
        )
        rating_details = {
            "rating": row["rating"], "rating_date": row.get("date"),
            "source": row.get("source"), "model": row.get("model"), "report_stop": stop,
        }
        if h.ticker in decided:
            card = next(c for c in decisions if c.details.get("ticker") == h.ticker)
            card.reason = f"{card.reason} {sentence}"
            card.details = {**card.details, **rating_details, "kind": "mae+rating"}
        else:
            decisions.append(ProposalCard(
                action="DECIDE",
                reason=sentence,
                details={"ticker": h.ticker, **rating_details, "kind": "rating"},
            ))

    # 4. challenger vs incumbent.
    held = {h.ticker for h in holdings}
    scored = [h for h in holdings if h.score is not None]
    swaps: list[ProposalCard] = []
    if not scored:
        alerts.append(ProposalCard(
            action="ALERT",
            reason=T["no_score_alert"],
        ))
    else:
        used: set[str] = set()
        floor = ips.turnover.verdict_floor
        hurdle, friction_pct, friction_field = swap_hurdle(ips, market)
        # strongest challenger picks first — caller order must not decide who
        # gets the weakest incumbent
        for c in sorted(challengers, key=lambda c: c.final_score, reverse=True):
            if c.ticker in held:
                continue
            verdict = verdicts.get(c.ticker, "neutral")
            if not verdict_at_least(verdict, floor):
                continue
            theme = themes.get(c.ticker)
            same_theme_only = theme in breached
            pool = [h for h in scored if h.ticker not in used and (not same_theme_only or h.theme == theme)]
            if not pool:
                continue
            incumbent = min(pool, key=lambda h: h.score)
            gap = c.final_score - incumbent.score
            if gap < hurdle:
                continue
            used.add(incumbent.ticker)
            auto = [t for t in (c.ticker, incumbent.ticker) if t in auto_scored]
            disclosure = ""
            if len(auto) == 2:
                disclosure = T["disclosure_both"].format(
                    names=", ".join(auto), n=auto_scored[auto[0]], pool=pool_name,
                )
            elif auto:
                # One operand is a percentile in that pool and the other is a hand-typed
                # number that was never put on it, so the subtraction spans two scales and
                # is not a rank distance in either (R14).
                hand = c.ticker if auto[0] == incumbent.ticker else incumbent.ticker
                disclosure = T["disclosure_one"].format(
                    auto=auto[0], n=auto_scored[auto[0]], pool=pool_name, hand=hand,
                )
            # The bridge between step 3 and step 4: the ranking is a momentum composite
            # and does not read setup_type (tasks/TODO.md T39), so a thesis-intact
            # value_dip can still be the weakest incumbent. Say so on the card rather
            # than letting both halves of the run go silent about the same position.
            note = thesis_note.get(incumbent.ticker)
            bridge = (
                T["swap_bridge"].format(
                    incumbent=incumbent.ticker,
                    setup_type=_setup_name(incumbent.setup_type, lang_key), note=note,
                )
                if note else ""
            )
            # Selling a position this run already forced a decision on is one of that
            # card's three options, not a fourth: without this the same run told the user
            # to add to it per plan and to sell it, with neither card naming the other.
            if incumbent.ticker in decided:
                bridge += T["swap_decided_addendum"].format(
                    incumbent=incumbent.ticker, loss=decided[incumbent.ticker],
                )
            # Sizing on a SWAP is the incumbent's, and the card says whose it is. The buy
            # is a name the user has not opened: a Candidate carries no entry or
            # invalidation price (cli.py builds it from a screen, not from a plan), so the
            # percent-risk cap has nothing to read on that side. What can be sized is the
            # slot being freed.
            target, cap_clause, why = target_weight(ips, incumbent, T)
            sizing = T["swap_sizing"].format(
                incumbent=incumbent.ticker, target=target, why=why, challenger=c.ticker,
            )
            swaps.append(ProposalCard(
                action="SWAP",
                sell=incumbent.ticker,
                buy=c.ticker,
                reason=T["swap_main"].format(
                    challenger=c.ticker, c_score=c.final_score, incumbent=incumbent.ticker,
                    i_score=incumbent.score, gap=gap, hurdle=ips.turnover.hurdle,
                    friction=friction_pct, verdict=_rating_name(verdict, lang_key),
                    floor=_rating_name(floor, lang_key),
                ) + sizing + bridge + disclosure,
                ips_clauses=[
                    "turnover.hurdle", "turnover.verdict_floor",
                    f"friction.{friction_field}", cap_clause,
                ],
                score_gap=gap,
                friction_pct=friction_pct,
                details={
                    "challenger_score": c.final_score,
                    "incumbent_score": incumbent.score,
                    "verdict": verdict,
                    "auto_scored": auto,
                    "incumbent_setup_type": incumbent.setup_type,
                    "incumbent_thesis": note,
                    "incumbent_decided": incumbent.ticker in decided,
                    "target_weight": target,
                    "binding_cap": cap_clause,
                },
            ))

    # 5. order + weekly turnover cap.
    swaps.sort(key=lambda card: card.score_gap, reverse=True)
    room = max(ips.turnover.max_swaps_per_week - swaps_this_week, 0)
    kept, suppressed = swaps[:room], swaps[room:]
    if suppressed:
        kept.append(ProposalCard(
            action="ALERT",
            reason=T["suppressed_alert"].format(
                n=len(suppressed), limit=ips.turnover.max_swaps_per_week, made=swaps_this_week,
            ),
            ips_clauses=["turnover.max_swaps_per_week"],
            details={"suppressed_count": len(suppressed)},
        ))

    # decisions after alerts: a DECIDE quotes the thesis ALERT above it ("see the ALERT
    # above") when the same run broke that position's thesis. SCALE goes after TRIMs
    # (both are cap enforcement) and before the challenger-driven SWAP cards.
    result = alerts + decisions + trims + scale_cards + kept
    # TASK-22: every card renders `reason` in `lang_key` (English by construction unless
    # `lang`/`ips.lang` resolved to Chinese above) — tag it here, once, rather than at
    # every `ProposalCard(...)` call site above.
    for card in result:
        card.lang = lang_key
    return result
