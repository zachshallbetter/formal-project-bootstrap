"""scripts/acp.py and scripts/acp-check.py against a stub gateway.

The stub answers with whatever each test scripts, so the fail-closed rules are
tested on the client alone: nothing here needs acp-gateway, GitHub or a network.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "stub-gateway-token-that-must-never-appear"
OWNER, NAME, BOARD = "example-org", "example-repo", 3
MAIN = "refs/heads/main"
OLD, NEW = "a" * 40, "b" * 40


class Stub(BaseHTTPRequestHandler):
    routes: dict = {}
    seen: list = []

    def _answer(self, body=None):
        path = self.path.split("?")[0]
        Stub.seen.append({"method": self.command, "path": path, "body": body,
                          "authorization": self.headers.get("Authorization")})
        status, reply = Stub.routes.get(path, (404, {"error": "NOT_FOUND"}))
        if self.headers.get("Authorization") not in (None, "Bearer " + TOKEN) and path != "/health":
            status, reply = 401, {"error": "UNAUTHORIZED", "detail": "Missing or wrong bearer token."}
        raw = reply.encode() if isinstance(reply, str) else json.dumps(reply).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._answer()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self._answer(json.loads(self.rfile.read(length) or b"null"))

    def log_message(self, *_):
        pass


def decision(name="ALLOW", **extra):
    body = {"decision": name, "code": "A0", "reason": "VERIFIED_AND_PERMITTED",
            "action": "git.protected_ref.update", "request_id": "r1", "evaluated_at": "2026-09-23T00:00:00Z",
            "policy_id": "p", "policy_version": 1, "repository_trust": "VERIFIED",
            "policy_effect": "AUTHORIZED_FOR_THIS_EXACT_ACTION",
            "authorized_action": {"action": "git.protected_ref.update", "ref": MAIN, "old_sha": OLD, "new_sha": NEW},
            "capability": {"scope": "x"}, "capability_token": "cap.token.value"}
    body.update(extra)
    return body


class AcpClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.tmp = tempfile.mkdtemp()
        cls.project = Path(cls.tmp) / "project"
        subprocess.run([sys.executable, "scripts/init-project.py", "--name", "Client", "--id", "client",
                        "--output", str(cls.project), "--acp-gateway-url", cls.url,
                        "--acp-owner", OWNER, "--acp-project", str(BOARD)],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        for args in (["init", "-q", "-b", "main"],
                     ["remote", "add", "origin", f"https://github.com/{OWNER}/{NAME}.git"]):
            subprocess.run(["git", *args], cwd=cls.project, check=True)
        (cls.project / ".env.local").write_text(f"ACP_GATEWAY_TOKEN={TOKEN}\n", encoding="utf-8")
        cls.schema = json.loads((ROOT / "schemas/acp-decision.schema.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        Stub.routes = {"/health": (200, {"status": "ok", "app_configured": True}),
                       "/internal/app-status": (200, {"configured": True}),
                       "/internal/projects": (200, {"projects": [{"number": BOARD, "title": "b", "allowed": True}]}),
                       "/notice": (200, {"governed": True, "policy_id": "p"})}
        Stub.seen = []

    def acp(self, *args, env=None, script="scripts/acp.py"):
        environment = {k: v for k, v in os.environ.items() if not k.startswith("ACP_")}
        environment.update(env or {})
        cp = subprocess.run([sys.executable, script, *args], cwd=self.project, text=True,
                            capture_output=True, env=environment)
        self.assertNotIn(TOKEN, cp.stdout + cp.stderr, "the gateway token is never printed")
        return cp

    def authorize(self, *extra, env=None):
        cp = self.acp("authorize", "--action", "git.protected_ref.update", "--ref", MAIN,
                      "--old-sha", OLD, "--new-sha", NEW, *extra, env=env)
        out = json.loads(cp.stdout)
        jsonschema.validate(out, self.schema)
        return cp.returncode, out

    def test_allow_for_the_exact_action_proceeds_and_is_recorded_without_the_capability(self):
        Stub.routes["/internal/authorize"] = (200, decision())
        rc, out = self.authorize("--record", "--work-item", "7")
        self.assertEqual((rc, out["decision"]), (0, "ALLOW"))
        sent = Stub.seen[-1]["body"]
        self.assertEqual(sent["repository_claim"]["owner"], OWNER)
        self.assertEqual(sent["context"], {"ref": MAIN, "old_sha": OLD, "new_sha": NEW})
        record = json.loads((self.project / "records/evidence.jsonl").read_text().splitlines()[-1])
        self.assertEqual((record["gate"], record["decision"], record["workItem"]), ("acp-decision", "ALLOW", "7"))
        self.assertNotIn("cap.token.value", json.dumps(record))

    def test_not_governed_is_not_an_authorization(self):
        Stub.routes["/internal/authorize"] = (200, decision(reason="OUT_OF_POLICY_SCOPE", policy_effect="NOT_GOVERNED",
                                                            authorized_action=None, capability_token=None))
        rc, out = self.authorize()
        self.assertEqual((rc, out["decision"], out["reason"]), (11, "DENY", "ACP_NOT_GOVERNING"))
        self.assertTrue(out["synthetic"])
        self.assertEqual(out["gateway_decision"]["reason"], "OUT_OF_POLICY_SCOPE")

    def test_not_governed_passes_only_when_the_profile_is_not_fail_closed(self):
        profile_path = self.project / "PROJECT_PROFILE.json"
        original = profile_path.read_text(encoding="utf-8")
        profile = json.loads(original)
        profile["authorizationProvider"]["failClosed"] = False
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        try:
            Stub.routes["/internal/authorize"] = (200, decision(reason="OUT_OF_POLICY_SCOPE",
                                                                policy_effect="NOT_GOVERNED", authorized_action=None))
            rc, out = self.authorize()
            self.assertEqual((rc, out["decision"]), (0, "ALLOW"))
        finally:
            profile_path.write_text(original, encoding="utf-8")

    def test_an_allow_for_something_else_is_refused(self):
        other = {"action": "git.protected_ref.update", "ref": "refs/heads/release", "old_sha": OLD, "new_sha": NEW}
        Stub.routes["/internal/authorize"] = (200, decision(authorized_action=other))
        rc, out = self.authorize()
        self.assertEqual((rc, out["reason"]), (11, "AUTHORIZED_ACTION_MISMATCH"))

    def test_every_failure_to_obtain_a_decision_fails_closed(self):
        cases = {
            "unreachable": ({"ACP_GATEWAY_URL": "http://127.0.0.1:9"}, None),
            "refused": ({"ACP_GATEWAY_TOKEN": "wrong"}, None),
            "server error": ({}, (502, {"error": "UPSTREAM_FAILURE", "detail": "x"})),
            "not json": ({}, (200, "<html>")),
            "missing fields": ({}, (200, {"decision": "ALLOW", "reason": "x"})),
            "unknown decision": ({}, (200, decision(name="MAYBE"))),
        }
        for label, (env, route) in cases.items():
            with self.subTest(label):
                if route:
                    Stub.routes["/internal/authorize"] = route
                else:
                    Stub.routes["/internal/authorize"] = (200, decision())
                cp = self.acp("authorize", "--action", "git.remote.update", env=env)
                out = json.loads(cp.stdout)
                jsonschema.validate(out, self.schema)
                self.assertEqual((cp.returncode, out["decision"], out["reason"]), (11, "DENY", "GATEWAY_UNAVAILABLE"))
                self.assertTrue(out["synthetic"])

    def test_each_decision_has_its_own_exit_code(self):
        for name, code in (("DENY", 11), ("AUTH_REQUIRED", 12), ("REVERIFY_REQUIRED", 13), ("QUARANTINE", 14),
                           ("LOCKED", 15), ("RECOVERY_AUTHORIZED", 16), ("VERIFY_RECOVERY", 17)):
            with self.subTest(name):
                Stub.routes["/internal/authorize"] = (200, decision(name=name, reason="X"))
                rc, out = self.authorize()
                self.assertEqual((rc, out["decision"]), (code, name))

    def test_missing_token_is_a_local_setup_blocker(self):
        env_file = self.project / ".env.local"
        env_file.write_text("", encoding="utf-8")
        try:
            cp = self.acp("authorize", "--action", "git.remote.update")
            self.assertEqual(cp.returncode, 2)
            self.assertEqual(json.loads(cp.stdout)["reason"], "GATEWAY_UNAVAILABLE")
            self.assertFalse(any(s["path"] == "/internal/authorize" for s in Stub.seen), "nothing was sent")
        finally:
            env_file.write_text(f"ACP_GATEWAY_TOKEN={TOKEN}\n", encoding="utf-8")

    def test_reports_use_the_gateways_typed_events(self):
        Stub.routes["/internal/report"] = (200, {"accepted": True, "authorizes": False, "kind": "checkpoint"})
        cp = self.acp("report", "--event", "PROTECTED_EFFECT_PENDING", "--checkpoint", "PRE_PUSH",
                      "--action", "git.protected_ref.update", "--ref", MAIN)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        sent = Stub.seen[-1]["body"]
        self.assertEqual(sent["event_type"], "PROTECTED_EFFECT_PENDING")
        self.assertEqual(sent["evidence"], {"checkpoint": "PRE_PUSH", "action": "git.protected_ref.update"})
        self.assertEqual(sent["resource"]["ref"], MAIN)
        self.assertEqual(sent["principal"]["client_type"], "formal-project-bootstrap")
        contract = yaml.safe_load((ROOT / "contracts/acp-protected-effects.yaml").read_text(encoding="utf-8"))
        named = set()
        for entry in contract["reports"]:
            named.update(entry["event"] if isinstance(entry["event"], list) else [entry["event"]])
        self.assertIn("PROTECTED_EFFECT_PENDING", named)

    def test_snapshot_hashes_the_control_artifacts(self):
        Stub.routes["/internal/integrity/snapshot"] = (200, {"accepted": True})
        cp = self.acp("snapshot", "--checkpoint", "SESSION_START")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        artifacts = {a["path"]: a for a in Stub.seen[-1]["body"]["artifacts"]}
        self.assertEqual(artifacts["AGENTS.md"]["state"], "present")
        self.assertEqual(len(artifacts["AGENTS.md"]["sha256"]), 64)
        self.assertNotIn(".env.local", artifacts)

    def test_policy_candidate_names_the_repository_board_and_control_artifacts(self):
        cp = self.acp("policy")
        policy = json.loads(cp.stdout)
        self.assertEqual(policy["repository"], {"owner": OWNER, "name": NAME,
                                                "canonical_remote": f"https://github.com/{OWNER}/{NAME}.git"})
        self.assertEqual(policy["boards"], [{"owner": OWNER, "number": BOARD}])
        paths = {a["path"] for a in policy["artifact_manifest"]["artifacts"]}
        self.assertTrue({"AGENTS.md", "PROJECT_PROFILE.json", "contracts/acp-protected-effects.yaml"} <= paths)
        self.assertNotIn("signature", policy, "a candidate is never signed by the project")

    def test_an_inline_comment_in_board_env_is_not_part_of_the_value(self):
        board_env = self.project / ".agents/board.env"
        original = board_env.read_text(encoding="utf-8")
        board_env.write_text(original.replace(f"ACP_BOARD_NUMBER={BOARD}",
                                              f"ACP_BOARD_NUMBER={BOARD}        # Example — Board"),
                             encoding="utf-8")
        try:
            cp = self.acp("--json", script="scripts/acp-check.py")
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertEqual(json.loads(cp.stdout)["checks"]["board"], "OK")
        finally:
            board_env.write_text(original, encoding="utf-8")

    def test_notice_says_whether_the_repository_is_governed(self):
        cp = self.acp("notice")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIsNone(Stub.seen[-1]["authorization"], "the notice is unauthenticated")
        Stub.routes["/notice"] = (200, {"governed": False})
        self.assertEqual(self.acp("notice").returncode, 5)
        self.assertEqual(self.acp("notice", "--allow-ungoverned").returncode, 0)
        self.assertEqual(self.acp("notice", env={"ACP_GATEWAY_URL": "http://127.0.0.1:9"}).returncode, 4)

    def test_report_can_name_a_file_and_its_digest(self):
        Stub.routes["/internal/report"] = (200, {"accepted": True})
        cp = self.acp("report", "--event", "LOCAL_POLICY_MODIFIED", "--path", "AGENTS.md")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        evidence = Stub.seen[-1]["body"]["evidence"]
        self.assertEqual(evidence["path"], "AGENTS.md")
        self.assertEqual(len(evidence["current_sha256"]), 64)

    def test_policy_manifest_covers_the_client_and_the_skill_tree(self):
        manifest = json.loads(self.acp("policy").stdout)["artifact_manifest"]
        artifacts = {a["path"]: a for a in manifest["artifacts"]}
        self.assertIn("scripts/acp.py", artifacts)
        self.assertIn("PROJECT_INTENT.md", artifacts)
        self.assertEqual({a["change_policy"] for a in artifacts.values()}, {"authorize_and_report"})
        self.assertFalse(artifacts["NEW_AGENT_PROMPT.md"]["required"])
        patterns = {p["pattern"]: p["change_policy"] for p in manifest["patterns"]}
        self.assertEqual(patterns, {".agents/skills/**": "authorize_and_report",
                                    "records/deviations.jsonl": "report_only"})
        strict = json.loads(self.acp("policy", "--strict").stdout)["artifact_manifest"]["artifacts"]
        self.assertEqual({a["change_policy"] for a in strict}, {"admin_exact_transition"})

    def test_acp_check_requires_a_governing_policy(self):
        cp = self.acp(script="scripts/acp-check.py")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        notice = next(s for s in Stub.seen if s["path"] == "/notice")
        self.assertIsNone(notice["authorization"], "the notice is read unauthenticated")
        Stub.routes["/notice"] = (200, {"governed": False})
        cp = self.acp(script="scripts/acp-check.py")
        self.assertEqual(cp.returncode, 5, "not governed has its own exit code")
        self.assertIn("no ACP policy governs example-org/example-repo", cp.stderr)
        cp = self.acp("--allow-ungoverned", script="scripts/acp-check.py")
        self.assertEqual(cp.returncode, 0)
        self.assertIn("WARNING", cp.stderr)


if __name__ == "__main__":
    unittest.main()
