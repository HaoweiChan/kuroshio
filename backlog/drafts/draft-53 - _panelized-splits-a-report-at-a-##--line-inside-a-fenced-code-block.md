---
id: DRAFT-53
title: '`_panelized` splits a report at a `## ` line inside a fenced code block'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #30
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
kuroshio/site/render.py `_panelized` splits role text at lines starting with `## `; a fenced code block containing such a line is cut in two and the fenced line is promoted to an h2 with the backticks printed literally. Verifier note on PR #30: `_panelized("## Setup\n\n```text\n## a fenced line\nvalue\n```\n\n## Next\nafter\n")`. Track fence state while splitting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case tests/test_site.py::test_panelized_ignores_headings_inside_fences green
<!-- AC:END -->
