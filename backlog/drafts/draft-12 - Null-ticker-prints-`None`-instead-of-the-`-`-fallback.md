---
id: DRAFT-12
title: Null ticker prints `None` instead of the `?` fallback
status: Draft
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

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:46 `item.get('ticker', '?')` returns None (not `'?'`) when the key is present but null, so `- {ticker: null, weight: 0.1, bogus: 1}` produces `holdings.yml: None: unknown key 'bogus'`.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the message reads `?` (or `<no ticker>`) when the ticker is absent or null.
<!-- AC:END -->
