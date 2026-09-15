---
id: TASK-23
title: 'zh cards carry no leftover English words'
status: In Progress
assignee: []
created_date: '2026-09-15'
labels: []
dependencies: []
references:
  - TASK-22
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-22 (PR #46) renders `propose` cards in Traditional Chinese, but the `zh` table in
`CARD_TEXT` (kuroshio/core/allocator/engine.py) still leaves English words inside Chinese
sentences, and some interpolated values are English: `run` (這次 run), `thesis`, `entry date`,
`cap`, `book`, `universe`, the field names `entry_price` / `invalidation_price` / `setup_type`,
in-text card names `ALERT` / `DECIDE` / `SWAP`, `x` in "3x ATR", the setup values
(`trend_add`, `pullback_add`, `value_dip`, `other`), rating/verdict values (`'Hold'`, `'neutral'`,
`Underweight` …) and the `unrecorded source` / `unrecorded model` fallbacks. The owner reads these
cards on Discord and the mix is hard to read.

In `zh` only:

- Every English word above becomes Chinese: e.g. 這次檢查, 投資論點, 進場日期, 上限, 組合, 股池,
  進場價, 失效價, 進場型態, 警示 / 決策 / 換倉, 「3 倍 ATR」.
- Setup values render through a zh name table: trend_add 趨勢加碼, pullback_add 回檔加碼,
  value_dip 價值低接, other 其他 (an unknown value falls back to itself).
- Rating and verdict values render through a zh table: Buy 買進, Overweight 增持,
  Hold / Neutral 中立, Underweight 減持, Sell 賣出, case-insensitive (unknown → itself); the
  rating-source/model fallbacks become 未記錄來源 / 未記錄模型.
- Allowed to stay Latin: tickers, theme names, IPS clause keys on the `- ` detail line, dates,
  numbers, recorded model/source identifiers, and the acronyms IPS, NAV, MAE, ATR, MA.
- Downstream parsers read these zh phrases and they must survive unchanged: a ticker-led reason
  still opens with the ticker, a theme reason still opens with `「<theme>」主題`, the coverage
  summary still contains `沒有被完整監控`, and the missing-price alert still lists names as
  `虧損規則：T1, T2。`.

Not changed: English output (byte-for-byte), `### ` heads, which cards fire, `details`, numbers,
the vendored `kuroshio/agents/engine`.

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips ~/.kuroshio/ips-us.md --holdings ~/.kuroshio/book/latest/actual/holdings_us.yaml --market us --candidates ~/.kuroshio/book/latest/candidates.yml --no-ledger > /tmp/zh23.out; echo rc=$?; grep -vE '^(###|- |$)' /tmp/zh23.out | grep -nE '[a-z]'` · budget $0, one yfinance fetch of ~25 names, under 60 s · reps 1 — rc=0 (the owner IPS now has `lang: zh`), and the final grep prints nothing: no lowercase Latin letter left in any card body.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 every zh card case in tests/test_allocator_zh.py asserts (via one shared helper) that its reason, after removing the fixture's tickers, themes, dates, numbers and the allowed acronyms, contains no Latin letter; all cases pass, including every conditional clause and the rating-veto card with and without recorded source/model.
- [ ] #2 setup and rating/verdict values render through the zh tables above (tests for each value and for an unknown value falling back to itself); English output is byte-for-byte unchanged (pre-existing tests unedited).
- [ ] #3 tests pin the four downstream phrases: ticker-first and `「<theme>」主題` openings, `沒有被完整監控`, and `虧損規則：T1, T2。`.
<!-- AC:END -->
