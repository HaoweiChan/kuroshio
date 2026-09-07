---
id: DRAFT-12
title: Null ticker prints `None` instead of the `?` fallback
status: Done
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T23
  - 'PR #5 R5'
priority: low
---

## Resolution

Closed by TASK-15. Both parsers now use `item.get('ticker') or '?'`, so a null (not
just absent) ticker reports `?` in the error prefix. Covered by
`test_holdings_from_yaml_null_ticker_reports_question_mark` and
`test_candidates_from_yaml_null_ticker_reports_question_mark` (tests/test_cli.py).

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:46 `item.get('ticker', '?')` returns None (not `'?'`) when the key is present but null, so `- {ticker: null, weight: 0.1, bogus: 1}` produces `holdings.yml: None: unknown key 'bogus'`.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the message reads `?` (or `<no ticker>`) when the ticker is absent or null.
<!-- AC:END -->

## Scheduled

Rolled into TASK-15 (input type validation for holdings.yml and candidates.yml) — do not
fix separately; that task closes all seven together and moves this file on merge.
