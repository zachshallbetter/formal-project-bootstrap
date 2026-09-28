from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProtocolAdapterTests(unittest.TestCase):
    def test_all_bundled_adapters_validate(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validate-protocol-adapters.py"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("5", result.stdout)

    def test_iepe_profile_is_explicitly_bound_on_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "scripts/init-project.py", "--name", "IEPE Fixture", "--id", "iepe-fixture", "--profile", "iepe", "--iepe-source", "https://github.com/zachshallbetter/IEPE", "--iepe-revision", "0970d358f4156bfc44b326295a45844e717734c1", "--output", directory],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            profile = json.loads((Path(directory) / "PROJECT_PROFILE.json").read_text())
            self.assertEqual(profile["protocolAdapters"], ["iepe"])
            self.assertTrue((Path(directory) / "profiles/iepe/adapter.json").exists())
            reference = json.loads((Path(directory) / ".iepe/protocol-reference.json").read_text())
            self.assertEqual(reference["protocolId"], "IEPE-001")
            self.assertEqual(reference["revision"], "0970d358f4156bfc44b326295a45844e717734c1")

    def test_qualification_fails_closed_when_evidence_is_not_consumed(self) -> None:
        record = {
            "format": "1", "qualificationId": "q-1", "candidate": "c-1", "claim": "claim",
            "context": "test", "profile": "default", "obligations": ["o-1"],
            "evidence": [{"id": "e-1", "status": "out-of-scope", "reason": "wrong context"}],
            "evaluator": "evaluator", "authority": "authority", "disposition": "QUALIFIED",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qualification.json"
            path.write_text(json.dumps(record))
            result = subprocess.run([sys.executable, "scripts/validate-qualification.py", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_qualification_preserves_supersession_without_promoting(self) -> None:
        record = {
            "format": "1", "qualificationId": "q-old", "candidate": "c-1", "claim": "claim",
            "context": "old context", "profile": "default", "obligations": ["o-1"],
            "evidence": [{"id": "e-old", "status": "superseded", "reason": "newer context"}],
            "evaluator": "evaluator", "authority": "authority", "disposition": "SUPERSEDED",
            "supersedes": "q-new", "scope": "old", "freshness": "expired",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qualification.json"
            path.write_text(json.dumps(record))
            result = subprocess.run([sys.executable, "scripts/validate-qualification.py", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_protected_interaction_requires_acp_and_receipt(self) -> None:
        contract = {
            "format":"1", "contractId":"ic-1", "intent":"deploy", "participants":["agent"], "boundary":"service",
            "state":"observed", "actions":{"available":[],"authorized":[],"enabled":[],"exposed":[]}, "checks":[],
            "transition":"deploy", "effect":{"class":"production-deploy","target":"service"}, "invariants":[],
            "authorization":{"decision":"ALLOW","decisionId":"d-1","idempotencyKey":"k-1"},
            "recovery":{"plan":"rollback","reversibleBeforeCommit":True}, "receipt":None, "closure":{"status":"open"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(contract))
            result = subprocess.run([sys.executable, "scripts/validate-interaction-contract.py", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_semantic_surface_requires_provenance_and_neutrality(self) -> None:
        surface = {
            "format": "1", "resolutionId": "surface-1", "sourceState": "publication-1",
            "purpose": "reading", "context": "member", "access": "available", "members": [],
            "explanation": "selected by declared purpose", "dependencies": ["publication-1", "resolver-1"],
            "rendererNeutral": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.json"
            path.write_text(json.dumps(surface))
            result = subprocess.run([sys.executable, "scripts/validate-semantic-surface.py", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_semantic_surface_rejects_renderer_leakage(self) -> None:
        surface = {
            "format": "1", "resolutionId": "surface-2", "sourceState": "publication-1",
            "purpose": "reading", "context": "member", "access": "withheld", "members": [],
            "explanation": "protected", "dependencies": ["publication-1"], "css": ".secret {}",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.json"
            path.write_text(json.dumps(surface))
            result = subprocess.run([sys.executable, "scripts/validate-semantic-surface.py", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_recipient_status_is_derived_from_explicit_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipient.json"
            path.write_text(json.dumps({"recipient": None}))
            result = subprocess.run([sys.executable, "scripts/recipient-status.py", str(path), "--as-of", "2026-09-28"], cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertIn('"status": "primitive"', result.stdout)

    def test_esp_profile_initializes_unbound_instance_and_empty_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "scripts/init-project.py", "--name", "ESP Fixture", "--id", "esp-fixture", "--profile", "esp-rcp", "--output", directory],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            instance = json.loads((Path(directory) / "records/external-state.json").read_text())
            self.assertEqual(instance["lifecycle"], "bootstrap")
            self.assertEqual(instance["state"], "unbound")
            self.assertIsNone(instance["owner"])
            self.assertEqual((Path(directory) / "records/recipient.json").read_text().strip(), '{\n  "recipient": null\n}')
            self.assertEqual((Path(directory) / "records/commitments.jsonl").read_text(), "")

    def test_esp_lifecycle_requires_binding_and_records_idempotent_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            init = subprocess.run([sys.executable, "scripts/init-project.py", "--name", "ESP Lifecycle", "--id", "esp-life", "--profile", "esp-rcp", "--output", directory], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            command = [sys.executable, "scripts/esp-instance.py", "--project", directory, "bind-owner", "--owner", "owner-1", "--actor", "owner-1", "--at", "2026-09-28T12:00:00+00:00", "--event-id", "event-1", "--reason", "explicit owner binding"]
            self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            advance = [sys.executable, "scripts/esp-instance.py", "--project", directory, "advance", "--to", "discover", "--actor", "owner-1", "--at", "2026-09-28T12:01:00+00:00", "--event-id", "event-2", "--reason", "begin discovery"]
            self.assertEqual(subprocess.run(advance, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            duplicate = [sys.executable, "scripts/esp-instance.py", "--project", directory, "advance", "--to", "define", "--actor", "owner-1", "--at", "2026-09-28T12:02:00+00:00", "--event-id", "event-2", "--reason", "duplicate id"]
            self.assertNotEqual(subprocess.run(duplicate, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            events = (Path(directory) / "records/external-state-events.jsonl").read_text().splitlines()
            self.assertEqual(len(events), 2)

    def test_reconciliation_detects_existing_iepe_pin_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".iepe").mkdir()
            reference = {"protocol": {"id": "IEPE-001", "version": "0.2.0", "revision": "rev-1", "source": "local-iepe"}}
            (project / ".iepe/protocol-reference.json").write_text(json.dumps(reference, indent=2))
            before = (project / ".iepe/protocol-reference.json").read_bytes()
            result = subprocess.run([sys.executable, "scripts/reconcile-project.py", "--project", directory], cwd=ROOT, capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report["bootstrap"]["detectedProtocols"][0]["id"], "IEPE-001")
            self.assertEqual(report["bootstrap"]["detectedProtocols"][0]["revisionOrDigest"], "rev-1")
            self.assertEqual((project / ".iepe/protocol-reference.json").read_bytes(), before)

    def test_reconciliation_reports_stale_generated_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            init = subprocess.run([sys.executable, "scripts/init-project.py", "--name", "Stale Context", "--id", "stale-context", "--output", str(project)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            (project / "PROJECT_INTENT.md").write_text((project / "PROJECT_INTENT.md").read_text() + "\nchanged\n")
            result = subprocess.run([sys.executable, "scripts/reconcile-project.py", "--project", str(project)], cwd=ROOT, capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report["bootstrap"]["contextFreshness"], "stale-or-invalid")

    def test_iepe_adoption_report_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".iepe").mkdir()
            (project / ".iepe/protocol-reference.json").write_text(json.dumps({"protocolId":"IEPE-001","protocolVersion":"0.2.0","source":"local","revision":"revision-1","relationship":"reference","conformanceCommand":"python3 tools/validate.py"}))
            before = sorted(str(path.relative_to(project)) for path in project.rglob("*"))
            result = subprocess.run([sys.executable, "scripts/iepe-adopt.py", "--project", directory], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(report["readOnly"])
            self.assertEqual(report["iepeReference"]["revision"], "revision-1")
            after = sorted(str(path.relative_to(project)) for path in project.rglob("*"))
            self.assertEqual(before, after)

    def test_esp_records_are_typed_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            init = subprocess.run([sys.executable, "scripts/init-project.py", "--name", "ESP Records", "--id", "esp-records", "--profile", "esp-rcp", "--output", directory], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            commitment = json.dumps({"commitmentId":"commit-1","counterparty":"person-1","obligation":"deliverable-1","status":"open"})
            command = [sys.executable, "scripts/esp-record.py", "--project", directory, "commitment", "--record", commitment]
            self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            conflicting = json.dumps({"commitmentId":"commit-1","counterparty":"person-2","obligation":"deliverable-1","status":"open"})
            conflict_command = [sys.executable, "scripts/esp-record.py", "--project", directory, "commitment", "--record", conflicting]
            self.assertNotEqual(subprocess.run(conflict_command, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            self.assertEqual(len((Path(directory) / "records/commitments.jsonl").read_text().splitlines()), 1)

    def test_esp_recovery_is_explicit_and_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            init = subprocess.run([sys.executable, "scripts/init-project.py", "--name", "ESP Recovery", "--id", "esp-recovery", "--profile", "esp-rcp", "--output", directory], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            common = ["--project", directory]
            bind = [sys.executable, "scripts/esp-instance.py", *common, "bind-owner", "--owner", "owner-1", "--actor", "owner-1", "--at", "2026-09-28T12:00:00+00:00", "--event-id", "bind-1", "--reason", "bind"]
            self.assertEqual(subprocess.run(bind, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            recover = [sys.executable, "scripts/esp-instance.py", *common, "recover", "--actor", "owner-1", "--at", "2026-09-28T12:01:00+00:00", "--event-id", "recover-1", "--reason", "pause for external correction"]
            self.assertEqual(subprocess.run(recover, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            instance = json.loads((Path(directory) / "records/external-state.json").read_text())
            self.assertEqual(instance["state"], "paused")
            resume = [sys.executable, "scripts/esp-instance.py", *common, "resume", "--actor", "owner-1", "--at", "2026-09-28T12:02:00+00:00", "--event-id", "resume-1", "--reason", "correction verified"]
            self.assertEqual(subprocess.run(resume, cwd=ROOT, capture_output=True, text=True).returncode, 0)
            instance = json.loads((Path(directory) / "records/external-state.json").read_text())
            self.assertEqual(instance["state"], "active")

    def test_esp_promotion_requires_qualified_evidence_and_commitment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            init = subprocess.run([sys.executable, "scripts/init-project.py", "--name", "ESP Promotion", "--id", "esp-promotion", "--profile", "esp-rcp", "--output", directory], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            def run_instance(command: str, target: str, number: int) -> subprocess.CompletedProcess[str]:
                return subprocess.run([sys.executable, "scripts/esp-instance.py", "--project", directory, command, "--to", target, "--actor", "owner-1", "--at", f"2026-09-28T12:{number:02d}:00+00:00", "--event-id", f"event-{number}", "--reason", target], cwd=ROOT, capture_output=True, text=True)
            bind = subprocess.run([sys.executable, "scripts/esp-instance.py", "--project", directory, "bind-owner", "--owner", "owner-1", "--actor", "owner-1", "--at", "2026-09-28T12:00:00+00:00", "--event-id", "bind", "--reason", "bind"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(bind.returncode, 0)
            for number, target in enumerate(["discover", "define", "contract", "baseline", "map", "prepare", "execute", "observe"], 1):
                self.assertEqual(run_instance("advance", target, number).returncode, 0)
            self.assertNotEqual(run_instance("advance", "qualify", 9).returncode, 0)
            evidence = json.dumps({"evidenceId":"e-1","claim":"claim-1","source":"receipt-1","status":"consumed"})
            self.assertEqual(subprocess.run([sys.executable, "scripts/esp-record.py", "--project", directory, "evidence", "--record", evidence], cwd=ROOT, capture_output=True, text=True).returncode, 0)
            self.assertEqual(run_instance("advance", "qualify", 10).returncode, 0)
            self.assertNotEqual(run_instance("advance", "decide", 11).returncode, 0)
            qualification = json.dumps({"format":"1","qualificationId":"q-1","candidate":"c-1","claim":"claim-1","context":"ctx","profile":"default","obligations":["o-1"],"evidence":[{"id":"e-1","status":"consumed"}],"evaluator":"eval-1","authority":"auth-1","disposition":"QUALIFIED"})
            self.assertEqual(subprocess.run([sys.executable, "scripts/esp-record.py", "--project", directory, "qualification", "--record", qualification], cwd=ROOT, capture_output=True, text=True).returncode, 0)
            self.assertEqual(run_instance("advance", "decide", 12).returncode, 0)
            self.assertEqual(run_instance("advance", "commit", 13).returncode, 0)
            self.assertNotEqual(run_instance("advance", "promote", 14).returncode, 0)
            commitment = json.dumps({"commitmentId":"commit-1","counterparty":"person-1","obligation":"deliverable-1","status":"open"})
            self.assertEqual(subprocess.run([sys.executable, "scripts/esp-record.py", "--project", directory, "commitment", "--record", commitment], cwd=ROOT, capture_output=True, text=True).returncode, 0)
            self.assertEqual(run_instance("advance", "promote", 15).returncode, 0)


if __name__ == "__main__":
    unittest.main()
