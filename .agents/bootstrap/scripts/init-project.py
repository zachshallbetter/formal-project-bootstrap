#!/usr/bin/env python3
"""Instantiate Formal Project Bootstrap into a new or existing project."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout import (  # noqa: E402
    PROTOCOL_RECORD_FILES, RECORD_FILES, REPOSITORY_ROOT as ROOT, TEMPLATES, Layout, release_machinery,
)

VERSION = (ROOT / ".agents/bootstrap/VERSION").read_text(encoding="utf-8").strip()
LAYOUT = Layout(Path("."), contained=True)          # relative paths for a new project
TEMPLATE = ROOT / TEMPLATES

GITIGNORE_LINES = [
    ".env", ".env.*", "!.env.example", ".env.local",
    ".agents/llms*.txt", "**/llms*.txt", "**/llm-full-docs*.txt", "**/llm-full-docs-all.zip",
    "**/llm-full-docs*/", ".agents/records/local/", ".agents/.upgrades/",
    "dist/", "build/", "target/", "out/", "node_modules/", "coverage/", "htmlcov/",
    ".next/", ".turbo/", ".vercel/", ".cache/", ".pytest_cache/", ".mypy_cache/",
    ".ruff_cache/", ".coverage*", ".reports/", "tmp/", "temp/", "__pycache__/", "*.py[cod]",
    "*.pyo", "*.egg-info/", "*.tmp", "*.temp", "*.bak", "*~", "*.tsbuildinfo", "*.log",
    "*.swp", "*.swo", "*.orig", "*.rej",
]
# Negations for paths a global core.excludesFile commonly ignores. Only the
# repository's own .gitignore can override a global ignore.
GITIGNORE_KEEP = ["!.agents/", "!**/.agents/", "!AGENTS.md"]


def render_text(text: str, project_id: str, project_name: str) -> str:
    return text.replace("<PROJECT_ID>", project_id).replace("<PROJECT_NAME>", project_name)


def render_readme(project_id: str, project_name: str) -> str:
    return f"""# {project_name}

Formal Project Bootstrap supplies project structure for explicit intent, authority, work, evidence, context, and recovery. Project-specific behavior and maturity must be documented from that project's own records.

**Project ID:** `{project_id}`

**Bootstrap version:** `{VERSION}`

This repository's purpose and authorized outcomes are defined in [`.agents/project/intent.md`](.agents/project/intent.md); its operating authority is declared in [`.agents/project/profile.json`](.agents/project/profile.json).

## Purpose and scope

Read [`.agents/project/intent.md`](.agents/project/intent.md) for the project objective and boundaries. Read [`.agents/project/profile.json`](.agents/project/profile.json) and [`.agents/project/bindings.yaml`](.agents/project/bindings.yaml) for authority, provider, and domain bindings. This README is an entry point and does not supersede those records.

## Quick start

1. Read the project intent, profile, and bindings before changing project state.
2. Follow [`.agents/bootstrap/docs/BOOTSTRAP_SEQUENCE.md`](.agents/bootstrap/docs/BOOTSTRAP_SEQUENCE.md) and reconcile existing authority and work.
3. Check the setup and the local context lock:

   ```bash
   .agents/acp/acp status
   .agents/bootstrap/bootstrap validate
   ```

Generate local searchable context when needed with `.agents/bootstrap/bootstrap context`. The generated `llms*.txt` exports are ignored and excluded from release archives.

## Repository structure

- [`AGENTS.md`](AGENTS.md) — contributor operating contract.
- [`.agents/project/`](.agents/project/) — intent, profile, bindings, contracts and rules this project owns.
- [`.agents/records/`](.agents/records/) — persistent evidence, negative results, deviations, and alignment records.
- [`.agents/acp/`](.agents/acp/) — the ACP client; start with its README.
- [`.agents/bootstrap/`](.agents/bootstrap/) — operating definitions, schemas, and context, validation and upgrade tooling.

