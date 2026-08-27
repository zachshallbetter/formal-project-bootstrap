#!/usr/bin/env python3
"""Instantiate Formal Project Bootstrap into a new or existing project."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

COPY_FILES = ["AGENTS.md", "NEW_AGENT_PROMPT.md"]
COPY_DIRS = ["schemas", ".agents/skills", "contracts"]
COPY_DOCS = [
    "AGENT_CAPABILITIES.md",
    "ALIGNMENT.md",
    "AUTHORITY_MODEL.md",
    "BOOTSTRAP_SEQUENCE.md",
    "CONFORMANCE.md",
    "CONTEXT_COMPILATION.md",
    "EVIDENCE_METHOD.md",
    "EXECUTION_PIPELINE.md",
    "EXECUTION_PROVIDER_CONTRACT.md",
    "EXISTING_PROJECT_ADOPTION.md",
    "FORMAL_RESOURCES.md",
    "INITIAL_EPICS_TEMPLATE.md",
    "LANDING_AND_PROMOTION.md",
    "MULTI_AGENT_COORDINATION.md",
    "NEGATIVE_KNOWLEDGE.md",
    "RECOVERY.md",
    "SKILLS_INDEX.md",
    "WORK_GRAPH.md",
]
SCRIPT_FILES = ["gen-context.py", "validate-bootstrap.py"]
RECORD_FILES = [
    "evidence.jsonl",
    "negative-results.jsonl",
    "deviations.jsonl",
    "alignment.jsonl",
]


def render_text(text: str, project_id: str, project_name: str) -> str:
    return text.replace("<PROJECT_ID>", project_id).replace("<PROJECT_NAME>", project_name)


def write_candidate(out: Path, rel: str, content: bytes, collisions: list[str]) -> None:
    target = out / rel
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return
    if target.read_bytes() == content:
        return
    candidate = out / ".formal-bootstrap" / "candidates" / rel
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(content)
    collisions.append(rel)


def copy_tree_non_destructive(src: Path, out: Path, rel: str, collisions: list[str]) -> None:
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        child_rel = str(Path(rel) / path.relative_to(src))
        write_candidate(out, child_rel, path.read_bytes(), collisions)


def append_alignment(out: Path, collisions: list[str]) -> None:
    if not collisions:
        return
    record = {
        "type": "bootstrap_collision",
        "status": "unresolved",
        "paths": sorted(collisions),
        "meaning": "Existing project content differed from bootstrap candidates and was preserved.",
        "requiredAction": "Reconcile authority and synthesize deliberately; do not copy over existing canonical state blindly.",
    }
    with (out / "records/alignment.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=["new", "existing"], default="new")
    parser.add_argument("--profile", action="append", default=[])
    args = parser.parse_args()

    out = Path(args.output).resolve()
    if args.mode == "new" and out.exists() and any(out.iterdir()):
        print(f"REFUSED: new-mode output is not empty: {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    if (out / ".formal-bootstrap.json").exists():
        print("REFUSED: project is already marked as initialized", file=sys.stderr)
        return 2

    (out / "records").mkdir(parents=True, exist_ok=True)
    for name in RECORD_FILES:
        (out / "records" / name).touch(exist_ok=True)

    collisions: list[str] = []

    for rel in COPY_FILES:
        content = render_text((ROOT / rel).read_text(encoding="utf-8"), args.id, args.name).encode()
        write_candidate(out, rel, content, collisions)

    for rel in COPY_DIRS:
        copy_tree_non_destructive(ROOT / rel, out, rel, collisions)

    for name in COPY_DOCS:
        write_candidate(out, f"docs/{name}", (ROOT / "docs" / name).read_bytes(), collisions)

    for name in SCRIPT_FILES:
        write_candidate(out, f"scripts/{name}", (ROOT / "scripts" / name).read_bytes(), collisions)

    intent = render_text(
        (ROOT / "PROJECT_INTENT_TEMPLATE.md").read_text(encoding="utf-8"), args.id, args.name
    ).encode()
    write_candidate(out, "PROJECT_INTENT.md", intent, collisions)

    profile = json.loads((ROOT / "PROJECT_PROFILE_TEMPLATE.json").read_text(encoding="utf-8"))
    profile["projectId"] = args.id
    profile["projectName"] = args.name
    profile["profileVersion"] = VERSION
    profile["operatingMode"] = args.mode
    profile["profiles"] = args.profile
    write_candidate(out, "PROJECT_PROFILE.json", (json.dumps(profile, indent=2) + "\n").encode(), collisions)

    context = json.loads((ROOT / "CONTEXT_SOURCES_TEMPLATE.json").read_text(encoding="utf-8"))
    write_candidate(out, "CONTEXT_SOURCES.json", (json.dumps(context, indent=2) + "\n").encode(), collisions)

    resources = render_text(
        (ROOT / "FORMAL_RESOURCE_MANIFEST_TEMPLATE.json").read_text(encoding="utf-8"),
        args.id,
        args.name,
    ).encode()
    write_candidate(out, "FORMAL_RESOURCE_MANIFEST.json", resources, collisions)

    bindings = render_text(
        (ROOT / "bindings/PROJECT_BINDINGS_TEMPLATE.yaml").read_text(encoding="utf-8"),
        args.id,
        args.name,
    ).encode()
    write_candidate(out, "bindings/PROJECT_BINDINGS.yaml", bindings, collisions)

    selected_profiles = []
    for name in args.profile:
        src = ROOT / "profiles" / name
        if not src.exists():
            print(f"REFUSED: unknown profile {name}", file=sys.stderr)
            return 2
        copy_tree_non_destructive(src, out, f"profiles/{name}", collisions)
        selected_profiles.append(name)

    if not (out / "README.md").exists():
        (out / "README.md").write_text(
            f"# {args.name}\n\nProject intent and operation are defined by `PROJECT_INTENT.md`, `AGENTS.md`, and `PROJECT_PROFILE.json`.\n",
            encoding="utf-8",
        )

    (out / "VERSION").write_text(VERSION + "\n", encoding="utf-8")

    marker = {
        "format": "2",
        "bootstrap": "formal-project-bootstrap",
        "bootstrapVersion": VERSION,
        "projectId": args.id,
        "projectName": args.name,
        "mode": args.mode,
        "profiles": selected_profiles,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "unresolvedBootstrapCollisions": sorted(collisions),
    }
    (out / ".formal-bootstrap.json").write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    append_alignment(out, collisions)

    if collisions:
        print("INITIALIZED WITH UNRESOLVED COLLISIONS:")
        for path in sorted(collisions):
            print(f"  {path}")
        print("Existing-project admission is incomplete until .formal-bootstrap/candidates and authority overlaps are reconciled.")
        return 3

    subprocess.check_call([sys.executable, str(out / "scripts/gen-context.py")], cwd=out)
    subprocess.check_call(
        [sys.executable, str(out / "scripts/validate-bootstrap.py"), "--check-context"], cwd=out
    )
    print(f"initialized {args.id} ({args.mode}) at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
