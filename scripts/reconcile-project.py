#!/usr/bin/env python3
"""Inspect a repository and report bootstrap adoption state without writing files."""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

def git(project: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=project, text=True, capture_output=True, check=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(json.dumps({"error": f"project is not a directory: {project}"}))
        return 2
    findings: list[dict[str, str]] = []
    marker = profile = None
    for label, rel in (("marker", ".formal-bootstrap.json"), ("profile", "PROJECT_PROFILE.json")):
        path = project / rel
        if not path.exists():
            findings.append({"severity": "missing", "path": rel, "meaning": f"bootstrap {label} is absent"})
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            findings.append({"severity": "error", "path": rel, "meaning": f"bootstrap {label} is unreadable: {exc}"})
            continue
        if label == "marker": marker = value
        else: profile = value
    expected = ["AGENTS.md", ".agents", "CONTEXT_SOURCES.json", ".agents/context-lock.json", "scripts/gen-context.py", "scripts/validate-bootstrap.py", "scripts/acp.py", "scripts/upgrade-project.py", "scripts/reconcile-project.py", "schemas", "contracts", "docs/CONFORMANCE.md"]
    artifacts = {path: ("present" if (project / path).exists() else "missing") for path in expected}
    for path, state in artifacts.items():
        if state == "missing": findings.append({"severity": "missing", "path": path, "meaning": "expected bootstrap or governance artifact is absent"})
    if marker and profile:
        if marker.get("projectId") != profile.get("projectId"): findings.append({"severity": "conflict", "path": ".formal-bootstrap.json/PROJECT_PROFILE.json", "meaning": "project identifiers differ"})
        if marker.get("bootstrapVersion") != profile.get("profileVersion"): findings.append({"severity": "conflict", "path": ".formal-bootstrap.json/PROJECT_PROFILE.json", "meaning": "bootstrap versions differ"})
    result = {"format": "1", "project": str(project), "git": {"root": git(project, "rev-parse", "--show-toplevel"), "head": git(project, "rev-parse", "HEAD"), "branch": git(project, "branch", "--show-current"), "status": git(project, "status", "--short"), "remote": git(project, "config", "--get", "remote.origin.url")}, "bootstrap": {"initialized": marker is not None and profile is not None, "marker": marker, "profile": profile, "artifacts": artifacts}, "findings": findings}
    result["reconcileRequired"] = any(item["severity"] in {"missing", "conflict", "error"} for item in findings)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 1 if result["reconcileRequired"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
