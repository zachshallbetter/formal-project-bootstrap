from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


class RepositoryTests(unittest.TestCase):
    def run_ok(self, *args: str, cwd: Path = ROOT, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True,
                              env={**os.environ, **env} if env else None)

    def test_version_is_single_source_for_profile(self):
        profile = json.loads((ROOT / "PROJECT_PROFILE_TEMPLATE.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["profileVersion"], VERSION)
        self.assertIn(f"**Version:** {VERSION}", (ROOT / "README.md").read_text(encoding="utf-8"))
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{VERSION}"', pyproject)
        self.assertIn(f"v{VERSION}", (ROOT / "docs/STATUS.md").read_text(encoding="utf-8"))

    def test_context_generation_is_deterministic(self):
        self.run_ok(sys.executable, "scripts/gen-context.py")
        first_index = (ROOT / ".agents/llms.txt").read_bytes()
        first_full = (ROOT / ".agents/llms-full.txt").read_bytes()
        first_lock = json.loads((ROOT / ".agents/context-lock.json").read_text(encoding="utf-8"))
        self.run_ok(sys.executable, "scripts/gen-context.py")
        second_lock = json.loads((ROOT / ".agents/context-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(first_index, (ROOT / ".agents/llms.txt").read_bytes())
        self.assertEqual(first_full, (ROOT / ".agents/llms-full.txt").read_bytes())
        self.assertEqual(first_lock["aggregateSourceDigest"], second_lock["aggregateSourceDigest"])
        self.assertEqual(first_lock["validityBasis"], "aggregate-source-digest")
        self.assertEqual(first_lock["repositoryState"]["validationRole"], "provenance")

    def test_context_generator_excludes_sensitive_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "project"
            (out / "scripts").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/gen-context.py", out / "scripts/gen-context.py")
            (out / "VERSION").write_text("0.6.0\n", encoding="utf-8")
            (out / "CONTEXT_SOURCES.json").write_text(json.dumps({
                "excludeDirectories": [".git", ".agents"],
                "excludePaths": [],
                "includeExtensions": [".txt"],
                "maxFileBytes": 1024,
            }), encoding="utf-8")
            (out / "public.txt").write_text("public\n", encoding="utf-8")
            (out / ".env.production").write_text("TOP_SECRET\n", encoding="utf-8")
            self.run_ok(sys.executable, "scripts/gen-context.py", cwd=out)
            corpus = (out / ".agents/llms-full.txt").read_text(encoding="utf-8")
            self.assertIn("public", corpus)
            self.assertNotIn("TOP_SECRET", corpus)

    def test_context_generator_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "project"
            (out / "scripts").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/gen-context.py", out / "scripts/gen-context.py")
            (out / "VERSION").write_text("0.6.0\n", encoding="utf-8")
            (out / "CONTEXT_SOURCES.json").write_text(json.dumps({
                "excludeDirectories": [".git", ".agents"],
                "excludePaths": [],
                "includeExtensions": [".txt"],
                "maxFileBytes": 1024,
            }), encoding="utf-8")
            outside = Path(tmp) / "outside.txt"
            outside.write_text("OUTSIDE_BOUNDARY\n", encoding="utf-8")
            (out / "linked.txt").symlink_to(outside)
            self.run_ok(sys.executable, "scripts/gen-context.py", cwd=out)
            corpus = (out / ".agents/llms-full.txt").read_text(encoding="utf-8")
            self.assertNotIn("OUTSIDE_BOUNDARY", corpus)

    def test_context_check_does_not_create_agents_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "project"
            (out / "scripts").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/gen-context.py", out / "scripts/gen-context.py")
            (out / "VERSION").write_text("0.6.0\n", encoding="utf-8")
            (out / "CONTEXT_SOURCES.json").write_text(json.dumps({
                "excludeDirectories": [".git", ".agents"],
                "excludePaths": [],
                "includeExtensions": [".txt"],
                "maxFileBytes": 1024,
            }), encoding="utf-8")
            cp = subprocess.run(
                [sys.executable, "scripts/gen-context.py", "--check"],
                cwd=out, text=True, capture_output=True,
            )
            self.assertEqual(cp.returncode, 2)
            self.assertFalse((out / ".agents").exists())

    def test_upgrade_plans_applies_and_rolls_back_safe_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            release = Path(tmp) / "release"
            self.run_ok(
                sys.executable,
                "scripts/init-project.py",
                "--name", "Upgrade Fixture",
                "--id", "upgrade-fixture",
                "--mode", "new",
                "--output", str(project),
            )
            shutil.copytree(
                ROOT,
                release,
                ignore=shutil.ignore_patterns(".venv", ".git", ".wt", "dist", "build", "__pycache__"),
            )
            (release / "VERSION").write_text("0.5.4\n", encoding="utf-8")
            (release / "docs/ALIGNMENT.md").write_text(
                (release / "docs/ALIGNMENT.md").read_text(encoding="utf-8") + "\nUpgrade fixture marker.\n",
                encoding="utf-8",
            )
            upgrade = ROOT / "scripts/upgrade-project.py"
            plan = subprocess.run(
                [sys.executable, str(upgrade), "--project", str(project), "--from", str(release),
                 "--base", str(ROOT), "--check"],
                text=True, capture_output=True,
            )
            self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
            self.assertFalse((project / ".formal-bootstrap/upgrades/0.5.4/plan.json").exists())
            self.run_ok(
                sys.executable, str(upgrade), "--project", str(project), "--from", str(release),
                "--base", str(ROOT), "--apply",
            )
            self.assertEqual((project / "VERSION").read_text(encoding="utf-8").strip(), "0.5.4")
            self.assertIn("Upgrade fixture marker", (project / "docs/ALIGNMENT.md").read_text(encoding="utf-8"))
            self.run_ok(sys.executable, str(upgrade), "--project", str(project), "--from", str(release), "--verify")
            self.run_ok(sys.executable, str(upgrade), "--project", str(project), "--from", str(release), "--rollback")
            self.assertEqual((project / "VERSION").read_text(encoding="utf-8").strip(), VERSION)
            self.assertNotIn("Upgrade fixture marker", (project / "docs/ALIGNMENT.md").read_text(encoding="utf-8"))

    def test_upgrade_keeps_project_edits_replaces_machinery_and_finds_its_base_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            release = Path(tmp) / "release"
            self.run_ok(sys.executable, "scripts/init-project.py", "--name", "Owned Fixture",
                        "--id", "owned-fixture", "--mode", "new", "--output", str(project))
            shutil.copytree(ROOT, release, ignore=shutil.ignore_patterns(
                ".venv", ".git", ".wt", "dist", "build", "__pycache__"))
            git = ["git", "-C", str(release), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                   "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false"]
            self.run_ok("git", "init", "-q", str(release))
            self.run_ok(*git, "add", "-A")
            self.run_ok(*git, "commit", "-q", "-m", "base")
            self.run_ok(*git, "tag", f"v{VERSION}")
            (release / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            for rel in ("AGENTS.md", "scripts/acp.py"):
                path = release / rel
                path.write_text(path.read_text(encoding="utf-8") + "\n# release change\n", encoding="utf-8")
            agents = project / "AGENTS.md"
            agents.write_text(agents.read_text(encoding="utf-8") + "\n## Project rule\n", encoding="utf-8")
            client = project / "scripts/acp.py"
            client.write_text(client.read_text(encoding="utf-8") + "\n# stray local edit\n", encoding="utf-8")
            (project / "records/local-work-items.jsonl").unlink()
            (project / "records/evidence.jsonl").write_text('{"kept": true}\n', encoding="utf-8")

            upgrade = ROOT / "scripts/upgrade-project.py"
            cp = subprocess.run([sys.executable, str(upgrade), "--project", str(project), "--from", str(release),
                                 "--apply"], text=True, capture_output=True)
            self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
            planned = json.JSONDecoder().raw_decode(cp.stdout)[0]
            self.assertIn(f"at tag v{VERSION}", planned["base"])
            self.assertEqual(planned["classification"]["conflicts"], ["AGENTS.md"])
            self.assertEqual(planned["classification"]["replacedLocalEdits"], ["scripts/acp.py"])
            self.assertIn("docs/ALIGNMENT.md", planned["classification"]["unchanged"])
            self.assertIn("records/local-work-items.jsonl", planned["classification"]["additions"])
            self.assertEqual((project / "records/evidence.jsonl").read_text(encoding="utf-8"), '{"kept": true}\n')

            self.assertIn("## Project rule", agents.read_text(encoding="utf-8"))
            self.assertNotIn("# release change", agents.read_text(encoding="utf-8"))
            staged = project / ".formal-bootstrap/upgrades/9.9.9/candidates/AGENTS.md"
            self.assertIn("# release change", staged.read_text(encoding="utf-8"))
            self.assertIn("# release change", client.read_text(encoding="utf-8"))
            self.assertNotIn("# stray local edit", client.read_text(encoding="utf-8"))
            backup = project / ".formal-bootstrap/upgrades/9.9.9/backup/scripts/acp.py"
            self.assertIn("# stray local edit", backup.read_text(encoding="utf-8"))
            self.assertIn("project-owned files kept as they are", cp.stderr)
            self.assertIn("scripts/acp.py", cp.stderr)
            self.assertEqual((project / ".formal-bootstrap/upgrades/.gitignore").read_text(encoding="utf-8").splitlines()[-1], "*")

    def test_context_check_accepts_sources_with_crlf_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            self.run_ok(sys.executable, "scripts/init-project.py", "--name", "CRLF Fixture",
                        "--id", "crlf-fixture", "--mode", "new", "--output", str(project))
            (project / "docs/windows-notes.md").write_bytes(b"# Notes\r\n\r\nWritten on Windows.\r\n")
            self.run_ok(sys.executable, "scripts/gen-context.py", cwd=project)
            self.assertIn(b"\r\n", (project / ".agents/llms-full.txt").read_bytes())
            self.run_ok(sys.executable, "scripts/gen-context.py", "--check", cwd=project)

    def test_readme_standard_accepts_equivalent_section_names(self):
        spec = importlib.util.spec_from_file_location("validate_bootstrap", ROOT / "scripts/validate-bootstrap.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text("# Fixture\n\nA small fixture project used to check README section names.\n\n"
                              "## Install\n\nx\n\n## Project map\n\nx\n\n## Development\n\nx\n\n"
                              "## Current status\n\nx\n", encoding="utf-8")
            self.assertEqual(module.readme_findings(readme), [])

    def test_upgrade_replaces_legacy_gateway_env_binding_with_endpoint_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            self.run_ok(sys.executable, "scripts/init-project.py", "--name", "Legacy ACP Fixture",
                        "--id", "legacy-acp-fixture", "--output", str(project))
            profile_path = project / "PROJECT_PROFILE.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            provider = profile["authorizationProvider"]
            provider.pop("gatewayEndpointSet")
            provider["gatewayUrlEnv"] = "ACP_GATEWAY_URL"
            provider["gatewayTokenEnv"] = "ACP_GATEWAY_TOKEN"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            spec = importlib.util.spec_from_file_location("upgrade_project", ROOT / "scripts/upgrade-project.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            target = module.source_map(ROOT, project, "legacy-acp-fixture", "Legacy ACP Fixture")
            upgraded = json.loads(target["PROJECT_PROFILE.json"])
            upgraded_provider = upgraded["authorizationProvider"]
            self.assertEqual(upgraded_provider["gatewayEndpointSet"], "production")
            self.assertNotIn("gatewayUrlEnv", upgraded_provider)
            self.assertNotIn("gatewayTokenEnv", upgraded_provider)

    def test_initializer_produces_valid_new_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "project"
            self.run_ok(
                sys.executable,
                "scripts/init-project.py",
                "--name", "Fixture Project",
                "--id", "fixture-project",
                "--mode", "new",
                "--output", str(out),
            )
            marker = json.loads((out / ".formal-bootstrap.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["bootstrapVersion"], VERSION)
            self.assertEqual(marker["mode"], "new")
            profile = json.loads((out / "PROJECT_PROFILE.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["projectId"], "fixture-project")
            self.assertEqual(profile["operatingMode"], "new")
            resources = json.loads((out / "FORMAL_RESOURCE_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(resources["projectId"], "fixture-project")
            for name in ["evidence.jsonl", "negative-results.jsonl", "deviations.jsonl", "alignment.jsonl", "local-work-items.jsonl"]:
                self.assertTrue((out / "records" / name).exists())
            self.run_ok(sys.executable, "scripts/validate-bootstrap.py", "--check-context", cwd=out)

    def test_reconcile_inventory_is_read_only_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            self.run_ok(
                sys.executable, "scripts/init-project.py", "--name", "Inventory Fixture",
                "--id", "inventory-fixture", "--mode", "new", "--output", str(project),
            )
            # Never read this machine's real endpoint registry: give the run its own.
            registry = Path(tmp) / "acp-endpoints.json"
            endpoint_set = json.loads((project / "PROJECT_PROFILE.json").read_text(encoding="utf-8"))[
                "authorizationProvider"]["gatewayEndpointSet"]
            registry.write_text(json.dumps({"formatVersion": 1, "endpointSets": {endpoint_set: [
                {"name": "vercel", "url": "https://acp.example.invalid", "keychainAccount": "ACP_GATEWAY_TOKEN"}]}}),
                encoding="utf-8")
            registry.chmod(0o600)
            missing = json.loads(self.run_ok(
                sys.executable, "scripts/reconcile-project.py", "--project", str(project),
                env={"ACP_ENDPOINT_REGISTRY": str(Path(tmp) / "absent-registry.json")}).stdout)
            self.assertTrue(any("configure the selected machine-local ACP endpoint set" in step
                                for step in missing["acpIntegration"]["setup"]["nextSteps"]))
            before = subprocess.run(["git", "status", "--short"], cwd=project, text=True, capture_output=True).stdout
            result = self.run_ok(sys.executable, "scripts/reconcile-project.py", "--project", str(project),
                                 env={"ACP_ENDPOINT_REGISTRY": str(registry)})
            after = subprocess.run(["git", "status", "--short"], cwd=project, text=True, capture_output=True).stdout
            inventory = json.loads(result.stdout)
            self.assertTrue(inventory["bootstrap"]["initialized"])
            self.assertFalse(inventory["reconcileRequired"])
            self.assertEqual(inventory["acpIntegration"]["status"], "formal-project-bootstrap")
            self.assertEqual(inventory["acpIntegration"]["setup"]["authorization"], "NOT_EVALUATED")
            self.assertEqual(inventory["acpIntegration"]["setup"]["policyActivation"], "NOT_VERIFIED")
            self.assertEqual(inventory["acpIntegration"]["setup"]["boardBinding"], "unbound")
            self.assertEqual(
                inventory["acpIntegration"]["setup"]["endpointSet"]["credentialAuthentication"],
                "NOT_VERIFIED",
            )
            self.assertTrue(any(
                "acp-check.py --json" in step
                for step in inventory["acpIntegration"]["setup"]["nextSteps"]
            ))
            self.assertEqual(before, after)

    def test_reconcile_identifies_existing_legacy_acp_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "legacy"
            (project / "scripts").mkdir(parents=True)
            (project / "scripts/acp.py").write_text("# project-specific ACP client\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "scripts/reconcile-project.py", "--project", str(project)],
                cwd=ROOT, text=True, capture_output=True,
            )
            inventory = json.loads(result.stdout)
            self.assertEqual(inventory["acpIntegration"]["status"], "existing-or-legacy")
            self.assertEqual(inventory["acpIntegration"]["evidencePaths"], ["scripts/acp.py"])
            self.assertIn("do not install a parallel ACP authority", inventory["acpIntegration"]["guidance"])

    def test_existing_mode_preserves_conflicting_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "existing"
            out.mkdir()
            original = "# Existing project authority\n"
            (out / "AGENTS.md").write_text(original, encoding="utf-8")
            cp = subprocess.run(
                [
                    sys.executable, "scripts/init-project.py",
                    "--name", "Existing Fixture",
                    "--id", "existing-fixture",
                    "--mode", "existing",
                    "--output", str(out),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(cp.returncode, 3)
            self.assertEqual((out / "AGENTS.md").read_text(encoding="utf-8"), original)
            self.assertTrue((out / ".formal-bootstrap/candidates/AGENTS.md").exists())
            alignment = (out / "records/alignment.jsonl").read_text(encoding="utf-8")
            self.assertIn("bootstrap_collision", alignment)

    def test_release_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_ok(
                sys.executable,
                "scripts/package-release.py",
                "--output", tmp,
                "--verify-reproducible",
            )
            archive = Path(tmp) / f"formal-project-bootstrap-v{VERSION}.zip"
            checksum = Path(tmp) / f"formal-project-bootstrap-v{VERSION}.sha256"
            self.assertTrue(archive.exists())
            declared = checksum.read_text(encoding="utf-8").split()[0]
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(declared, actual)
            with zipfile.ZipFile(archive) as package:
                local_environment_files = [
                    name for name in package.namelist()
                    if Path(name).name == ".env" or (Path(name).name.startswith(".env.") and Path(name).name != ".env.example")
                ]
                private_thread_metadata = [name for name in package.namelist()
                                           if "/.agents/thread/" in f"/{name}"]
            self.assertEqual(local_environment_files, [])
            self.assertEqual(private_thread_metadata, [])

    def test_acp_binding_is_declared_in_templates(self):
        profile = json.loads((ROOT / "PROJECT_PROFILE_TEMPLATE.json").read_text(encoding="utf-8"))
        acp = profile["authorizationProvider"]
        self.assertEqual(acp["name"], "acp-gateway")
        self.assertTrue(acp["failClosed"])
        self.assertEqual(profile["executionProvider"]["protection"], "acp-gateway")
        for ref in (acp["integrationRef"], acp["decisionSchema"], acp["actionMap"], acp["checkScript"]):
            self.assertTrue((ROOT / ref).exists(), ref)
        bindings = (ROOT / "bindings/PROJECT_BINDINGS_TEMPLATE.yaml").read_text(encoding="utf-8")
        self.assertIn('protection: "acp-gateway"', bindings)
        self.assertIn("acp-gateway:decision", bindings)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## 17. External authorization authority (ACP)", agents)
        self.assertIn("fail closed", agents)
        schema = json.loads((ROOT / "schemas/acp-decision.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(schema["properties"]["decision"]["enum"]),
            {"ALLOW", "DENY", "AUTH_REQUIRED", "REVERIFY_REQUIRED", "QUARANTINE",
             "LOCKED", "RECOVERY_AUTHORIZED", "VERIFY_RECOVERY"},
        )
        self.assertTrue((ROOT / ".agents/skills/authorize-protected-effect/SKILL.md").exists())
        self.assertIn("authorize-protected-effect", (ROOT / "docs/SKILLS_INDEX.md").read_text(encoding="utf-8"))

    def test_initializer_binds_acp_without_writing_the_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bound"
            self.run_ok(
                sys.executable,
                "scripts/init-project.py",
                "--name", "Bound Project",
                "--id", "bound-project",
                "--mode", "new",
                "--acp-endpoint-set", "production",
                "--acp-owner", "example-org",
                "--acp-project", "3",
                "--acp-repository", "example-org/bound-project",
                "--output", str(out),
            )
            profile = json.loads((out / "PROJECT_PROFILE.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["authorizationProvider"]["status"], "bound")
            self.assertEqual(profile["authorizationProvider"]["board"], {"owner": "example-org", "number": 3})
            self.assertEqual(profile["authorizationProvider"]["gatewayEndpointSet"], "production")
            board_env = (out / ".agents/board.env").read_text(encoding="utf-8")
            self.assertIn("ACP_BOARD_NUMBER=3", board_env)
            self.assertIn("ACP_REMOTE_URL=https://github.com/example-org/bound-project.git", board_env)
            self.assertNotIn("ACP_GATEWAY_TOKEN", board_env)
            self.assertNotIn("ACP_GATEWAY_URL", board_env)
            proposal_path = out / ".formal-bootstrap/acp-policy-proposal.json"
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            self.assertEqual(proposal["repository"]["owner"], "example-org")
            self.assertEqual(proposal["repository"]["name"], "bound-project")
            self.assertEqual(proposal["boards"], [{"owner": "example-org", "number": 3}])
            self.assertNotIn("ACP_GATEWAY_TOKEN", proposal_path.read_text(encoding="utf-8"))
            self.assertNotIn(proposal_path.read_text(encoding="utf-8"), (out / ".agents/llms-full.txt").read_text(encoding="utf-8"))
            gitignore = (out / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".env.local", gitignore)
            self.assertIn("!.agents/", gitignore)
            self.assertTrue((out / "docs/ACP_INTEGRATION.md").exists())
            self.assertTrue((out / "scripts/acp-check.py").exists())
            self.assertTrue((out / "contracts/acp-protected-effects.yaml").exists())
            self.assertTrue((out / "schemas/acp-decision.schema.json").exists())
            self.run_ok(sys.executable, "scripts/validate-bootstrap.py", "--check-context", cwd=out)
            # The compiled context must never carry the token even if a local env file exists.
            (out / ".env.local").write_text("ACP_GATEWAY_TOKEN=supersecretvalue\n", encoding="utf-8")
            self.run_ok(sys.executable, "scripts/gen-context.py", cwd=out)
            self.assertNotIn("supersecretvalue", (out / ".agents/llms-full.txt").read_text(encoding="utf-8"))
            # acp-check refuses to run without the token, and never prints one that exists.
            cp = subprocess.run(
                [sys.executable, "scripts/acp-check.py", "--json"],
                cwd=out, text=True, capture_output=True,
                env={k: v for k, v in os.environ.items() if not k.startswith("ACP_")},
            )
            self.assertNotEqual(cp.returncode, 0)
            self.assertNotIn("supersecretvalue", cp.stdout + cp.stderr)

    def test_initializer_generates_boardless_policy_proposal_from_repository_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "partial"
            cp = self.run_ok(
                sys.executable,
                "scripts/init-project.py",
                "--name", "Partial ACP Project",
                "--id", "partial-acp-project",
                "--mode", "new",
                "--acp-repository", "example-org/partial-acp-project",
                "--output", str(out),
            )
            profile = json.loads((out / "PROJECT_PROFILE.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["authorizationProvider"]["status"], "declared")
            self.assertIn("ACP_SETUP_INCOMPLETE", cp.stdout)
            self.assertIn("bind an existing ProjectsV2 board later", cp.stdout)
            proposal = json.loads((out / ".formal-bootstrap/acp-policy-proposal.json").read_text(encoding="utf-8"))
            self.assertEqual(proposal["repository"]["owner"], "example-org")
            self.assertEqual(proposal["repository"]["name"], "partial-acp-project")
            self.assertNotIn("boards", proposal)
            self.assertTrue((out / "records/local-work-items.jsonl").exists())

    def test_local_work_ledger_accepts_only_complete_e0_e1_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "local-ledger"
            self.run_ok(sys.executable, "scripts/init-project.py", "--name", "Local Ledger",
                        "--id", "local-ledger", "--mode", "new", "--output", str(out))
            ledger = out / "records/local-work-items.jsonl"
            item = {
                "id": "issue-16-local-bootstrap",
                "state": "Ready",
                "intentRef": "PROJECT_INTENT.md",
                "objectiveOrHypothesis": "Complete a bounded local bootstrap change.",
                "scope": ["scripts/init-project.py"],
                "exclusions": ["GitHub writes", "protected pushes", "deployments"],
                "dependencies": [],
                "acceptance": ["local validator accepts the item"],
                "evidenceRequirements": ["validator output"],
                "permissions": ["source.inspect", "local.edit", "local.test", "local.commit"],
                "effectClass": "E1",
                "target": {"repositoryOrArtifact": "local-ledger", "authorizedPaths": ["scripts/init-project.py"]},
                "budget": {"retries": 1},
                "stopConditions": ["a requested path is outside scope"],
            }
            ledger.write_text(json.dumps(item) + "\n", encoding="utf-8")
            self.run_ok(sys.executable, "scripts/validate-local-work-items.py", cwd=out)
            item["effectClass"] = "E2"
            ledger.write_text(json.dumps(item) + "\n", encoding="utf-8")
            rejected = subprocess.run([sys.executable, "scripts/validate-local-work-items.py"],
                                      cwd=out, text=True, capture_output=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("completed historical evidence", rejected.stderr)

    def test_initializer_rejects_insecure_acp_gateway_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "insecure"
            cp = subprocess.run(
                [sys.executable, "scripts/init-project.py", "--name", "Insecure", "--id", "insecure",
                 "--mode", "new", "--acp-endpoint-set", "Not_Lowercase", "--output", str(out)],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertEqual(cp.returncode, 2)
            self.assertIn("lowercase name", cp.stderr)
            self.assertFalse(out.exists())

    def test_validator_rejects_token_in_committed_board_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "leaky"
            self.run_ok(
                sys.executable, "scripts/init-project.py",
                "--name", "Leaky", "--id", "leaky", "--mode", "new",
                "--acp-endpoint-set", "production",
                "--acp-owner", "example-org", "--acp-project", "3",
                "--acp-repository", "example-org/leaky",
                "--output", str(out),
            )
            board_env = out / ".agents/board.env"
            board_env.write_text(board_env.read_text(encoding="utf-8") + "ACP_GATEWAY_TOKEN=oops\n", encoding="utf-8")
            cp = subprocess.run([sys.executable, "scripts/validate-bootstrap.py"], cwd=out, text=True, capture_output=True)
            self.assertEqual(cp.returncode, 2)
            self.assertIn("never be written", cp.stderr)

    def test_json_artifacts_parse(self):
        for path in [
            "PROJECT_PROFILE_TEMPLATE.json",
            "schemas/acp-decision.schema.json",
            "schemas/acp-endpoint-registry.schema.json",
            "CONTEXT_SOURCES_TEMPLATE.json",
            "FORMAL_RESOURCE_MANIFEST_TEMPLATE.json",
            "schemas/agent-message.schema.json",
            "schemas/context-lock.schema.json",
            "schemas/context-sources.schema.json",
            "schemas/formal-resource-manifest.schema.json",
            "schemas/work-disposition.schema.json",
        ]:
            json.loads((ROOT / path).read_text(encoding="utf-8"))

    def test_bootstrap_sequence_does_not_require_synthetic_b5_b8(self):
        text = (ROOT / "docs/BOOTSTRAP_SEQUENCE.md").read_text(encoding="utf-8")
        self.assertIn("should manufacture", text)
        self.assertIn("NOT OBSERVED", text)
        self.assertIn("Gate B6 — Candidate / landing / evidence separation", text)
        self.assertIn("Gate B7 — Multi-agent coordination", text)
        self.assertIn("Gate B8 — Recovery", text)


if __name__ == "__main__":
    unittest.main()
