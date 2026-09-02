---
id: DRAFT-36
title: A decided position gets the same DECIDE card on every run
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T51
  - T6
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
nothing records that the user actually decided. A position 20% under entry emits an identical DECIDE card every run until the holdings file changes, and the only edits that silence it are lies (raise `entry_price`) or amputations (delete it, which also stops the thesis rule). "No silent holding of losers" then decays into a card the user learns to scroll past — the exact failure the Freeman-Shor discipline is about. Needs somewhere to record the decision and when it was made (a field on `Holding`, or the ledger T10 wants anyway), after which the card returns only when the loss deepens materially.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a position whose decision is recorded produces no DECIDE card at the same loss, and a fresh one once it is materially further under water; one test per half.
<!-- AC:END -->
