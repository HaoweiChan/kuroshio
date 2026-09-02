---
id: DRAFT-13
title: Provider fetch + ImportError hint is now copy-pasted three times
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T24
  - T4
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`cmd_screen` (cli.py:151-160), `cmd_backtest` and now `cmd_propose` each carry the same `get_provider(name)` / `fetch_panel(...)` / `except ImportError -> print 'the X provider is not installed' -> return 2` block. T4 followed the existing pattern rather than widen its diff; the third copy is the one that argues for extracting it.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 one helper (e.g. `_fetch_panel(profile, provider_name, tickers, ...)`) returning the panel or signalling the exit-2 path, used by all three commands, with the existing provider-missing tests still passing unchanged.
<!-- AC:END -->
