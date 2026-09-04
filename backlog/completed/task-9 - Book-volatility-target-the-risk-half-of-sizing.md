---
id: TASK-9
title: 'Book volatility target: the risk half of sizing'
status: Done
assignee: []
created_date: '2026-09-04'
labels: []
dependencies:
  - TASK-7
references:
  - docs/backtest-2026-09.md §E
  - TASK-1 (cap (c), split out: this is the only sizing rule the backtest supports today)
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-1's three caps assume a signal worth sizing; docs/backtest-2026-09.md found none, so the conviction and percent-risk halves wait. The one sizing rule the data supports is a book-level volatility target: on 12-1 momentum top-20 a 15% annualized target cut the 2021–2026 max drawdown from −33% to −14% (§E), at an out-of-sample return cost the IPS owner can choose to pay. Add `caps.book_vol_target_pct` (annualized %, `None` = off) to the IPS; `simulate` scales gross exposure to the target from the trailing 20-session realized vol of the current book (cash absorbs, never levers up); `propose` emits one SCALE card when the book's realized vol exceeds the target, naming the vol it read, the window, the target and the pro-rata cut — and nothing when it does not. `allocator/signals.py` grows a `book_vol(panel, holdings)` alongside `monitor_inputs`, so `propose` still takes no panel.

Probe: none — library/CLI with no deployed surface; ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 on the synthetic dropper panel, `simulate` with `book_vol_target_pct: 15` has a smaller max drawdown than without and never a gross exposure above 1.0; `propose` on a book whose 20-session vol is 24% with a 15% target emits one SCALE card whose text carries 24, 20, 15 and the scale factor, and emits none at 12%; `book_vol_target_pct: 0` and `150` fail `validate`; the IPS examples document the field with the §E numbers.
<!-- AC:END -->
