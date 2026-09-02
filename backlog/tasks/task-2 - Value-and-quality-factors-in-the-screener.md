---
id: TASK-2
title: Value and quality factors in the screener
status: To Do
assignee: []
created_date: '2026-09-02 22:15'
labels: []
dependencies: []
references:
  - TODO.md T8
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
the screener is momentum-only; `MarketDataProvider.fetch_fundamentals` exists (providers/base.py) and is never called. Add value (composite percentile of e.g. earnings yield, FCF yield) and quality (e.g. ROE/ROIC, margin) factor groups to the US screener via fetch_fundamentals, combined as fixed-weight percentile composites per screening/score.py conventions. No factor timing. Missing fundamentals degrade gracefully (weight renormalization already does this).

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 screen output shows per-factor sub-scores; a name with missing fundamentals still ranks (momentum-only) without NaN; weights live in the screener config, not code constants.
<!-- AC:END -->
