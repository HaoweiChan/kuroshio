---
id: DRAFT-43
title: Card price precision does not survive the comparison that fired the card
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T60
  - 'PR #10 R8 repair'
  - 'PR #10 R9 (merged as named debt at the round-4 circuit breaker)'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cards print prices at two decimals (`_price_phrase`, and the entry price beside it), which is right for every name a user is likely to hold and collapses for penny ones: a correct card for entry 0.03 at price 0.0255 reads "X is -15.0% from your entry price of 0.03, at 0.03" — the same shape as the breakeven card R7 was about, though the numbers behind it are right and the stated -15.0% is exact. The rule itself is precision-clean since the R8 repair; only the display is coarse. `_price_phrase` is shared with T5's thesis cards, so widening it is a change to every card, not just this one. R9 is the sharper half of the same defect and the reason this is P1, not P3. Once the R8 repair made off-cent prices fire, the two-decimal display began contradicting the verdict printed beside it: entry 1.10 / price 0.935 emits `LOSER is -15.0% from your entry price of 1.10, at 0.94 - at or past your IPS max adverse excursion of -15.0%`, and 0.94 from 1.10 is -14.55%. `details['price']` is 0.935, so the structured field and the reason text denote different numbers. Same at entry 0.30 / price 0.255 (`at 0.26`, -13.3%). Both were NO CARD before that repair, so the card shape is new. The verdict is correct in every case; what is wrong is a restated number beside it. Two stale test comments belong to this fix, found in the round-4 review: tests/test_allocator.py:806-808 describes 5.610000000000001 as `5.61 * (1 + 1e-15)` when it is `math.nextafter(5.61, 10)`, one ULP up (~7 ULP for the stated form), and gives the loss as -14.999999999999982% instead of -14.99999999999998485%; tests/test_allocator.py:585 still says "the comparison is against the trigger price the card prints", and the card prints no trigger price since the R8 repair.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a price that does not survive two decimals is printed at a precision that does (or the card names the loss without restating the price), so no card prints a price inconsistent with the comparison that fired it and `details['price']` denotes the same value as the reason text; the thesis cards are unchanged or deliberately changed with them. Cases at entry 0.03 / price 0.0255, entry 1.10 / price 0.935 and entry 3.77 / price 3.2044 assert the full reason string and details, so a display mutant goes red. The two comments above are corrected while there.
<!-- AC:END -->
