---
id: DRAFT-14
title: propose drops the US `sector` factor because it has no --sector-map
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T25
  - T4
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T4 calls `profile.screen(panel)` / `profile.score_names(panel, tickers=...)` with no `sector_map`, because `propose` has no `--sector-map` flag (`screen`/`backtest` both do). For `--market us` that silently drops the `sector` factor (0.20 of WEIGHTS) and renormalizes, so an auto-filled score is not the same number `kuroshio screen --sector-map ...` would print for the same name on the same day. Same for `--asof`: propose always scores the latest session.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `propose` accepts `--sector-map` (and, if wanted, `--asof`) and threads it into both screening calls, matching `cmd_screen`'s `screen_kwargs` handling; one test proving the sector factor appears in an auto-filled US score.
<!-- AC:END -->
