#!/usr/bin/env python3
"""Refuse a change that re-runs an approach the project already disproved.

`records/negative-results.jsonl` records what was attempted, what was disproven,
and what would justify reopening it. Retention alone does not prevent
rediscovery: in an observed adoption, an approach recorded as closed was re-run,
reproduced the documented failure exactly, and was then proposed as a way
forward by the same worker that had recorded it hours earlier. A corpus informs;
a gate refuses.

A row participates only if it carries `detect` patterns, and most rows should
not. A marker must mean a retry and nothing else. Rows whose evidence is real
but whose retry has no reliable textual signature stay as knowledge and set
`"gate": false` with a reason, so the absence is a recorded decision rather than
an oversight. Gating a row whose evidence is narrower than the rule would
entrench a conclusion the evidence does not support.

It reads the diff, not the tree. A retry is something a change *adds*; a
repository that documents a closed approach mentions it everywhere, correctly.
The first implementation scanned the tree and produced findings exclusively
against files doing their job: the intent document naming the constraint, a
source comment warning against it, the ledger itself. Prose files and comment
lines are therefore excluded.

Overriding is lawful rather than forbidden: record a deviation naming the row in
`records/deviations.jsonl` (AGENTS.md 10). The governing state then changes
explicitly instead of forcing a choice between standing doctrine and an ad hoc
instruction.

    python3 scripts/check-negative-results.py               # working tree vs HEAD
    python3 scripts/check-negative-results.py origin/main   # a branch, for CI
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "records/negative-results.jsonl"
DEVIATIONS = ROOT / "records/deviations.jsonl"

# Where a closed approach is *described* rather than performed. A ledger entry,
# a design doc and a project-intent constraint all name what is closed; that is
# their job.
ALWAYS_SKIP = ("records/", "docs/", "datasets/", ".agents/", ".formal-bootstrap/",
               "scripts/check-negative-results.py")

# Prose files state what is excluded; they do not execute it.
PROSE_SUFFIXES = (".md", ".txt", ".json", ".jsonl", ".yaml", ".yml")

COMMENT = re.compile(r"^\s*(//|#|\*|/\*|--|<!--)")


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"{path.name}:{n}: unparseable, refusing to pass: {e}", file=sys.stderr)
            raise SystemExit(3)
    return out


def waived() -> dict[str, str]:
    """Row ids with a live deviation, mapped to the stated reason."""
    now = dt.datetime.now(dt.timezone.utc)
    live: dict[str, str] = {}
    for d in rows(DEVIATIONS):
        ref = d.get("ruleRef")
        if not ref:
            continue
        expires = d.get("expiresAt")
        if expires:
            try:
                if dt.datetime.fromisoformat(expires.replace("Z", "+00:00")) <= now:
                    continue
            except ValueError:
                continue        # an unparseable expiry is not a waiver
        live[ref] = d.get("reason", "(no reason recorded)")
    return live


def added_lines(base: str | None) -> list[tuple[str, int, str]]:
    """Lines this change introduces, as (path, line, text).

    A retry is something a change *adds*. Scanning the whole tree asks whether a
    closed approach is mentioned anywhere, and the answer is always yes — the
    ledger, the design docs and the intent constraints all name what is closed.
    The first version of this check did exactly that and produced seven findings,
    every one of them a file correctly documenting a closed row.
    """
    args = ["git", "-C", str(ROOT), "diff", "--unified=0", "--no-color"]
    args.append(base) if base else args.extend(["HEAD"])
    diff = subprocess.run(args, capture_output=True, text=True, check=True).stdout

    # Untracked files are wholly new, so every line in them is added.
    untracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True).stdout.split()

    out: list[tuple[str, int, str]] = []
    path, line_no = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            path, line_no = raw[6:], 0
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line_no = int(m.group(1)) if m else 0
        elif raw.startswith("+") and path:
            out.append((path, line_no, raw[1:]))
            line_no += 1

    for rel in untracked:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out.extend((rel, i, l) for i, l in enumerate(text.splitlines(), 1))

    return [(p, n, t) for p, n, t in out
            if not p.startswith(ALWAYS_SKIP)
            and not p.endswith(PROSE_SUFFIXES)
            and not COMMENT.match(t)]


def main() -> int:
    ledger = rows(LEDGER)
    gated = [r for r in ledger if r.get("detect")]
    if not ledger:
        print("no negative results recorded; nothing to check")
        return 0

    base = sys.argv[1] if len(sys.argv) > 1 else None
    changes = added_lines(base)
    findings: list[tuple[dict, str, str, int]] = []

    for row in gated:
        allow = row.get("allow", [])
        patterns = [re.compile(p, re.IGNORECASE) for p in row["detect"]]
        for rel, line, text in changes:
            if any(fnmatch.fnmatch(rel, a) for a in allow):
                continue
            for pat in patterns:
                m = pat.search(text)
                if m:
                    findings.append((row, rel, m.group(0), line))
                    break

    live = waived()
    blocking = [f for f in findings if f[0]["id"] not in live]

    for row, rel, hit, line in findings:
        note = f"  WAIVED by deviation: {live[row['id']]}" if row["id"] in live else ""
        print(f"\n{'-' if note else '!'} {row['id']}  {rel}:{line}  matched {hit!r}{note}")
        if note:
            continue
        print(f"    attempted: {row['attempted']}")
        print(f"    disproven: {row['disproven']}")
        print(f"    evidence:  {row['evidence']}")
        print(f"    reopen if: {row['reopen']}")

    considered = len(gated)
    print(f"\nchecked {len(changes)} added code lines against {considered} gated rows "
          f"({len(ledger) - considered} recorded but not gated)")
    if blocking:
        print(f"REFUSED: {len(blocking)} closed approach(es) reintroduced.\n"
              f"Reopen the row with new evidence, or record a deviation naming it "
              f"in records/deviations.jsonl.", file=sys.stderr)
        return 1
    print("OK no closed approach reintroduced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
