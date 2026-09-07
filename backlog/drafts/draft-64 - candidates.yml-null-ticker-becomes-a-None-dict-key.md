---
id: DRAFT-64
title: 'candidates.yml null ticker becomes a None dict key'
status: Draft
assignee: []
labels:
  - debt
dependencies: []
references:
  - TASK-15 implementer report
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-15 rejects a *missing* `ticker` in `_candidates_from_yaml`, which is what its
acceptance named. A ticker key that is present but null still gets through:
`- {ticker: null, verdict: buy}` parses to `Candidate(ticker=None, ...)` and lands as a
`None` key in the `verdicts` / `themes` maps the allocator reads. The holdings parser has
the same shape for its own non-required fields.

Repro (fails today):
`python -c "from kuroshio.cli import _candidates_from_yaml; import tempfile; f=tempfile.NamedTemporaryFile(suffix='.yml',delete=False,mode='w'); f.write('- {ticker: null, verdict: buy}\n'); f.close(); print(_candidates_from_yaml(f.name))"`

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case `test_candidates_from_yaml_rejects_null_ticker` green — a present-but-null `ticker` is a `ValueError` on the same exit-2 path as a missing one.
<!-- AC:END -->
