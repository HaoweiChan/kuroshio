---
id: TASK-19
title: 'Attack sleeve admits only Overweight/Buy overflow names (--attack-floor)'
status: PR
assignee: []
created_date: '2026-09-09'
labels: []
dependencies: []
references:
  - TASK-13
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner traded the 2026-09-04 book on 2026-09-09 and asked why MTSI, rated Hold, sat in the
attack sleeve. Because the sleeve is defined mechanically: the first `attack_n` names the
per-theme cap pushed out of the core, with the rating used only as a veto (Sell/Underweight).
Concentration beyond the diversification rule is extra risk, so the attack sleeve — and only the
attack sleeve — should require conviction: `kuroshio book --attack-floor {hold,overweight,buy}`,
default `overweight`. An overflow name below the floor is skipped with the reason "below the
attack floor (<rating>)" and the next overflow name by rank takes the slot; the core's veto-only
rule is unchanged; the rating stays a gate, never a ranking input (the hurdle is still the score
gap). `rule_attack` in the rendered book names the floor.

On the 2026-09-08 screen this turns the attack sleeve from SMTC / ASML / ENTG (Hold) into
SMTC / ASML / TSM (Overweight, rank 65).

Probe: `PYTHONPATH=. .venv/bin/python -m kuroshio.cli book --market us --screen
~/.kuroshio/screen/latest.json --ratings ~/.kuroshio/ledger/ratings.jsonl --scores
~/.kuroshio/ledger/scores.jsonl --ips ~/.kuroshio/ips-us.md --meta ~/.kuroshio/book/meta.json
--pm-size ~/.kuroshio/book/pm_size.json --locked ~/.kuroshio/book/locked.json --out $(mktemp -d)`
(budget: one run, under 30 s, no provider) yields an attack sleeve whose every rating is
Overweight or Buy and lists the skipped Hold overflow name with the floor reason.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `--attack-floor` parses hold/overweight/buy (default overweight) and is validated; the attack sleeve admits an overflow name only when its rating is at or above the floor; `hold` reproduces today's behaviour.
- [ ] #2 a skipped overflow name appears in `skipped` with "below the attack floor (<rating>)" and the next qualifying overflow name by rank takes the slot; the core selection is unchanged — one test per branch.
- [ ] #3 the rendered book's attack rule names the floor in both label languages.
<!-- AC:END -->
