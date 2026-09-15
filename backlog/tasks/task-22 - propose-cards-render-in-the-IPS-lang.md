---
id: TASK-22
title: 'propose cards render in the IPS lang (zh = Traditional Chinese)'
status: PR
assignee: []
created_date: '2026-09-15'
labels: []
dependencies: []
references:
  - TASK-21
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The desk posts `propose` cards to a Chinese-reading owner, but every card body is English while
the book, the site and the desk's own titles are Chinese — the notification reads as a mix of two
languages. The IPS already carries `lang` (`en` default) and `kuroshio book`/`site` already honour
it through `kuroshio/site/labels.py`'s `labels(lang)`; `propose` ignores it.

Cards render in a language:

- `propose()` in `kuroshio/core/allocator/engine.py` takes keyword-only `lang: str | None = None`
  (None → `ips.lang`). Every card `reason` it builds has a `zh` (Traditional Chinese) rendering,
  and `ProposalCard.to_markdown` renders its detail-line labels (`score gap`, `est. friction`,
  `per your IPS`) in the card's language.
- Resolution follows `labels()`: `zh`, `zh-TW`, `zh_TW` → Chinese; anything else, including an
  unknown value, → English. The English wording stays byte-for-byte what it is today, so every
  existing test passes without edits.
- Stays verbatim in every language (machine-read downstream): the `### ` head line (`### SWAP A → B`,
  `### DECIDE T`, `### TRIM T`, `### SCALE gross exposure`, `### ALERT`), tickers, theme names,
  `setup_type` values, IPS clause keys (`caps.theme_pct`, …), dates and numbers.
- `_run_propose` and `kuroshio propose` gain `--lang` (default: the IPS field); `kuroshio book`
  passes its own resolved lang to its in-process propose so book.md's cards match its labels; the
  MCP `propose` tool keeps the IPS default.
- The translations live in one place per language (e.g. a template table the engine formats), not
  as `if lang` branches scattered through the rule code.

Not changed: which cards fire, their order, `details`, any number; stderr notices; the vendored
`kuroshio/agents/engine`.

Probe: `sed 's/^lang: .*/lang: zh/' ~/.kuroshio/ips-us.md > /tmp/ips-zh.md && PYTHONPATH=. .venv/bin/python -m kuroshio.cli propose --ips /tmp/ips-zh.md --holdings ~/.kuroshio/book/latest/actual/holdings_us.yaml --market us --candidates ~/.kuroshio/book/latest/candidates.yml --no-ledger > /tmp/zh.out; echo rc=$?; grep -vE '^(###|- |$)' /tmp/zh.out | grep -E '\b[a-z]{2,} [a-z]{2,} [a-z]{2,}\b'` · budget $0, one yfinance fetch of ~25 names, under 60 s · reps 1 — rc=0, the same `###` heads as the English run in `~/.kuroshio/book/latest/actual/propose.out`, and the final grep prints nothing (no run of three lowercase English words left in any card body).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 every card kind `propose()` can emit (each `action=` site in engine.py, including every conditional clause of its reason) has a test that renders it with `lang="zh"` and asserts no run of three lowercase English words remains in the reason, and that the `### ` head, tickers, numbers and IPS clause keys are unchanged from the English card.
- [ ] #2 `lang=None` uses `ips.lang`; `en`, an unknown value, and no IPS `lang` give today's English byte-for-byte (the existing suite passes unedited); `zh-TW`/`zh_TW` give Chinese.
- [ ] #3 `kuroshio propose --lang zh` and `kuroshio book --lang zh` print Chinese cards (CLI tests); README names the IPS `lang` / `--lang` behaviour for cards in one sentence.
<!-- AC:END -->
