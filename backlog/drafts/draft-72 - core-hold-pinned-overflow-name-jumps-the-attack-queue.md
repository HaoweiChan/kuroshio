---
id: DRAFT-72
title: A core-held name pushed out by the per-theme cap jumps the attack queue
status: Draft
assignee: []
created_date: '2026-10-14'
labels:
  - debt
dependencies: []
references:
  - 'PR #66 R1'
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 run `PYTHONPATH=.:tests python -c "import test_book as t, kuroshio.core.book as bk; s,r=t._one_theme_screen(); [print(h,[x['ticker'] for x in bk.build_book(s,r,t._ips(),rules=bk.BookRules(core_n=2,core_per_theme=1,attack_n=1,core_hold_rank=h),prev_book={'core':[{'ticker':'T5'},{'ticker':'T6'}]})['attack']]) for h in (0,7)]"` passes: prints ['T2'] for both values (today 7 → ['T6']).
<!-- AC:END -->