Domain-specific source, tests, run commands, and additional records are documented by the project as they are established.

## Verification

`.agents/bootstrap/bootstrap validate` checks bootstrap structure and the source-bound context lock. Structural validation checks repository shape; project-specific implementation tests check executable behavior; empirical evaluation requires its own evidence and must not be inferred from either. Run the checks documented by the implementation or selected profiles.

## Status and limitations

Formal Project Bootstrap supplies operating scaffolding. Its presence does not imply that domain functionality is implemented, tested, independently reviewed, or empirically validated. Record those states with their evidence and limitations.
"""


def write_candidate(out: Path, rel: str, content: bytes, collisions: list[str]) -> None:
    target = out / rel
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return
    if target.read_bytes() == content:
        return
    candidate = out / LAYOUT.rel("candidates") / rel
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(content)
    collisions.append(rel)


def copy_tree_non_destructive(src: Path, out: Path, rel: str, collisions: list[str]) -> None:
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        child_rel = str(Path(rel) / path.relative_to(src))
        write_candidate(out, child_rel, path.read_bytes(), collisions)


def write_acp_wiring(out: Path, args, collisions: list[str]) -> None:
    """Commit-safe repository identity and board wiring; endpoint secrets stay machine-local."""
    board_lines = ["# ACP board binding for this repository. Committed; not a secret."]
    if args.acp_owner:
        board_lines.append(f"ACP_BOARD_OWNER={args.acp_owner}")
        board_lines.append(f"ACP_BOARD_NUMBER={args.acp_project}")
        board_lines.append(f"GH_PROJECT_OWNER={args.acp_owner}")
        board_lines.append(f"GH_PROJECT_NUMBER={args.acp_project}")
    if args.acp_repository:
        repo_owner, repo_name = args.acp_repository.split("/", 1)
        board_lines.append(f"ACP_REMOTE_URL=https://github.com/{repo_owner}/{repo_name}.git")
    if args.acp_owner or args.acp_repository:
        write_candidate(out, ".agents/board.env", ("\n".join(board_lines) + "\n").encode(), collisions)

    gitignore = out / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    additions = [line for line in GITIGNORE_LINES + GITIGNORE_KEEP if line not in existing]
    if additions:
        block = ["", "# formal-project-bootstrap: secrets stay out; AGENTS.md and the .agents/ tree stay in"] + additions
        merged = ("\n".join(existing + block) + "\n").encode()
        if gitignore.exists() and args.mode == "existing":
            # Existing authority is never rewritten in place; stage the merged candidate.
            write_candidate(out, ".gitignore", merged, collisions)
        else:
            gitignore.write_text(merged.decode(), encoding="utf-8")


def generate_acp_policy_proposal(out: Path, args) -> str:
    """Generate an unsigned, unregistered proposal for the exact repository identity."""
    proposal_rel = LAYOUT.rel("policy_proposal")
    proposal_path = out / proposal_rel
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    repo_owner, repo_name = args.acp_repository.split("/", 1)
    env = {
        **os.environ,
        "ACP_REMOTE_URL": f"https://github.com/{repo_owner}/{repo_name}.git",
    }
    result = subprocess.run(
        [sys.executable, str(out / ".agents/acp/acp"), "--project-root", str(out), "policy"],
        cwd=out,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(
            "ACP_SETUP_INCOMPLETE: policy proposal generation failed; run .agents/acp/acp policy after setup.",
            file=sys.stderr,
        )
        return "not generated; run .agents/acp/acp policy after setup"
    try:
        proposal = json.loads(result.stdout)
    except json.JSONDecodeError:
        proposal = None
    repository = proposal.get("repository") if isinstance(proposal, dict) else None
    boards = proposal.get("boards", []) if isinstance(proposal, dict) else []
    if (not isinstance(repository, dict)
            or repository.get("owner") != repo_owner
            or repository.get("name") != repo_name
            or (args.acp_owner and {"owner": args.acp_owner, "number": args.acp_project} not in boards)
            or (not args.acp_owner and boards)):
        print(
            "ACP_SETUP_INCOMPLETE: generated policy scope did not match the supplied repository and optional board; "
            "no proposal was written.",
            file=sys.stderr,
        )
        return "not generated; proposal scope did not match the supplied repository and board"
    proposal_bytes = (json.dumps(proposal, indent=2, sort_keys=True) + "\n").encode()
    if not proposal_path.exists():
        proposal_path.write_bytes(proposal_bytes)
        return proposal_rel
    if proposal_path.read_bytes() == proposal_bytes:
        return f"{proposal_rel} (already current)"
    candidate = out / LAYOUT.rel("candidates") / "acp-policy-proposal.json"
    if not candidate.exists():
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(proposal_bytes)
        print(
            "ACP_SETUP_INCOMPLETE: existing policy proposal preserved; "
            f"new proposal staged at {LAYOUT.rel('candidates')}/acp-policy-proposal.json.",
            file=sys.stderr,
        )
        return f"{LAYOUT.rel('candidates')}/acp-policy-proposal.json (existing proposal preserved)"
    print(
        "ACP_SETUP_INCOMPLETE: existing policy proposal and candidate preserved; review them before regenerating.",
        file=sys.stderr,
    )
    return "not generated; existing proposal and candidate preserved for review"


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
    with (out / LAYOUT.rel("records") / "alignment.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=["new", "existing"], default="new")
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--iepe-source", default=None)
    parser.add_argument("--iepe-revision", default=None)
    parser.add_argument("--iepe-version", default="0.2.0")
    parser.add_argument("--acp-endpoint-set", default="production",
                        help="select a named machine-local ACP endpoint set (default: production)")
    parser.add_argument("--acp-owner", default=None, help="GitHub owner of the ProjectsV2 board")
    parser.add_argument("--acp-project", type=int, default=None, help="ProjectsV2 board number")
    parser.add_argument("--acp-repository", default=None, metavar="OWNER/NAME",
                        help="GitHub repository identity; writes the canonical remote into .agents/board.env")
    args = parser.parse_args()
    if (args.acp_owner is None) != (args.acp_project is None):
        print("REFUSED: --acp-owner and --acp-project must be given together", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", args.acp_endpoint_set):
        print("REFUSED: --acp-endpoint-set must be a lowercase name of at most 64 characters", file=sys.stderr)
        return 2
    if args.acp_repository:
        parts = args.acp_repository.split("/")
        if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
            print("REFUSED: --acp-repository must be OWNER/NAME", file=sys.stderr)
            return 2
        if not all(all(ch.isalnum() or ch in "-_." for ch in part) for part in parts):
            print("REFUSED: --acp-repository contains unsupported characters", file=sys.stderr)
            return 2
    if args.acp_project is not None and args.acp_project < 1:
        print("REFUSED: --acp-project must be a positive ProjectsV2 board number", file=sys.stderr)
        return 2
    if "iepe" in args.profile and (not args.iepe_source or not args.iepe_revision):
        print("REFUSED: --profile iepe requires --iepe-source and --iepe-revision", file=sys.stderr)
        return 2

    final_out = Path(args.output).resolve()
    if args.mode == "new" and final_out.exists() and any(final_out.iterdir()):
        print(f"REFUSED: new-mode output is not empty: {final_out}", file=sys.stderr)
        return 2
    staging = None
    if args.mode == "new":
        final_out.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{final_out.name}.bootstrap-", dir=final_out.parent))
        out = staging
    else:
        out = final_out
        out.mkdir(parents=True, exist_ok=True)

    if any((out / marker).exists() for marker in (LAYOUT.rel("installation"), ".formal-bootstrap.json")):
        print("REFUSED: project is already marked as initialized", file=sys.stderr)
        return 2
    if (out / ".agents").is_symlink():
        print("REFUSED: .agents is a symbolic link; bootstrap needs a real .agents/ directory", file=sys.stderr)
        return 2

    records = out / LAYOUT.rel("records")
    records.mkdir(parents=True, exist_ok=True)
    for name in RECORD_FILES:
        (records / name).touch(exist_ok=True)
    if "esp-rcp" in args.profile:
        for name in PROTOCOL_RECORD_FILES:
            if name.endswith(".jsonl"):
                (records / name).touch(exist_ok=True)

    collisions: list[str] = []

    # Machinery: copied verbatim, at the same paths it has in the release.
    for rel, content in release_machinery(ROOT).items():
        write_candidate(out, rel, content, collisions)
    for executable in (".agents/acp/acp", ".agents/bootstrap/bootstrap"):
        if (out / executable).exists():
            (out / executable).chmod(0o755)

    # Project-owned: rendered once from the templates, never overwritten later.
    write_candidate(out, "AGENTS.md",
                    render_text((ROOT / "AGENTS.md").read_text(encoding="utf-8"), args.id, args.name).encode(),
                    collisions)
    write_candidate(out, LAYOUT.rel("intent"),
                    render_text((TEMPLATE / "intent.md").read_text(encoding="utf-8"), args.id, args.name).encode(),
                    collisions)
    for name, target in (("contracts", LAYOUT.rel("contracts")), ("rules", LAYOUT.rel("rules"))):
        copy_tree_non_destructive(TEMPLATE / name, out, target, collisions)

    profile = json.loads((TEMPLATE / "profile.json").read_text(encoding="utf-8"))
    profile["projectId"] = args.id
    profile["projectName"] = args.name
    profile["operatingMode"] = args.mode
    profile["profiles"] = args.profile
    profile["protocolAdapters"] = args.profile
    acp = profile.setdefault("authorizationProvider", {})
    acp["gatewayEndpointSet"] = args.acp_endpoint_set
    acp["status"] = "bound" if args.acp_owner and args.acp_project and args.acp_repository else "declared"
    acp["board"] = {"owner": args.acp_owner, "number": args.acp_project}
    write_candidate(out, LAYOUT.rel("profile"), (json.dumps(profile, indent=2) + "\n").encode(), collisions)

    context = json.loads((TEMPLATE / "context-sources.json").read_text(encoding="utf-8"))
    write_candidate(out, LAYOUT.rel("context_sources"), (json.dumps(context, indent=2) + "\n").encode(), collisions)

    resources = render_text((TEMPLATE / "formal-resources.json").read_text(encoding="utf-8"),
                            args.id, args.name).encode()
    write_candidate(out, LAYOUT.rel("formal_resources"), resources, collisions)

    if "iepe" in args.profile:
        reference = {
            "$schema": "https://iepe.dev/schema/protocol-reference.schema.json",
            "conformanceCommand": "python3 tools/validate.py",
            "protocolId": "IEPE-001", "protocolVersion": args.iepe_version,
            "relationship": "reference", "revision": args.iepe_revision, "source": args.iepe_source,
        }
        write_candidate(out, ".iepe/protocol-reference.json", (json.dumps(reference, indent=2) + "\n").encode(), collisions)

    if "esp-rcp" in args.profile:
        ledger = LAYOUT.rel("records")
        instance = {
            "format": "1", "instanceId": args.id,
            "protocol": {"id": "esp", "version": "0.3.0", "revisionOrDigest": "git:f1892e4"},
            "lifecycle": "bootstrap", "state": "unbound",
            "authority": {"owner": None, "qualification": None, "promotion": None}, "owner": None,
            "records": {name: f"{ledger}/{filename}" for name, filename in (
                ("campaigns", "campaigns.jsonl"), ("commitments", "commitments.jsonl"), ("evidence", "evidence.jsonl"),
                ("qualifications", "qualifications.jsonl"), ("receipts", "receipts.jsonl"),
                ("measurements", "measurements.jsonl"), ("learning", "learning.jsonl"),
                ("events", "external-state-events.jsonl"))},
            "lastReceiptId": None,
        }
        write_candidate(out, f"{ledger}/external-state.json", (json.dumps(instance, indent=2) + "\n").encode(), collisions)
        write_candidate(out, f"{ledger}/recipient.json", (json.dumps({"recipient": None}, indent=2) + "\n").encode(), collisions)

    bindings = render_text((TEMPLATE / "bindings.yaml").read_text(encoding="utf-8"), args.id, args.name).encode()
    write_candidate(out, LAYOUT.rel("bindings"), bindings, collisions)

    selected_profiles = []
    for name in args.profile:
        if not (ROOT / LAYOUT.rel("protocol_profiles") / name).exists():
            print(f"REFUSED: unknown profile {name}", file=sys.stderr)
            return 2
        selected_profiles.append(name)

    write_acp_wiring(out, args, collisions)

    if not (out / "README.md").exists():
        (out / "README.md").write_text(render_readme(args.id, args.name), encoding="utf-8")

    marker = {
        "format": "3",
        "bootstrap": "formal-project-bootstrap",
        "bootstrapVersion": VERSION,
        "projectId": args.id,
        "projectName": args.name,
        "mode": args.mode,
        "profiles": selected_profiles,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "source": "https://github.com/zachshallbetter/formal-project-bootstrap",
        "unresolvedBootstrapCollisions": sorted(collisions),
    }
    (out / LAYOUT.rel("installation")).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    append_alignment(out, collisions)

    if collisions:
        print("INITIALIZED WITH UNRESOLVED COLLISIONS:")
        for path in sorted(collisions):
            print(f"  {path}")
        print(f"Existing-project admission is incomplete until {LAYOUT.rel('candidates')} and authority overlaps are reconciled.")
        return 3

    complete_acp_binding = bool(args.acp_owner and args.acp_project and args.acp_repository)
    policy_proposal_status = generate_acp_policy_proposal(out, args) if args.acp_repository else None
    subprocess.check_call([sys.executable, str(out / LAYOUT.rel("bootstrap_scripts") / "gen-context.py")], cwd=out)
    subprocess.check_call(
        [sys.executable, str(out / LAYOUT.rel("bootstrap_scripts") / "validate-bootstrap.py"), "--check-context"],
        cwd=out,
    )
    if staging is not None:
        staging.rename(final_out)
        out = final_out
    print(f"initialized {args.id} ({args.mode}) at {out}")
    if args.acp_repository:
        print(f"ACP local wiring: repository identity is declared; endpoint set {args.acp_endpoint_set!r} is selected.")
        print(f"ACP policy proposal: {policy_proposal_status} (not registered; grants no authority).")
        print("ACP next step: run .agents/acp/acp status; it names anything still missing and the command that fixes it.")
        if complete_acp_binding:
            print("ACP owner step: register the policy (acp-gateway scripts/policy-admin.py register OWNER/NAME --apply).")
        else:
            print("ACP_SETUP_INCOMPLETE: board binding and endpoint credentials remain separate setup steps.")
            print("ACP board step: bind an existing ProjectsV2 board later; policy proposal generation does not require it.")
            print("ACP operator steps: register/sign and activate the proposal only through the reviewed policy workflow.")
    elif args.acp_owner or args.acp_repository:
        missing = []
        if not args.acp_owner or not args.acp_project:
            missing.append("--acp-owner and --acp-project (an existing ProjectsV2 board)")
        if not args.acp_repository:
            missing.append("--acp-repository OWNER/NAME")
        print("ACP_SETUP_INCOMPLETE: missing " + "; ".join(missing) + f"; machine endpoint set {args.acp_endpoint_set!r} must also exist.")
        print("The profile remains declared. Supply --acp-repository OWNER/NAME to generate an unsigned proposal without a board.")
    else:
        print("ACP_SETUP_NOT_CONFIGURED: run .agents/acp/acp init to bind the gateway, board, and repository identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
