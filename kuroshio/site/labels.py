"""Every user-visible string `kuroshio book` and `kuroshio site` print, keyed by language.

`labels(lang)` is the only accessor: it falls back to English for an unknown language and
for a key a translation forgot, so a half-translated table can never render a blank cell.
Values with `{}` placeholders are `str.format` templates — the placeholder names are part
of the contract, so a translation must keep them (tests/test_site.py checks both).
"""

from __future__ import annotations

LABELS: dict[str, dict[str, str]] = {
    "en": {
        # --- shared ---
        "disclaimer": (
            "Mechanical output, not investment advice. Kuroshio proposes; it never places an order. "
            "Whether to trade any of this is your decision."
        ),
        "none": "(none)",
        "na": "n/a",
        "all": "all",
        "generated": "generated {when}",
        # --- book.md ---
        "book_title": "Kuroshio book — screen as of {asof}",
        "rules_head": "Build rules",
        "rule_core": (
            "Core: up to {core_n} names down the screen ranking, theme = industry, "
            "at most {per_theme} per theme."
        ),
        "rule_veto": (
            "Agent veto: the newest rating within {ttl} days of the screen date. Sell / Underweight "
            "and unrated names are dropped, and a rating dies at the first earnings print after it."
        ),
        "rule_weight": (
            "Weight = min({base:.0%} base, caps.position_pct, percent-risk = {risk:.0%} of NAV "
            "divided by the entry-to-stop distance), times the PM size multiplier."
        ),
        "rule_attack": (
            "Attack budget {budget:.0%}: theme-cap overflow names go in at base weight first, then "
            "the highest-ranked core names are raised to {double:.0%}. Concentration, not leverage."
        ),
        "rule_cash": "Cash: whatever is left.",
        "holdings_head": "Holdings",
        "sleeve": "Sleeve",
        "core": "core",
        "attack": "attack",
        "locked": "locked",
        "locked_not_resized": "locked, not resized",
        "owner": "owner",
        "rank": "#",
        "ticker": "Ticker",
        "industry": "Industry",
        "sector": "Sector",
        "rating": "Rating",
        "weight": "Weight",
        "cap": "Binding cap",
        "entry": "Entry",
        "stop": "Stop",
        "stop_dist": "Stop distance",
        "target": "Target",
        "rr": "R:R",
        "mom": "12-1",
        "vol": "1y vol",
        "vs_ma50": "vs MA50",
        "sleeve_totals": "Core {core:.1%} · attack {attack:.1%} · locked {locked:.1%} · cash {cash:.1%}",
        "concentration_head": "Concentration",
        "book_vol_head": "Book volatility",
        "book_vol_line": (
            "Realized volatility of the held names over the last {window} sessions: "
            "{vol:.0f}% annualized."
        ),
        "proposals_head": "Proposals",
        "no_proposals": "No proposals — portfolio is within policy.",
        "skipped_head": "Vetoed, unrated, and below the cut",
        "risks_head": "What this book is really risking",
        "risk_factor": (
            "These are not {n} independent bets — they are one momentum factor. The per-theme cap "
            "limits a single industry; the sector table is the exposure that actually matters."
        ),
        "risk_stops": (
            "Stops and targets come from the research ratings and have no hit-rate record yet; the "
            "percent-risk cap sizes on them anyway. The ledger is what will settle that."
        ),
        "risk_entry": "Entry prices are the {asof} close — real fills will differ.",
        # --- alloc.md / alloc page ---
        "alloc_title": "Book allocation on NAV — screen {asof}",
        "alloc_lede": (
            "NAV **{nav:,.0f}** from the positions file you passed. Shares = floor(NAV x weight / "
            "the {asof} close). Mechanical output, not investment advice."
        ),
        "nav": "NAV",
        "cash": "Cash",
        "cash_now": "Cash (now)",
        "cash_after": "Cash after buying",
        "invested": "Book invested",
        "target_usd": "Target",
        "close": "Close",
        "shares": "Shares",
        "actual_usd": "Actual",
        "held_usd": "Held now",
        "delta_usd": "Difference",
        "locked_head": "Locked positions",
        "locked_lede": (
            "Positions you told the book not to touch; still counted in exposure and concentration."
        ),
        "symbol": "Symbol",
        "asset_type": "Type",
        "market_value": "Market value",
        "avg_cost": "Avg cost",
        "theme": "Theme",
        "qty": "Qty",
        "disposals_head": "Held but not in the book",
        "disposals_lede": "What a full reset to the book would sell, {total:,.0f} in total.",
        "queue_head": "Research queue",
        "unrated_head": "Unrated in the screened top names",
        "review_head": "Due for a re-rating (older than {days} days, or earnings within {warn} days)",
        # --- site ---
        "nav_page_title": "NAV allocation",
        "book_page_title": "Book",
        "reports_page_title": "Research reports",
        "book_lede": (
            "Screen ranking -> rating veto -> IPS weights. Mechanical output, not investment advice; "
            "whether to trade any of it is your decision."
        ),
        "reports_lede": "Every report the research pipeline wrote, newest first.",
        "report_lede": "Full research report.",
        "book_names": "Book names",
        "gross": "Gross exposure",
        "locked_weight": "Locked",
        "book_vol_stat": "Book volatility",
        "sort_hint": "screen {asof} · entry = the {asof} close · click a column to sort",
        "ips_head": "IPS · {name}",
        "position_cap": "position cap",
        "hard_cap": "hard cap / name",
        "theme_budget": "theme budget",
        "theme_cap": "theme cap · {theme}",
        "risk_budget": "risk budget / name",
        "forced_decision": "forced decision",
        "turnover_hurdle": "turnover hurdle",
        "verdict_floor": "verdict floor",
        "max_swaps": "max swaps / week",
        "step_holdings": "STEP 1 · HOLDINGS",
        "step_policy": "STEP 2 · POLICY",
        "step_vetoes": "STEP 3 · VETOES",
        "policy_head": "Concentration and IPS",
        "policy_lede": (
            "Theme budgets and the per-name cap come from your IPS; the cards are what propose "
            "says about this book."
        ),
        "holdings_lede": (
            "Core names walk the screen ranking under the per-theme cap; attack names are the "
            "overflow leaders; locked names are yours."
        ),
        "skipped_lede": "Screened names that did not make the book.",
        "filter_veto": "vetoed",
        "filter_unrated": "unrated",
        "filter_cut": "below the cut",
        "date": "Date",
        "in_book": "In book",
        "last_close": "last close",
        "next_earnings": "next earnings",
        "other_dates": "Other dates",
        "reports_count": "{reports} report(s) · {names} name(s)",
        "no_report": "(no report)",
    },
    "zh": {
        "disclaimer": "機械輸出，不是投資建議。Kuroshio 只提案，從不下單；下不下單是你的決定。",
        "none": "（無）",
        "na": "n/a",
        "all": "全部",
        "generated": "產生於 {when}",
        "book_title": "Kuroshio book — 篩選日 {asof}",
        "rules_head": "建構規則",
        "rule_core": "核心：沿篩選排名最多 {core_n} 檔，theme = industry，每個 theme 最多 {per_theme} 檔。",
        "rule_veto": (
            "評級否決：取篩選日前 {ttl} 天內最新的一筆評級。Sell / Underweight 與未評級剔除；"
            "評級在它之後的第一次財報就失效。"
        ),
        "rule_weight": (
            "權重 = min({base:.0%} 基礎, caps.position_pct, percent-risk = {risk:.0%} NAV ÷ 進場到停損距離)，"
            "再乘 PM 的倉位係數。"
        ),
        "rule_attack": (
            "攻擊預算 {budget:.0%}：被 theme 上限擠出的名字先以基礎權重放進去，剩餘預算把排名最高的核心名字"
            "加碼到 {double:.0%}。集中而非槓桿。"
        ),
        "rule_cash": "現金：剩下的。",
        "holdings_head": "持倉",
        "sleeve": "部位",
        "core": "核心",
        "attack": "攻擊",
        "locked": "鎖定",
        "locked_not_resized": "鎖定，不調整",
        "owner": "owner",
        "rank": "排名",
        "ticker": "Ticker",
        "industry": "Industry",
        "sector": "Sector",
        "rating": "評級",
        "weight": "權重",
        "cap": "綁住的 cap",
        "entry": "進場",
        "stop": "停損",
        "stop_dist": "停損距離",
        "target": "目標",
        "rr": "R:R",
        "mom": "12-1",
        "vol": "1y vol",
        "vs_ma50": "現價 vs MA50",
        "sleeve_totals": "核心 {core:.1%} · 攻擊 {attack:.1%} · 鎖定 {locked:.1%} · 現金 {cash:.1%}",
        "concentration_head": "集中度",
        "book_vol_head": "帳戶波動",
        "book_vol_line": "持股（現金不計）近 {window} 個交易日實現波動：{vol:.0f}% 年化。",
        "proposals_head": "propose 卡片",
        "no_proposals": "沒有提案 — 目前在政策範圍內。",
        "skipped_head": "被否決、未評級、額滿之後",
        "risks_head": "這個 book 的真實風險",
        "risk_factor": (
            "這不是 {n} 個獨立的部位，是一個動能因子。每個 theme 的上限只擋單一 industry，"
            "sector 集中度表才是真的曝險。"
        ),
        "risk_stops": (
            "停損與目標來自研究評級，還沒有任何命中率紀錄；percent-risk cap 仍然拿它算權重。"
            "帳本會把這件事記下來。"
        ),
        "risk_entry": "進場價是 {asof} 收盤，實際成交會不同。",
        "alloc_title": "Book 在 NAV 上的分配 — 篩選日 {asof}",
        "alloc_lede": (
            "NAV **{nav:,.0f}**，來自你傳入的持倉檔。股數 = floor(NAV × 權重 ÷ {asof} 收盤)。"
            "機械輸出，不是投資建議。"
        ),
        "nav": "NAV",
        "cash": "現金",
        "cash_now": "現金（現在）",
        "cash_after": "建倉後現金",
        "invested": "book 投入",
        "target_usd": "目標金額",
        "close": "收盤",
        "shares": "股數",
        "actual_usd": "實際金額",
        "held_usd": "現持有",
        "delta_usd": "差額",
        "locked_head": "鎖定部位",
        "locked_lede": "你說不動的部位；book 不調整，但算進曝險與集中度。",
        "symbol": "Symbol",
        "asset_type": "類型",
        "market_value": "市值",
        "avg_cost": "均價",
        "theme": "theme",
        "qty": "股數",
        "disposals_head": "現持有但不在 book",
        "disposals_lede": "完全照 book 重建會處分的部位，合計 {total:,.0f}。",
        "queue_head": "研究佇列",
        "unrated_head": "篩選前段裡尚未評級的名字",
        "review_head": "該重評的（評級超過 {days} 天，或 {warn} 天內財報）",
        "nav_page_title": "NAV 分配",
        "book_page_title": "Book",
        "reports_page_title": "研究報告",
        "book_lede": "篩選排名 → 評級否決 → IPS 權重。機械輸出，不是投資建議；下不下單是你的決定。",
        "reports_lede": "研究流程寫出的每一份報告，新的在前。",
        "report_lede": "完整研究報告。",
        "book_names": "book 持股",
        "gross": "總曝險",
        "locked_weight": "鎖定部位",
        "book_vol_stat": "帳戶波動",
        "sort_hint": "篩選 {asof} · 進場 = {asof} 收盤 · 點欄位排序",
        "ips_head": "IPS · {name}",
        "position_cap": "單一部位上限",
        "hard_cap": "單一部位硬上限",
        "theme_budget": "theme 預算",
        "theme_cap": "theme 上限 · {theme}",
        "risk_budget": "單一部位風險預算",
        "forced_decision": "強制決策點",
        "turnover_hurdle": "換股門檻",
        "verdict_floor": "評級下限",
        "max_swaps": "每週最多換股",
        "step_holdings": "STEP 1 · 持倉",
        "step_policy": "STEP 2 · 政策",
        "step_vetoes": "STEP 3 · 否決",
        "policy_head": "集中度與 IPS",
        "policy_lede": "theme 預算與單一部位上限來自你的 IPS；卡片是 propose 對這本 book 的意見。",
        "holdings_lede": "核心沿篩選排名走並受 theme 上限限制；攻擊是被擠出的領漲股；鎖定是你自己的部位。",
        "skipped_lede": "篩選到但沒進 book 的名字。",
        "filter_veto": "被否決",
        "filter_unrated": "未評級",
        "filter_cut": "額滿之後",
        "date": "日期",
        "in_book": "在 book",
        "last_close": "收盤",
        "next_earnings": "下次財報",
        "other_dates": "其他日期",
        "reports_count": "{reports} 份 · {names} 檔",
        "no_report": "（無報告）",
    },
}


def labels(lang: str | None) -> dict[str, str]:
    """The label table for `lang`, English-backed: an unknown language is English, and a
    key a translation is missing falls through to the English string."""
    lang = (lang or "en").lower().replace("_", "-")
    table = LABELS.get(lang) or LABELS.get(lang.split("-")[0]) or {}
    return {**LABELS["en"], **table}
