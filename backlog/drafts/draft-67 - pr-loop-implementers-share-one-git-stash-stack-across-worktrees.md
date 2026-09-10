---
id: DRAFT-67
title: 'pr-loop implementers share one git stash stack across worktrees'
status: Draft
assignee: []
created_date: '2026-09-10'
labels:
  - debt
dependencies: []
references:
  - PR #40 (TASK-15), PR #42 (TASK-16)
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The task-15 and task-16 implementers ran concurrently in separate worktrees and both used bare `git stash` / `git stash pop`; the stash stack is per repository, so each popped the other's uncommitted work and both trees ended up holding foreign hunks (task-15's book.py change surfaced in task-16's tree, task-16's cli.py/engine.py WIP in task-15's). The orchestrator caught it from the implementers' reports and reverted the foreign files by hand. The implementer brief should forbid bare stash (use a WIP commit, or `git stash push -m <tag>` + `apply <sha>`), and the orchestrator's pre-gate check should fail when `git diff origin/main --stat` touches files outside the task's declared context.

Probe: none — process change in the plugin skill text, no code
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 case the pr-loop implementer prompt names the stash rule and the orchestrator checklist has a foreign-file check before the gate
<!-- AC:END -->
