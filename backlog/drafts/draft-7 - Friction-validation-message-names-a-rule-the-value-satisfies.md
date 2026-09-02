---
id: DRAFT-7
title: Friction validation message names a rule the value satisfies
status: Draft
assignee: []
created_date: '2026-09-02 22:15'
labels:
  - debt
dependencies: []
references:
  - TODO.md T18
  - 'PR #4 R7'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
core/ips/parser.py:131-132 uses one message for three distinct rejections (bool, non-numeric, out-of-range), so a wrong-*type* value is reported with a rule its own printed value meets: `friction.tw_roundtrip_pct ('1e-3') must be a percent in [0, 100)` — and 0.001 is. The `1e-3` case is the sharp one, since PyYAML 1.1 resolves the no-dot exponent form to a string, so a user writing a perfectly reasonable number gets an error message that looks wrong. The value is correctly rejected; only the explanation misleads.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 the type failure and the range failure produce distinguishable messages, asserted by test_validate_catches_bad_friction for `"0.585"` vs `-10.0`.
<!-- AC:END -->
