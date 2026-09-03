---
id: DRAFT-47
title: Demo payload in docs/index.html still shows the pre-sizing TRIM text
status: Draft
assignee: []
labels:
  - debt
dependencies: []
references:
  - 'PR #13 (implementer-reported)'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The embedded demo card at `docs/index.html:371` reads "Trim it back under the ceiling", a sentence no engine path emits any more — every TRIM now states a target weight and names its binding cap. The showcase advertises output the code cannot produce. Repro: `grep -c "back under the ceiling" docs/index.html` returns 1 while `grep -rc "back under the ceiling" kuroshio/` returns 0.

Probe: none — library/CLI with no deployed surface
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case `test_demo_payload_matches_engine_output` green: the demo TRIM card text is regenerated from `propose()` output, and the case fails when the two diverge.
<!-- AC:END -->
