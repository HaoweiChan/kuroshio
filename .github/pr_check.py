#!/usr/bin/env python3
"""Check a PR title and body against the team's one PR shape.

Title:  <type>(<scope>)?: <lowercase summary>   type in TYPES; ids and `code` keep case.
Body:   six sections in order, greppable Verification lines, follow-ups with a case/run id.

Usage: pr_check.py [--event $GITHUB_EVENT_PATH] | [--title T --body-file F] | [--title-only --title T]
The same title rule applies to commit subjects (.githooks/commit-msg).
Exit 1 with one error per line on failure. Stdlib only.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

TYPES = ("feat", "fix", "docs", "chore", "refactor", "test", "perf", "ci", "build", "revert")
SECTIONS = ("Why", "What changed", "Verification", "Problems found", "Follow-ups", "Reviewer notes")
MAY_BE_NONE = ("Problems found", "Follow-ups")

TITLE_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9._/-]+)\))?: (?P<summary>\S.*)$")
ID_RE = re.compile(r"\b(?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+|[A-Z]\d+)\b")  # T-M42-4, ADR-045, M51
CODE_RE = re.compile(r"`[^`]*`")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
HEADING_RE = re.compile(r"^## (.+?)\s*$", re.M)
GATE_RE = re.compile(r"^Gate: .*\b\d+/\d+\b.*\b[0-9a-f]{7,40}\b", re.M)
LIVE_RE = re.compile(r"^Live: (?:run \S+.*|not run\s+[—-]\s*\S.*)$", re.M)
FOLLOWUP_ID_RE = re.compile(r"\b(?:case|run)\s+[A-Za-z0-9][\w.-]*")


def check_title(title):
    errors = []
    m = TITLE_RE.match(title or "")
    if not m:
        return [f"title must look like '<type>(<scope>)?: <summary>' with a lowercase type: {title!r}"]
    if m["type"] not in TYPES:
        errors.append(f"title type {m['type']!r} not in {', '.join(TYPES)}")
    summary = m["summary"]
    if summary.endswith("."):
        errors.append("title must not end with a period")
    stripped = ID_RE.sub("", CODE_RE.sub("", summary))
    if re.search(r"[A-Z]", stripped):
        errors.append("title must be lowercase (ids like T-M42-4 and `code` spans may keep their case)")
    return errors


def _line(section_text, prefix):
    for line in section_text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def check_body(body):
    errors = []
    text = COMMENT_RE.sub("", body or "")
    found = [h.strip() for h in HEADING_RE.findall(text)]
    for name in SECTIONS:
        if name not in found:
            errors.append(f"missing section '## {name}'")
    if errors:
        return errors
    order = [h for h in found if h in SECTIONS]
    if order != list(SECTIONS):
        errors.append("sections out of order; expected: " + ", ".join(SECTIONS))
        return errors
    for extra in (h for h in found if h not in SECTIONS):
        errors.append(f"unexpected section '## {extra}' — a pasted task's headings go inside <details>, each line prefixed with '> '")

    parts = {}
    matches = list(HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts[m.group(1).strip()] = text[m.end():end]

    for name in SECTIONS:
        lines = [line for line in parts[name].splitlines() if line.strip()]
        if not lines:
            errors.append(f"section '## {name}' is empty (write 'none' if nothing applies)")

    changed = parts["What changed"]
    if not (_line(changed, "Not changed:") or ""):
        errors.append("What changed needs a 'Not changed: <scope left alone, or none>' line")

    ver = parts["Verification"]
    if not GATE_RE.search(ver):
        errors.append("Verification needs 'Gate: <suite> N/N ... <sha>'")
    if not LIVE_RE.search(ver):
        errors.append("Verification needs 'Live: run <id> ...' or 'Live: not run — <reason>'")
    if not (_line(ver, "Not verified:") or ""):
        errors.append("Verification needs 'Not verified: <what you knowingly did not check, or none>'")

    for line in parts["Follow-ups"].splitlines():
        s = line.strip()
        if s and s != "none" and not FOLLOWUP_ID_RE.search(s):
            errors.append(f"Follow-ups line needs a 'case <id>' or 'run <id>': {s!r}")

    notes = parts["Reviewer notes"]
    for prefix in ("Start here:", "Reproduce:"):
        if not (_line(notes, prefix) or ""):
            errors.append(f"Reviewer notes needs a '{prefix} ...' line")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"))
    ap.add_argument("--title")
    ap.add_argument("--body-file")
    ap.add_argument("--title-only", action="store_true", help="commit-msg hook: check the subject line only")
    args = ap.parse_args(argv)
    if args.title_only:
        errors = check_title(args.title or "")
        for e in errors:
            print(f"pr-check: {e}")
        return 1 if errors else 0
    if args.title is not None or args.body_file:
        title = args.title or ""
        body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else ""
    elif args.event:
        pr = json.loads(Path(args.event).read_text(encoding="utf-8")).get("pull_request", {})
        title, body = pr.get("title", ""), pr.get("body") or ""
    else:
        ap.error("give --event or --title/--body-file")
    errors = check_title(title) + check_body(body)
    for e in errors:
        print(f"pr-check: {e}")
    print("pr-check: ok" if not errors else f"pr-check: {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
