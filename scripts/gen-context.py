#!/usr/bin/env python3
"""Deterministically compile canonical project sources into agent context projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
POLICY_PATH = ROOT / "CONTEXT_SOURCES.json"
FALLBACK_POLICY_PATH = ROOT / "CONTEXT_SOURCES_TEMPLATE.json"
AGENTS = ROOT / ".agents"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_git(path: Path, args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def one_repo_state(path: Path, rel: str) -> dict | None:
    commit = run_git(path, ["rev-parse", "HEAD"])
    if not commit:
        return None
    branch = run_git(path, ["branch", "--show-current"]) or None
    status = run_git(path, ["status", "--porcelain"])
    remote = run_git(path, ["remote", "get-url", "origin"])
    return {
        "path": rel,
        "commit": commit,
        "branch": branch,
        "dirty": bool(status),
        "remote": remote,
    }


def repository_state() -> dict:
    """Capture provenance only; context validity is source-digest based.

    Exact HEAD cannot be a validity predicate for tracked generated files without
    creating a self-reference. We still retain the observed Git state so agents can
    identify the checkout that produced the projection.
    """
    root_state = one_repo_state(ROOT, ".")
    if not root_state:
        return {"available": False, "validationRole": "provenance", "repositories": []}

    repos = [root_state]
    raw = run_git(ROOT, ["submodule", "status", "--recursive"])
    if raw:
        for line in raw.splitlines():
            parts = line.strip().lstrip("-+U").split()
            if len(parts) < 2:
                continue
            rel = parts[1]
            state = one_repo_state(ROOT / rel, rel)
            if state:
                repos.append(state)
            else:
                repos.append(
                    {
                        "path": rel,
                        "commit": parts[0],
                        "branch": None,
                        "dirty": None,
                        "remote": None,
                    }
                )
    return {"available": True, "validationRole": "provenance", "repositories": repos}


def load_policy() -> dict:
    path = POLICY_PATH if POLICY_PATH.exists() else FALLBACK_POLICY_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def source_files(policy: dict) -> list[tuple[str, bytes]]:
    ex_dirs = set(policy["excludeDirectories"])
    ex_paths = set(policy["excludePaths"])
    exts = set(policy["includeExtensions"])
    include_files = set(policy.get("includeFiles", []))
    max_bytes = int(policy["maxFileBytes"])
    include_vendor = bool(policy.get("includeVendor", True))
    result: list[tuple[str, bytes]] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        parts = rel.split("/")
        if any(part in ex_dirs for part in parts[:-1]):
            continue
        if not include_vendor and parts[0] == "vendor":
            continue
        if rel in ex_paths:
            continue
        if rel not in include_files and path.suffix.lower() not in exts:
            continue
        if path.stat().st_size > max_bytes:
            continue
        try:
            data = path.read_bytes()
            data.decode("utf-8")
        except Exception:
            continue
        result.append((rel, data))

    return sorted(result, key=lambda item: item[0])


def build() -> tuple[dict, str, str]:
    policy = load_policy()
    sources = source_files(policy)
    entries = [
        {"path": rel, "bytes": len(data), "sha256": sha(data)} for rel, data in sources
    ]
    aggregate = sha(
        "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    )
    repos = repository_state()
    lock = {
        "format": "2",
        "generatorVersion": VERSION,
        "root": ".",
        "validityBasis": "aggregate-source-digest",
        "repositoryState": repos,
        "aggregateSourceDigest": aggregate,
        "sources": entries,
    }

    index = [
        "# Project Context Index",
        f"> Generator: {VERSION}",
        f"> Source digest: `{aggregate}`",
        "",
        "> Generated projection. Canonical sources remain authoritative.",
        "",
    ]
    full = [
        "# PROJECT COMPILED CONTEXT",
        f"Generator: {VERSION}",
        f"Source digest: {aggregate}",
        "",
        "> Generated projection. Canonical sources remain authoritative.",
        "",
    ]

    for rel, data in sources:
        digest = sha(data)
        index.append(f"- `{rel}` | {len(data)} bytes | `{digest}`")
        full.extend(["", "=" * 72, f"FILE: {rel}", "=" * 72, "", data.decode("utf-8")])

    return lock, "\n".join(index) + "\n", "\n".join(full) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    lock, index, full = build()
    AGENTS.mkdir(parents=True, exist_ok=True)

    if args.check:
        lock_path = AGENTS / "context-lock.json"
        if not lock_path.exists():
            print("STALE: context lock missing", file=sys.stderr)
            return 2
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        if current.get("aggregateSourceDigest") != lock["aggregateSourceDigest"]:
            print("STALE: source digest differs", file=sys.stderr)
            return 2
        if current.get("generatorVersion") != VERSION:
            print("STALE: generator version differs", file=sys.stderr)
            return 2
        if not (AGENTS / "llms.txt").exists() or not (AGENTS / "llms-full.txt").exists():
            print("STALE: generated corpus missing", file=sys.stderr)
            return 2
        if (AGENTS / "llms.txt").read_text(encoding="utf-8") != index:
            print("STALE: llms.txt differs", file=sys.stderr)
            return 2
        if (AGENTS / "llms-full.txt").read_text(encoding="utf-8") != full:
            print("STALE: llms-full.txt differs", file=sys.stderr)
            return 2
        print(f"OK {lock['aggregateSourceDigest']}")
        return 0

    (AGENTS / "context-lock.json").write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )
    (AGENTS / "llms.txt").write_text(index, encoding="utf-8")
    (AGENTS / "llms-full.txt").write_text(full, encoding="utf-8")
    print(f"generated {len(lock['sources'])} sources {lock['aggregateSourceDigest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
