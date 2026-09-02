---
id: DRAFT-1
title: Decide whether `hold` is a legal IPS `verdict_floor` spelling
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T11
  - 'PR #3 R1'
  - R2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
T1 made `_rank` alias `hold` → `neutral` on *both* arguments of `verdict_at_least`, so `verdict_at_least("buy", "hold")` is True — but `validate()` (core/ips/parser.py:124) still rejects `turnover.verdict_floor: hold` against `VERDICT_ORDER`, and `cmd_propose` exits 2 on any validate problem. The same word is legal as an agent verdict and illegal as a user-authored floor. Pick one: accept `hold` in validation (share the alias helper, list it in the error message), or narrow `_rank` to the verdict argument only and drop the `verdict_at_least("buy", "Hold")` assertion in tests/test_ips.py:112. Whichever way it goes, docs/ARCHITECTURE.md:128 and the `examples/ips-*.md` comments still enumerate only the five canonical names and must say what `hold` does (R2).

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `kuroshio ips-validate` and `verdict_at_least` agree on whether `hold` is a legal floor, proven by a test; the ARCHITECTURE.md verdict-vocabulary line matches the decision.
<!-- AC:END -->
