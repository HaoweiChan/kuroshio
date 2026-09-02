---
id: DRAFT-17
title: 'Unknown --provider value is a traceback, not exit 2'
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T29
  - 'PR #6 R9'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`get_provider(provider_name)` is called inside `try: ... except ImportError` in all three commands (cmd_screen, cmd_backtest, and now cmd_propose at cli.py:296), but providers/__init__.py:23 raises `ValueError(f"Unknown provider {name!r}...")` — so `--provider bogus` prints a traceback instead of the exit-2 install hint next to it. Pre-existing shape, newly reproduced on the propose surface.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `except (ImportError, ValueError)` (or `choices=sorted(_REGISTRY)`) so an unknown provider exits 2 with the message on stderr, in all three commands.
<!-- AC:END -->
