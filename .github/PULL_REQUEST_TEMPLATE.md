<!-- Title: <type>(<scope>)?: <lowercase imperative summary>
     type ∈ feat fix docs chore refactor test perf ci build revert
     Keep every section; write "none" instead of deleting one. CI runs .github/pr_check.py. -->

## Why
<!-- 1–4 lines. The observed failure or the goal, with evidence: run id, case id,
     issue, postmortem section. A reader must be able to restate what was wrong
     without opening the diff. -->

<details><summary>Task (verbatim): <id> — <title></summary>
<!-- Paste `backlog task view <id> --plain` once at PR creation, from "## Description"
     down, every line prefixed with "> " (blockquote): GitHub renders it, and its
     headings do not become PR sections. Never edit afterwards. Delete this block
     for untracked work. -->
</details>

## What changed
<!-- Bullets by behavior, not by file: say the mechanism. -->
-
Not changed:

## Verification
Gate:
Red-first:
Live:
Not verified:
<!-- Gate: <suite> N/N · <suite> N/N · <sha>
     Red-first: <case-id> watched red at <sha>, green at <sha>   (one line per new case)
     Live: run <id> ×N on build <sha> · $<cost>    or    Live: not run — <reason>
     Not verified: what you knowingly did not check, or none -->

## Problems found
<!-- Defects met while doing the work, including what review found.
     claim → evidence → fixed (case id) | debt (id) | rejected (reason). Or: none -->
-

## Follow-ups
<!-- One line each; must name a case <id> or run <id>, otherwise it is not debt. Or: none -->
-

## Reviewer notes
Start here:
Reproduce:
