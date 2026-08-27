#!/usr/bin/env python3
"""Validate either the bootstrap repository or an initialized project."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = [
    "VERSION",
    "AGENTS.md",
    "docs/AUTHORITY_MODEL.md",
    "docs/ALIGNMENT.md",
    "docs/BOOTSTRAP_SEQUENCE.md",
    "docs/CONTEXT_COMPILATION.md",
    "docs/EVIDENCE_METHOD.md",
    "docs/EXECUTION_PIPELINE.md",
    "docs/EXECUTION_PROVIDER_CONTRACT.md",
    "docs/FORMAL_RESOURCES.md",
    "docs/LANDING_AND_PROMOTION.md",
    "docs/MULTI_AGENT_COORDINATION.md",
    "docs/NEGATIVE_KNOWLEDGE.md",
    "docs/RECOVERY.md",
    "docs/SKILLS_INDEX.md",
    "docs/WORK_GRAPH.md",
    "schemas/agent-message.schema.json",
    "schemas/context-lock.schema.json",
    "schemas/formal-resource-manifest.schema.json",
    "schemas/work-disposition.schema.json",
    "scripts/gen-context.py",
]
REPOSITORY_ONLY = [
    "README.md",
    "AUTHORITY.md",
    "VERSIONING.md",
    "GOVERNANCE.md",
    "PROJECT_INTENT_TEMPLATE.md",
    "PROJECT_PROFILE_TEMPLATE.json",
    "FORMAL_RESOURCE_MANIFEST_TEMPLATE.json",
    "CONTEXT_SOURCES_TEMPLATE.json",
    "bindings/PROJECT_BINDINGS_TEMPLATE.yaml",
    "scripts/init-project.py",
    "scripts/package-release.py",
]
PROJECT_ONLY = [
    "README.md",
    ".formal-bootstrap.json",
    "PROJECT_INTENT.md",
    "PROJECT_PROFILE.json",
    "FORMAL_RESOURCE_MANIFEST.json",
    "CONTEXT_SOURCES.json",
    "bindings/PROJECT_BINDINGS.yaml",
    "records/evidence.jsonl",
    "records/negative-results.jsonl",
    "records/deviations.jsonl",
    "records/alignment.jsonl",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-context", action="store_true")
    args = parser.parse_args()

    project_mode = (ROOT / ".formal-bootstrap.json").exists()
    required = COMMON + (PROJECT_ONLY if project_mode else REPOSITORY_ONLY)
    missing = [path for path in required if not (ROOT / path).exists()]
    if missing:
        print("MISSING:", *missing, sep="\n  ", file=sys.stderr)
        return 2

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not version or version.startswith("v"):
        print("INVALID: VERSION must contain bare SemVer", file=sys.stderr)
        return 2

    json_paths = [
        "schemas/agent-message.schema.json",
        "schemas/context-lock.schema.json",
        "schemas/formal-resource-manifest.schema.json",
        "schemas/work-disposition.schema.json",
    ]
    if project_mode:
        json_paths += [
            "PROJECT_PROFILE.json",
            "FORMAL_RESOURCE_MANIFEST.json",
            "CONTEXT_SOURCES.json",
            ".formal-bootstrap.json",
        ]
    else:
        json_paths += [
            "PROJECT_PROFILE_TEMPLATE.json",
            "FORMAL_RESOURCE_MANIFEST_TEMPLATE.json",
            "CONTEXT_SOURCES_TEMPLATE.json",
        ]

    for path in json_paths:
        json.loads((ROOT / path).read_text(encoding="utf-8"))

    profile_path = ROOT / ("PROJECT_PROFILE.json" if project_mode else "PROJECT_PROFILE_TEMPLATE.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("profileVersion") != version:
        print("INVALID: project profile version != VERSION", file=sys.stderr)
        return 2

    resource_path = ROOT / ("FORMAL_RESOURCE_MANIFEST.json" if project_mode else "FORMAL_RESOURCE_MANIFEST_TEMPLATE.json")
    resources = json.loads(resource_path.read_text(encoding="utf-8"))
    expected_id = profile.get("projectId")
    if resources.get("projectId") != expected_id:
        print("INVALID: formal resource manifest projectId != profile projectId", file=sys.stderr)
        return 2

    if args.check_context:
        rc = subprocess.call([sys.executable, str(ROOT / "scripts/gen-context.py"), "--check"])
        if rc:
            return rc

    mode = "project" if project_mode else "repository"
    print(f"OK {mode} structure v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
