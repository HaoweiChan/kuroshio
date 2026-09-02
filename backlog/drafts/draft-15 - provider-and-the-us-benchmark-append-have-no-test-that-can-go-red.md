---
id: DRAFT-15
title: '--provider and the us benchmark append have no test that can go red'
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T27
  - 'PR #6 R7'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cli.py:449 adds `--provider` to propose and cli.py:288 resolves it; cli.py:293-294 appends `profile.benchmark` for `us`. Every new T4 test uses `--market tw` with `_use_stub` = `monkeypatch.setattr("kuroshio.providers.get_provider", lambda name: stub)`, which discards `name` — deleting `args.provider or` from cli.py:288 still leaves the suite at 121 passed. `profile.benchmark` is None for tw, so cli.py:293-294 never executes in any test, while docs/ARCHITECTURE.md:202 advertises `[--provider ...]` on propose.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 one test asserting `get_provider` is called with the value of `--provider` (stub captures `name`), and one `--market us` test asserting `SPY` is in the fetched ticker list.
<!-- AC:END -->
