from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


class RepositoryTests(unittest.TestCase):
    def run_ok(self, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True)

    def test_version_is_single_source_for_profile(self):
        profile = json.loads((ROOT / "PROJECT_PROFILE_TEMPLATE.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["profileVersion"], VERSION)
        self.assertIn(f"**Version:** {VERSION}", (ROOT / "README.md").read_text(encoding="utf-8"))

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
            for name in ["evidence.jsonl", "negative-results.jsonl", "deviations.jsonl", "alignment.jsonl"]:
                self.assertTrue((out / "records" / name).exists())
            self.run_ok(sys.executable, "scripts/validate-bootstrap.py", "--check-context", cwd=out)

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
                "--acp-gateway-url", "https://acp.example.invalid/",
                "--acp-owner", "example-org",
                "--acp-project", "3",
                "--output", str(out),
            )
            profile = json.loads((out / "PROJECT_PROFILE.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["authorizationProvider"]["status"], "bound")
            self.assertEqual(profile["authorizationProvider"]["board"], {"owner": "example-org", "number": 3})
            board_env = (out / ".agents/board.env").read_text(encoding="utf-8")
            self.assertIn("ACP_GATEWAY_URL=https://acp.example.invalid\n", board_env)
            self.assertIn("ACP_BOARD_NUMBER=3", board_env)
            self.assertNotIn("ACP_GATEWAY_TOKEN", board_env)
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
            self.assertIn(cp.returncode, (2, 4))
            self.assertNotIn("supersecretvalue", cp.stdout + cp.stderr)

    def test_validator_rejects_token_in_committed_board_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "leaky"
            self.run_ok(
                sys.executable, "scripts/init-project.py",
                "--name", "Leaky", "--id", "leaky", "--mode", "new",
                "--acp-gateway-url", "https://acp.example.invalid",
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
            "CONTEXT_SOURCES_TEMPLATE.json",
            "FORMAL_RESOURCE_MANIFEST_TEMPLATE.json",
            "schemas/agent-message.schema.json",
            "schemas/context-lock.schema.json",
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
