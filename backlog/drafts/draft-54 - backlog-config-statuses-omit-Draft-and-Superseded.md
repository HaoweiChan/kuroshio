---
id: DRAFT-54
title: 'backlog config statuses omit Draft and Superseded'
status: Draft
assignee: []
created_date: '2026-09-06'
labels:
  - debt
dependencies: []
references:
  - PR #26 (TASK-11)
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`backlog/config.yml` lists `statuses: [To Do, In Progress, Done]`; `backlog/drafts/*` now carry `Draft` and `Superseded` (TASK-11 closed drafts 26/28/37), so the Backlog.md CLI's status vocabulary and the files disagree.

Reported by the TASK-11 implementer/verifier as adjacent to the trailing-stop work and left out of PR #26 by the debt rule.

Probe: none — library change, ruff + pytest are the whole truth
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 run `backlog task list --plain` lists no status warnings
<!-- AC:END -->
