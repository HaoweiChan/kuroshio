---
id: DRAFT-18
title: auto-filled scores are percentiles within the user's own files
status: Draft
assignee: []
created_date: '2026-09-02 22:17'
labels:
  - debt
dependencies: []
references:
  - TODO.md T30
  - 'PR #6 R2'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #6 put incumbents and challengers on one cross-section, guarded by a minimum pool size and a disclosure on the card. The guard was re-derived in round 3 (R13): it keys off the composite's *step* — `profile.min_rank_weight / (n - 1)`, read from each profile's factor weights — and refuses when that step is >= `turnover.hurdle + friction/100` (n <= 3 for both markets under the balanced IPS). That is a conservative heuristic, not an exact minimum step — it over-refuses both when the live composite is finer than the degraded one (R17) and when the surviving weights are unequal (R19). Above that size the number is still rank-within-your-portfolio, not strength within a market, and it moves when you add a ticker to the file; the card discloses that rather than fixing it. The real fix is a cross-section that is a universe: score against a `--universe` ticker file (or a cached `kuroshio screen` run's scores) and read the incumbent's and challenger's percentiles out of that, or give the screener an absolute score.

Probe: none — migrated from TODO.md
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 an auto-filled score for a name is unchanged by adding an unrelated ticker to holdings.yml, and a 2-name portfolio gets a real universe distance instead of a refusal; the pool-size guard and the rank-distance disclosure can then go.
<!-- AC:END -->
