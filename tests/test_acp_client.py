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
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "stub-gateway-token-that-must-never-appear"
FALLBACK_TOKEN = "stub-fallback-token-that-must-never-appear"
ADMIN_TOKEN = "stub-admin-token-that-must-never-appear"
OWNER, NAME, BOARD = "example-org", "example-repo", 3
MAIN = "refs/heads/main"
OLD, NEW = "a" * 40, "b" * 40


class Stub(BaseHTTPRequestHandler):
    routes: dict = {}
    routes_by_port: dict = {}
    seen: list = []
    drop_post_ports: set[int] = set()
    delays: dict = {}

    def _answer(self, body=None):
        path = self.path.split("?")[0]
        port = self.server.server_address[1]
        time.sleep(Stub.delays.get(path, 0))
        Stub.seen.append({"method": self.command, "path": path, "url": self.path, "body": body,
                          "port": port,
                          "authorization": self.headers.get("Authorization"),
                          "admin_authorization": self.headers.get("X-ACP-Admin-Authorization"),
                          "idempotency_key": self.headers.get("Idempotency-Key")})
        status, reply = Stub.routes_by_port.get(port, {}).get(
            path, Stub.routes.get(path, (404, {"error": "NOT_FOUND"})))
        if self.headers.get("Authorization") not in (None, "Bearer " + TOKEN,
                                                       "Bearer " + FALLBACK_TOKEN) and path != "/health":
            status, reply = 401, {"error": "UNAUTHORIZED", "detail": "Missing or wrong bearer token."}
        raw = reply.encode() if isinstance(reply, str) else json.dumps(reply).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        if 300 <= status < 400 and isinstance(reply, dict) and reply.get("location"):
            self.send_header("Location", reply["location"])
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._answer()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"null")
        if self.server.server_address[1] in Stub.drop_post_ports:
            Stub.seen.append({"method": self.command, "path": self.path.split("?")[0],
                              "body": body, "port": self.server.server_address[1],
                              "authorization": self.headers.get("Authorization"),
                              "admin_authorization": self.headers.get("X-ACP-Admin-Authorization"),
                              "idempotency_key": self.headers.get("Idempotency-Key")})
            self.close_connection = True
            return
        self._answer(body)

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
                        "--output", str(cls.project), "--acp-endpoint-set", "production",
                        "--acp-owner", OWNER, "--acp-project", str(BOARD),
                        "--acp-repository", f"{OWNER}/{NAME}"],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        for args in (["init", "-q", "-b", "main"],
                     ["remote", "add", "origin", f"https://github.com/{OWNER}/{NAME}.git"]):
            subprocess.run(["git", *args], cwd=cls.project, check=True)
        (cls.project / ".env.local").write_text(f"ACP_GATEWAY_TOKEN={TOKEN}\n", encoding="utf-8")
        cls.registry = Path(cls.tmp) / "acp-endpoints.json"
        cls.profile_bytes = (cls.project / "PROJECT_PROFILE.json").read_bytes()
        cls.schema = json.loads((ROOT / "schemas/acp-decision.schema.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        (self.project / "PROJECT_PROFILE.json").write_bytes(self.profile_bytes)
        self.write_endpoint_sets({"production": [
            {"name": "vercel", "url": self.url, "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
        ]})
        Stub.routes = {"/health": (200, {"status": "ok", "app_configured": True}),
                       "/ready": (200, {"status": "ready", "storage": "postgres",
                                        "state_authority_id": "test-shared",
                                        "idempotency": {"version": 1, "state_authority_id": "test-shared", "routes": [
                                            "/internal/authorize", "/internal/report",
                                            "/internal/integrity/snapshot", "/internal/recovery/complete",
                                            "/internal/recover", "/internal/overrides",
                                            "/internal/overrides/revoke"]}}),
                       "/internal/app-status": (200, {"configured": True}),
                       "/internal/projects": (200, {"projects": [{"number": BOARD, "title": "b", "allowed": True}]}),
                       "/internal/installations": (200, {"installations": [{"login": OWNER}]}),
                       "/internal/project-context": (200, {"snapshot": {"number": BOARD}, "allowed": True}),
                       "/notice": (200, {"governed": True, "policy_id": "p"})}
        Stub.routes_by_port = {}
        Stub.seen = []
        Stub.drop_post_ports = set()
        Stub.delays = {}

    def write_endpoint_sets(self, endpoint_sets):
        self.registry.write_text(json.dumps({"formatVersion": 1, "endpointSets": endpoint_sets}, indent=2) + "\n",
                                 encoding="utf-8")
        self.registry.chmod(0o600)

    def configure_endpoint_set(self, set_name, endpoints, *, select=True):
        if len(endpoints) > 1:
            for endpoint in endpoints:
                endpoint.setdefault("stateAuthorityId", "test-shared")
        registry = json.loads(self.registry.read_text(encoding="utf-8"))
        registry["endpointSets"][set_name] = endpoints
        self.write_endpoint_sets(registry["endpointSets"])
        if select:
            path = self.project / "PROJECT_PROFILE.json"
            profile = json.loads(path.read_text(encoding="utf-8"))
            profile["authorizationProvider"]["gatewayEndpointSet"] = set_name
            path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    def configure_loopback_fallback(self, *, primary_url="http://127.0.0.1:9", fallback_url=None,
                                    select=True):
        self.configure_endpoint_set("test-failover", [
            {"name": "vercel", "url": primary_url, "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
            {"name": "titan", "url": fallback_url or self.url,
             "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
        ], select=select)

    def acp(self, *args, env=None, script="scripts/acp.py", cwd=None):
        environment = {k: v for k, v in os.environ.items() if not k.startswith("ACP_")}
        environment["ACP_KEYCHAIN_LOOKUP"] = "0"
        environment["ACP_ENDPOINT_REGISTRY"] = str(self.registry)
        environment.update(env or {})
        cp = subprocess.run([sys.executable, script, *args], cwd=cwd or self.project, text=True,
                            capture_output=True, env=environment)
        self.assertNotIn(TOKEN, cp.stdout + cp.stderr, "the gateway token is never printed")
        self.assertNotIn(FALLBACK_TOKEN, cp.stdout + cp.stderr, "the fallback token is never printed")
        self.assertNotIn(ADMIN_TOKEN, cp.stdout + cp.stderr, "the admin token is never printed")
        return cp

    def authorize(self, *extra, env=None):
        cp = self.acp("authorize", "--action", "git.protected_ref.update", "--ref", MAIN,
                      "--old-sha", OLD, "--new-sha", NEW, *extra, env=env)
        out = json.loads(cp.stdout)
        jsonschema.validate(out, self.schema)
        return cp.returncode, out

    def test_database_migration_sends_and_checks_the_exact_six_field_scope(self):
        context = {"source_database": "source-project/source-db",
                   "target_database": "target-project/target-db", "work_item": "7",
                   "environment": "production", "ref": MAIN, "new_sha": NEW}
        Stub.routes["/internal/authorize"] = (200, decision(
            action="database.migrate", authorized_action={"action": "database.migrate", **context}))
        cp = self.acp("authorize", "--action", "database.migrate", "--environment", "production",
                      "--context-json", json.dumps({key: context[key] for key in
                                                    ("source_database", "target_database")}),
                      "--work-item", context["work_item"], "--ref", MAIN, "--new-sha", NEW)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(Stub.seen[-1]["body"]["context"], context)

        mismatched = {**context, "target_database": "other-project/other-db"}
        Stub.routes["/internal/authorize"] = (200, decision(
            action="database.migrate", authorized_action={"action": "database.migrate", **mismatched}))
        cp = self.acp("authorize", "--action", "database.migrate", "--environment", "production",
                      "--context-json", json.dumps({key: context[key] for key in
                                                    ("source_database", "target_database")}),
                      "--work-item", context["work_item"], "--ref", MAIN, "--new-sha", NEW)
        self.assertEqual(cp.returncode, 11, cp.stdout)
        self.assertEqual(json.loads(cp.stdout)["reason"], "AUTHORIZED_ACTION_MISMATCH")

    def test_database_migration_rejects_incomplete_or_secret_scope_before_network(self):
        invalid = (
            {"source_database": "same", "target_database": "same"},
            {"source_database": "postgresql://user:secret@host/db", "target_database": "target"},
            {"source_database": "source", "target_database": "target?token=secret"},
        )
        for context in invalid:
            with self.subTest(context=context):
                cp = self.acp("authorize", "--action", "database.migrate", "--environment", "production",
                              "--context-json", json.dumps(context), "--work-item", "7",
                              "--ref", MAIN, "--new-sha", NEW)
                self.assertEqual(cp.returncode, 2)
                self.assertEqual(Stub.seen, [])

    def test_board_read_uses_requested_board_through_shared_client(self):
        cp = self.acp("board", "--owner", OWNER, "--project", str(BOARD))
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(json.loads(cp.stdout), {"snapshot": {"number": BOARD}, "allowed": True})
        self.assertEqual(Stub.seen[-1]["path"], "/internal/project-context")
        self.assertIn(f"owner={OWNER}", Stub.seen[-1]["url"])
        self.assertIn(f"project={BOARD}", Stub.seen[-1]["url"])

    def test_legacy_gate_mode_is_not_reported_as_an_active_lock_after_successful_read(self):
        Stub.routes["/internal/project-context"] = (200, {
            "snapshot": {"number": BOARD}, "allowed": True,
            "acp": {"gate": "locked", "authorization_state": "NORMAL", "integrity": "MATCH"},
        })
        cp = self.acp("board", "--owner", OWNER, "--project", str(BOARD))
        self.assertEqual(cp.returncode, 0, cp.stderr)
        advisory = json.loads(cp.stdout)["acp"]
        self.assertEqual(advisory["gate_mode"], "locked")
        self.assertEqual(advisory["gate_status"], "BOARD_READ_ALLOWED")
        self.assertFalse(advisory["gate_blocked"])
        self.assertIsNone(advisory["active_block"])
        self.assertIn("does not authorize protected actions", advisory["gate_note"])

    def test_explicit_active_gate_contract_is_preserved(self):
        Stub.routes["/internal/project-context"] = (200, {
            "snapshot": {"number": BOARD}, "allowed": True,
            "acp": {"gate": "locked", "gate_mode": "locked", "gate_status": "CLEAR",
                    "gate_blocked": False, "active_block": None},
        })
        cp = self.acp("board", "--owner", OWNER, "--project", str(BOARD))
        self.assertEqual(cp.returncode, 0, cp.stderr)
        advisory = json.loads(cp.stdout)["acp"]
        self.assertEqual(advisory["gate_status"], "CLEAR")
        self.assertFalse(advisory["gate_blocked"])
        self.assertNotIn("gate_note", advisory)

    def test_project_discovery_uses_shared_client(self):
        cp = self.acp("projects", "--owner", OWNER)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(json.loads(cp.stdout)["projects"][0]["number"], BOARD)
        self.assertEqual(Stub.seen[-1]["path"], "/internal/projects")
        self.assertIn(f"owner={OWNER}", Stub.seen[-1]["url"])

    def test_installation_discovery_uses_shared_client(self):
        cp = self.acp("installations")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(json.loads(cp.stdout)["installations"][0]["login"], OWNER)
        self.assertEqual(Stub.seen[-1]["path"], "/internal/installations")

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

    def test_administrative_authorization_uses_admin_header_and_exact_action(self):
        for action in ("policy.modify", "credential.modify"):
            with self.subTest(action=action):
                Stub.routes["/internal/authorize"] = (200, decision(
                    reason="ADMINISTRATIVELY_AUTHORIZED", action=action,
                    action_class="administrative", policy_effect="AUTHORIZED_FOR_THIS_EXACT_ACTION",
                    authorized_action={"action": action}, capability=None, capability_token=None))
                cp = self.acp("authorize", "--action", action, "--summary", "approved admin change",
                              env={"ACP_POLICY_ADMIN_TOKEN": "stub-admin-secret"})
                self.assertEqual(cp.returncode, 0, cp.stderr)
                self.assertEqual(json.loads(cp.stdout)["authorized_action"], {"action": action})
                sent = Stub.seen[-1]
                self.assertEqual(sent["path"], "/internal/authorize")
                self.assertEqual(sent["admin_authorization"], "Bearer stub-admin-secret")
                self.assertEqual(sent["body"]["action"], action)
                self.assertNotIn("stub-admin-secret", cp.stdout + cp.stderr)

    def test_administrative_authorization_without_admin_token_fails_before_request(self):
        cp = self.acp("authorize", "--action", "policy.modify")
        self.assertEqual(cp.returncode, 2)
        self.assertEqual(Stub.seen, [])
        self.assertNotIn("stub-admin-secret", cp.stdout + cp.stderr)

    def test_shared_bootstrap_runner_uses_the_selected_worktree_identity(self):
        subprocess.run(["git", "-C", str(self.project), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.project), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.project), "commit", "--allow-empty", "-m", "target"],
                       check=True, capture_output=True)
        target_sha = subprocess.check_output(["git", "-C", str(self.project), "rev-parse", "HEAD"],
                                             text=True).strip()
        Stub.routes["/internal/authorize"] = (200, decision())
        cp = self.acp("--project-root", str(self.project), "authorize", "--action",
                      "git.protected_ref.update", "--ref", MAIN, "--old-sha", OLD, "--new-sha", NEW,
                      cwd=ROOT)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        sent = Stub.seen[-1]["body"]
        self.assertEqual((sent["repository_claim"]["owner"], sent["repository_claim"]["name"],
                          sent["repository_claim"]["head_sha"]), (OWNER, NAME, target_sha))

    def test_project_root_must_be_a_git_worktree_root(self):
        cp = self.acp("--project-root", str(self.project / ".agents"), "authorize",
                      "--action", "git.remote.update", cwd=ROOT)
        self.assertEqual(cp.returncode, 2)
        self.assertIn("Git worktree root", cp.stderr)
        self.assertEqual(Stub.seen, [])

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
            "unreachable": ({}, None),
            "refused": ({"ACP_GATEWAY_TOKEN": "wrong"}, None),
            "server error": ({}, (502, {"error": "UPSTREAM_FAILURE", "detail": "x"})),
            "not json": ({}, (200, "<html>")),
            "missing fields": ({}, (200, {"decision": "ALLOW", "reason": "x"})),
            "unknown decision": ({}, (200, decision(name="MAYBE"))),
        }
        for label, (env, route) in cases.items():
            with self.subTest(label):
                if label == "unreachable":
                    self.configure_endpoint_set("test-unreachable", [
                        {"name": "vercel", "url": "http://127.0.0.1:9",
                         "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                    ])
                else:
                    self.configure_endpoint_set("production", [
                        {"name": "vercel", "url": self.url,
                         "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                    ])
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

    @unittest.skipUnless(sys.platform == "darwin", "macOS Keychain lookup is Darwin-only")
    def test_gateway_bearer_uses_the_named_macos_keychain_item_without_writing_it(self):
        env_file = self.project / ".env.local"
        original = env_file.read_text(encoding="utf-8")
        helper = Path(self.tmp) / "keychain-bin"
        helper.mkdir(exist_ok=True)
        security = helper / "security"
        security.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "expected = ['find-generic-password', '-s', 'ACP Gateway Production', '-a', 'ACP_GATEWAY_TOKEN', '-w']\n"
            "if sys.argv[1:] != expected:\n"
            "    raise SystemExit(1)\n"
            "sys.stdout.write(os.environ['TEST_KEYCHAIN_TOKEN'])\n",
            encoding="utf-8")
        security.chmod(0o700)
        env_file.write_text("", encoding="utf-8")
        try:
            Stub.routes["/internal/authorize"] = (200, decision())
            rc, out = self.authorize(env={"ACP_KEYCHAIN_LOOKUP": "1", "PATH": f"{helper}:{os.environ['PATH']}",
                                          "TEST_KEYCHAIN_TOKEN": TOKEN})
            self.assertEqual((rc, out["decision"]), (0, "ALLOW"))
            self.assertEqual(Stub.seen[-1]["authorization"], "Bearer " + TOKEN)
            self.assertNotIn(TOKEN, json.dumps(out))
            self.assertEqual(env_file.read_text(encoding="utf-8"), "")
        finally:
            env_file.write_text(original, encoding="utf-8")

    def test_fallback_bearer_uses_its_own_keychain_account(self):
        self.configure_loopback_fallback()
        env_file = self.project / ".env.local"
        original = env_file.read_text(encoding="utf-8")
        helper = Path(self.tmp) / "fallback-keychain-bin"
        helper.mkdir(exist_ok=True)
        security = helper / "security"
        security.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "expected = ['find-generic-password', '-s', 'ACP Gateway Production', '-a', 'ACP_GATEWAY_TOKEN_FALLBACK', '-w']\n"
            "if sys.argv[1:] != expected:\n"
            "    raise SystemExit(1)\n"
            "sys.stdout.write(os.environ['TEST_KEYCHAIN_TOKEN'])\n",
            encoding="utf-8")
        security.chmod(0o700)
        env_file.write_text("", encoding="utf-8")
        try:
            Stub.routes["/internal/authorize"] = (200, decision())
            rc, out = self.authorize(env={
                "ACP_KEYCHAIN_LOOKUP": "1",
                "PATH": f"{helper}:{os.environ['PATH']}",
                "TEST_KEYCHAIN_TOKEN": FALLBACK_TOKEN,
            })
            self.assertEqual((rc, out["decision"]), (0, "ALLOW"))
            self.assertEqual(Stub.seen[-1]["authorization"], "Bearer " + FALLBACK_TOKEN)
            self.assertNotIn(FALLBACK_TOKEN, json.dumps(out))
            self.assertEqual(env_file.read_text(encoding="utf-8"), "")
        finally:
            env_file.write_text(original, encoding="utf-8")

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

    def test_acp_check_uses_configured_canonical_remote_without_git_origin(self):
        subprocess.run(["git", "remote", "remove", "origin"], cwd=self.project, check=True)
        try:
            cp = self.acp("--json", script="scripts/acp-check.py")
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertTrue(json.loads(cp.stdout)["checks"]["notice"] == "OK")
            notice = next(s for s in Stub.seen if s["path"] == "/notice")
            self.assertIn(f"owner={OWNER}", notice["url"])
            self.assertIn(f"name={NAME}", notice["url"])
        finally:
            subprocess.run(["git", "remote", "add", "origin", f"https://github.com/{OWNER}/{NAME}.git"],
                           cwd=self.project, check=True)

    def test_repository_identity_override_conflicting_with_remote_fails_closed(self):
        cp = self.acp("policy", env={"ACP_REPOSITORY_NAME": "other-repository"})
        self.assertEqual(cp.returncode, 2)
        self.assertIn("conflicts with ACP_REMOTE_URL or origin", cp.stderr)
        cp = self.acp("--json", script="scripts/acp-check.py",
                      env={"ACP_REPOSITORY_NAME": "other-repository"})
        self.assertEqual(cp.returncode, 2)
        self.assertIn("conflicts with ACP_REMOTE_URL or origin", cp.stderr)
        self.assertEqual(Stub.seen, [], "a conflicting repository identity must be rejected before network calls")

    def test_notice_says_whether_the_repository_is_governed(self):
        cp = self.acp("notice")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIsNone(Stub.seen[-1]["authorization"], "the notice is unauthenticated")
        Stub.routes["/notice"] = (200, {"governed": False})
        self.assertEqual(self.acp("notice").returncode, 5)
        self.assertEqual(self.acp("notice", "--allow-ungoverned").returncode, 0)
        self.configure_endpoint_set("test-down", [
            {"name": "vercel", "url": "http://127.0.0.1:9",
             "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
        ])
        self.assertEqual(self.acp("notice").returncode, 4)

    def test_endpoint_registry_cli_writes_private_ordered_machine_config_without_tokens(self):
        cp = self.acp("endpoints", "configure", "--set-name", "local-test", "--local-only",
                      "--endpoint", "loopback", self.url, "ACP_GATEWAY_TOKEN_LOCAL")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertNotIn(TOKEN, cp.stdout + cp.stderr)
        self.assertEqual(self.registry.stat().st_mode & 0o777, 0o600)
        output = json.loads(cp.stdout)
        self.assertEqual(output["endpointSets"]["local-test"], [{
            "name": "loopback", "url": self.url, "keychainAccount": "ACP_GATEWAY_TOKEN_LOCAL",
            "localOnly": True,
        }])
        duplicate = self.acp("endpoints", "configure", "--set-name", "local-test", "--local-only",
                             "--endpoint", "loopback", self.url, "ACP_GATEWAY_TOKEN_LOCAL")
        self.assertEqual(duplicate.returncode, 2)
        listed = self.acp("endpoints", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn('"local-test"', listed.stdout)
        production = self.acp("endpoints", "configure", "--set-name", "production-two",
                              "--shared-state-id", "acp-production-neon-01",
                              "--endpoint", "vercel", "https://vercel.example.invalid", "ACP_GATEWAY_TOKEN",
                              "--endpoint", "titan", "https://titan.example.invalid", "ACP_GATEWAY_TOKEN_TITAN")
        self.assertEqual(production.returncode, 0, production.stderr)
        configured = json.loads(production.stdout)["endpointSets"]["production-two"]
        self.assertEqual([item["stateAuthorityId"] for item in configured],
                         ["acp-production-neon-01"] * 2)

    def test_machine_registry_rejects_public_permissions_and_mixed_local_cloud_sets(self):
        self.registry.chmod(0o644)
        try:
            cp = self.acp("notice")
            self.assertEqual(cp.returncode, 2)
            self.assertIn("must be private", cp.stderr)
        finally:
            self.registry.chmod(0o600)
        self.configure_endpoint_set("mixed", [
            {"name": "loopback", "url": self.url,
             "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
            {"name": "cloud", "url": "https://acp.example.invalid",
             "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": False},
        ])
        cp = self.acp("notice")
        self.assertEqual(cp.returncode, 2)
        self.assertIn("cannot mix loopback and remote", cp.stderr)
        self.write_endpoint_sets({"production": [
            {"name": "vercel", "url": "https://vercel.example.invalid",
             "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": False},
            {"name": "titan", "url": "https://titan.example.invalid",
             "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": False},
        ]})
        cp = self.acp("notice")
        self.assertEqual(cp.returncode, 2)
        self.assertIn("same explicit stateAuthorityId", cp.stderr)
        self.registry.write_text('{"formatVersion":1,"formatVersion":1,"endpointSets":{}}\n',
                                 encoding="utf-8")
        self.registry.chmod(0o600)
        cp = self.acp("notice")
        self.assertEqual(cp.returncode, 2)
        self.assertIn("duplicate JSON key", cp.stderr)

    def test_unready_primary_selects_fallback_with_its_own_token(self):
        self.configure_loopback_fallback()
        Stub.routes["/internal/authorize"] = (200, decision())
        rc, out = self.authorize(env={
            "ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN,
        })
        self.assertEqual(rc, 0, out)
        auth = next(item for item in Stub.seen if item["path"] == "/internal/authorize")
        self.assertEqual(auth["authorization"], "Bearer " + FALLBACK_TOKEN)
        self.assertEqual(sum(item["path"] == "/internal/authorize" for item in Stub.seen), 1)

    def test_valid_primary_denial_is_not_routed_to_fallback(self):
        self.configure_endpoint_set("test-denial", [
            {"name": "vercel", "url": self.url, "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
            {"name": "titan", "url": "http://127.0.0.1:9",
             "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
        ])
        Stub.routes["/internal/authorize"] = (200, decision("DENY", reason="POLICY_REFUSAL",
            authorized_action=None, capability=None, capability_token=None))
        rc, out = self.authorize(env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
        self.assertEqual((rc, out["decision"]), (11, "DENY"))
        authorization_calls = [item for item in Stub.seen if item["path"] == "/internal/authorize"]
        self.assertEqual(len(authorization_calls), 1)
        self.assertEqual(authorization_calls[0]["authorization"], "Bearer " + TOKEN)

    def test_post_retries_only_with_shared_idempotency_and_reuses_the_same_key(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_port = fallback.server_address[1]
            fallback_url = f"http://127.0.0.1:{fallback_port}"
            capability = {"version": 1, "state_authority_id": "test-shared",
                          "routes": ["/internal/authorize"]}
            Stub.routes_by_port[primary_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared", "idempotency": capability}),
                "/internal/authorize": (503, {"error": "TEMPORARY"}),
            }
            Stub.routes_by_port[fallback_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared", "idempotency": capability}),
                "/internal/authorize": (200, decision()),
            }
            self.configure_endpoint_set("test-idempotent-post", [
                {"name": "vercel", "url": self.url, "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": fallback_url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            rc, out = self.authorize(env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual((rc, out["decision"]), (0, "ALLOW"))
            calls = [item for item in Stub.seen if item["path"] == "/internal/authorize"]
            self.assertEqual([item["port"] for item in calls], [primary_port, fallback_port])
            self.assertTrue(calls[0]["idempotency_key"])
            self.assertEqual(calls[0]["idempotency_key"], calls[1]["idempotency_key"])
            self.assertEqual(calls[0]["body"], calls[1]["body"])
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_post_does_not_retry_without_shared_idempotency_capability(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_port = fallback.server_address[1]
            fallback_url = f"http://127.0.0.1:{fallback_port}"
            for port in (primary_port, fallback_port):
                Stub.routes_by_port[port] = {
                    "/ready": (200, {"status": "ready", "storage": "postgres",
                                     "state_authority_id": "test-shared"}),
                    "/internal/authorize": (503, {"error": "TEMPORARY"}),
                }
            self.configure_endpoint_set("test-no-idempotency", [
                {"name": "vercel", "url": self.url, "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": fallback_url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            rc, out = self.authorize(env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual((rc, out["reason"]), (11, "GATEWAY_UNAVAILABLE"))
            calls = [item for item in Stub.seen if item["path"] == "/internal/authorize"]
            self.assertEqual([item["port"] for item in calls], [primary_port])
            self.assertIsNone(calls[0]["idempotency_key"])
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_post_transport_failure_retries_with_the_same_shared_idempotency_key(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_port = fallback.server_address[1]
            capability = {"version": 1, "state_authority_id": "test-shared",
                          "routes": ["/internal/authorize"]}
            Stub.routes_by_port[primary_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared", "idempotency": capability})}
            Stub.routes_by_port[fallback_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared", "idempotency": capability}),
                "/internal/authorize": (200, decision()),
            }
            Stub.drop_post_ports.add(primary_port)
            self.configure_endpoint_set("test-ambiguous-post", [
                {"name": "vercel", "url": self.url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": f"http://127.0.0.1:{fallback_port}",
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            rc, out = self.authorize(env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual((rc, out["decision"]), (0, "ALLOW"), out)
            calls = [item for item in Stub.seen if item["path"] == "/internal/authorize"]
            self.assertEqual([item["port"] for item in calls], [primary_port, fallback_port])
            self.assertEqual(calls[0]["idempotency_key"], calls[1]["idempotency_key"])
            self.assertEqual(calls[0]["body"], calls[1]["body"])
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_redirect_cannot_forward_gateway_or_admin_credentials(self):
        attacker = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=attacker.serve_forever, daemon=True).start()
        try:
            attacker_url = f"http://127.0.0.1:{attacker.server_address[1]}"
            Stub.routes["/internal/authorize"] = (302, {"location": attacker_url + "/steal"})
            cp = self.acp("authorize", "--action", "policy.modify", "--summary", "approved test",
                          env={"ACP_POLICY_ADMIN_TOKEN": ADMIN_TOKEN})
            self.assertEqual(cp.returncode, 11)
            self.assertFalse(any(item["port"] == attacker.server_address[1] for item in Stub.seen))
        finally:
            attacker.shutdown()
            attacker.server_close()

    def test_oversized_gateway_response_fails_closed(self):
        Stub.routes["/internal/authorize"] = (200, "x" * (8 * 1024 * 1024 + 1))
        rc, out = self.authorize()
        self.assertEqual(rc, 11)
        self.assertEqual(out["decision"], "DENY")
        self.assertEqual(out["reason"], "GATEWAY_UNAVAILABLE")
        self.assertIn("8 MiB", out["detail"])

    def test_transient_read_failure_uses_the_next_ready_endpoint(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_url = f"http://127.0.0.1:{fallback.server_address[1]}"
            Stub.routes_by_port[primary_port] = {"/notice": (503, {"error": "TEMPORARY"})}
            Stub.routes_by_port[fallback.server_address[1]] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared"}),
                "/notice": (200, {"governed": True, "policy_id": "p"}),
            }
            self.configure_endpoint_set("test-transient", [
                {"name": "vercel", "url": self.url, "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": fallback_url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            cp = self.acp("notice", env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual(cp.returncode, 0, cp.stderr)
            calls = [item for item in Stub.seen if item["path"] == "/notice"]
            self.assertEqual([item["port"] for item in calls], [primary_port, fallback.server_address[1]])
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_integrity_failure_on_read_is_not_routed_to_fallback(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_port = fallback.server_address[1]
            Stub.routes_by_port[primary_port] = {"/notice": (503, {"error": "INTEGRITY_MISMATCH"})}
            Stub.routes_by_port[fallback_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared"}),
                "/notice": (200, {"governed": True, "policy_id": "p"}),
            }
            self.configure_endpoint_set("test-integrity", [
                {"name": "vercel", "url": self.url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": f"http://127.0.0.1:{fallback_port}",
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            cp = self.acp("notice", env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual(cp.returncode, 3)
            reads = [item for item in Stub.seen if item["path"] == "/notice"]
            self.assertEqual([item["port"] for item in reads], [primary_port])
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_readiness_401_stops_before_selecting_fallback(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_port = fallback.server_address[1]
            Stub.routes_by_port[primary_port] = {"/ready": (401, {"error": "UNAUTHORIZED"})}
            Stub.routes_by_port[fallback_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared"}),
                "/notice": (200, {"governed": True, "policy_id": "p"}),
            }
            self.configure_endpoint_set("test-unauthorized", [
                {"name": "vercel", "url": self.url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": f"http://127.0.0.1:{fallback_port}",
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            cp = self.acp("notice", env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual(cp.returncode, 4)
            self.assertIn("vercel /ready HTTP 401", cp.stderr)
            self.assertIn("failover stopped", cp.stderr)
            self.assertEqual([item["port"] for item in Stub.seen if item["path"] == "/ready"], [primary_port])
            self.assertFalse(any(item["path"] == "/notice" for item in Stub.seen))
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_structured_readiness_error_stops_before_selecting_fallback(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_port = fallback.server_address[1]
            Stub.routes_by_port[primary_port] = {
                "/ready": (503, {"error": {"code": "POLICY_INVALID", "detail": "Policy signature is invalid."}})}
            Stub.routes_by_port[fallback_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared"}),
                "/notice": (200, {"governed": True, "policy_id": "p"}),
            }
            self.configure_endpoint_set("test-structured-error", [
                {"name": "vercel", "url": self.url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": f"http://127.0.0.1:{fallback_port}",
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            cp = self.acp("notice", env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual(cp.returncode, 4)
            self.assertIn("control failure", cp.stderr)
            self.assertEqual([item["port"] for item in Stub.seen if item["path"] == "/ready"],
                             [primary_port])
            self.assertFalse(any(item["path"] == "/notice" for item in Stub.seen))
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_readiness_failure_identifies_probe_status_and_owner_without_response_contents(self):
        Stub.routes["/ready"] = (200, "private-upstream-body-that-must-not-be-logged")
        cp = self.acp("notice")
        self.assertEqual(cp.returncode, 4)
        self.assertIn("vercel /ready: HTTP 200", cp.stderr)
        self.assertIn("non-object or non-JSON response", cp.stderr)
        self.assertIn("ACP operator", cp.stderr)
        self.assertIn("local E0/E1 work may continue", cp.stderr)
        self.assertNotIn("private-upstream-body", cp.stdout + cp.stderr)
        self.assertFalse(any(item["path"] == "/notice" for item in Stub.seen))

    def test_slow_but_ready_endpoint_is_selected(self):
        Stub.delays["/ready"] = 2.5
        cp = self.acp("notice")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue(any(item["path"] == "/notice" for item in Stub.seen))

    def test_readiness_timeout_names_the_limit_and_the_remedy(self):
        Stub.delays["/ready"] = 2.5
        cp = self.acp("--timeout", "1", "notice")
        self.assertEqual(cp.returncode, 4)
        self.assertIn("vercel /ready: transport unavailable", cp.stderr)
        self.assertIn("probe limit 1000ms", cp.stderr)
        self.assertIn("retry or raise --timeout", cp.stderr)
        self.assertFalse(any(item["path"] == "/notice" for item in Stub.seen))

    def test_shared_state_identity_mismatch_stops_failover_before_request(self):
        fallback = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=fallback.serve_forever, daemon=True).start()
        try:
            primary_port = self.server.server_address[1]
            fallback_port = fallback.server_address[1]
            Stub.routes_by_port[primary_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "different-database"})}
            Stub.routes_by_port[fallback_port] = {
                "/ready": (200, {"status": "ready", "storage": "postgres",
                                 "state_authority_id": "test-shared"}),
                "/notice": (200, {"governed": True, "policy_id": "p"}),
            }
            self.configure_endpoint_set("test-mismatched-state", [
                {"name": "vercel", "url": self.url,
                 "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
                {"name": "titan", "url": f"http://127.0.0.1:{fallback_port}",
                 "keychainAccount": "ACP_GATEWAY_TOKEN_FALLBACK", "localOnly": True},
            ])
            cp = self.acp("notice", env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
            self.assertEqual(cp.returncode, 4)
            self.assertFalse(any(item["path"] == "/notice" for item in Stub.seen))
            self.assertEqual([item["port"] for item in Stub.seen if item["path"] == "/ready"],
                             [primary_port])
        finally:
            fallback.shutdown()
            fallback.server_close()

    def test_local_endpoint_is_never_an_implicit_production_fallback(self):
        self.write_endpoint_sets({
            "production": [{"name": "vercel", "url": "http://127.0.0.1:9",
                            "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True}],
            "local": [{"name": "loopback", "url": self.url,
                       "keychainAccount": "ACP_GATEWAY_TOKEN_LOCAL", "localOnly": True}],
        })
        cp = self.acp("notice", env={"ACP_GATEWAY_TOKEN_LOCAL": FALLBACK_TOKEN})
        self.assertEqual(cp.returncode, 4)
        self.assertEqual(Stub.seen, [])

    def test_local_endpoint_requires_named_set_selection(self):
        Stub.routes["/internal/authorize"] = (200, decision())
        self.write_endpoint_sets({
            "production": [{"name": "vercel", "url": "http://127.0.0.1:9",
                            "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True}],
            "local": [{"name": "loopback", "url": self.url,
                       "keychainAccount": "ACP_GATEWAY_TOKEN_LOCAL", "localOnly": True}],
        })
        profile_path = self.project / "PROJECT_PROFILE.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["authorizationProvider"]["gatewayEndpointSet"] = "local"
        profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        rc, out = self.authorize(env={"ACP_GATEWAY_TOKEN_LOCAL": FALLBACK_TOKEN})
        self.assertEqual(rc, 0, out)
        auth = next(item for item in Stub.seen if item["path"] == "/internal/authorize")
        self.assertEqual(auth["authorization"], "Bearer " + FALLBACK_TOKEN)

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
        self.assertIn("scripts/acp_endpoint_registry.py", artifacts)
        self.assertIn("schemas/acp-endpoint-registry.schema.json", artifacts)
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

    def test_acp_check_reports_policy_and_board_setup_when_gateway_rejects_token(self):
        Stub.routes["/internal/app-status"] = (401, {"error": "UNAUTHORIZED", "detail": "bad token"})
        Stub.routes["/notice"] = (200, {"governed": True, "authorization_state": "NORMAL", "policy_id": "p"})
        cp = self.acp("--json", script="scripts/acp-check.py")
        self.assertEqual(cp.returncode, 3)
        summary = json.loads(cp.stderr)
        notice = next(item for item in Stub.seen if item["path"] == "/notice")
        self.assertIsNone(notice["authorization"])
        self.assertEqual(summary["notice"]["governed"], True)
        states = summary["onboarding"]["states"]
        self.assertEqual(states["policy_registration"], "REGISTERED")
        self.assertEqual(states["resource_authorization"], "NOT_CHECKED")
        self.assertEqual(states["credential"], "REJECTED")
        self.assertEqual(states["board_binding"], "CONFIGURED")
        self.assertEqual(states["failover_configuration"], "MISSING")
        self.assertEqual([(item["condition"], item["owner_role"])
                          for item in summary["onboarding"]["unmet_conditions"]],
                         [("failover_configuration", "gateway_operator"),
                          ("credential", "project_operator"),
                          ("policy_authorization", "project_owner")])

    def test_acp_check_reports_policy_credential_and_board_blockers_together(self):
        Stub.routes["/internal/app-status"] = (401, {"error": "UNAUTHORIZED", "detail": "bad token"})
        Stub.routes["/notice"] = (200, {"governed": False})
        cp = self.acp("--json", script="scripts/acp-check.py")
        self.assertEqual(cp.returncode, 3)
        summary = json.loads(cp.stderr)
        states = summary["onboarding"]["states"]
        self.assertEqual(states["policy_registration"], "NOT_REGISTERED")
        self.assertEqual(states["credential"], "REJECTED")
        self.assertEqual(states["board_binding"], "CONFIGURED")
        self.assertEqual(summary["checks"]["notice"], "FAILED (not governed)")

    def test_acp_check_preserves_recovery_states_and_routes_each_to_the_security_owner(self):
        cases = (
            ("QUARANTINED", "QUARANTINED", "security_administrator"),
            ("LOCKED", "LOCKED", "security_administrator"),
            ("RECOVERY_AUTHORIZED", "RECOVERY_AUTHORIZED", "security_administrator"),
            ("VERIFY_RECOVERY", "VERIFY_RECOVERY", "security_administrator"),
            ("NORMAL", "DISABLED", "policy_maintainer"),
            ("FUTURE_STATE", "UNKNOWN", "gateway_operator"),
        )
        for authorization_state, expected_state, expected_owner in cases:
            with self.subTest(authorization_state=authorization_state):
                Stub.routes["/notice"] = (200, {
                    "governed": True,
                    "authorization_state": authorization_state,
                    "controlled_operations": "DISABLED",
                    "incident_id": "incident-test" if authorization_state in ("QUARANTINED", "LOCKED") else None,
                })
                cp = self.acp("--json", script="scripts/acp-check.py")
                self.assertEqual(cp.returncode, 0, cp.stderr)
                summary = json.loads(cp.stdout)
                self.assertEqual(summary["onboarding"]["states"]["resource_authorization"], expected_state)
                condition = next(item for item in summary["onboarding"]["unmet_conditions"]
                                 if item["condition"] == "policy_authorization")
                self.assertEqual(condition["owner_role"], expected_owner)
                self.assertTrue(condition["next_step"])

    def test_acp_check_names_the_owner_step_for_an_unbound_board(self):
        board_file = self.project / ".agents/board.env"
        original_board_env = board_file.read_text(encoding="utf-8")
        board_file.write_text("", encoding="utf-8")
        profile_path = self.project / "PROJECT_PROFILE.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["authorizationProvider"]["board"] = {}
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        try:
            cp = self.acp("--json", script="scripts/acp-check.py")
            self.assertEqual(cp.returncode, 0, cp.stderr)
            summary = json.loads(cp.stdout)
            self.assertEqual(summary["onboarding"]["states"]["board_binding"], "MISSING")
            self.assertIn({"condition": "board_binding", "owner_role": "project_owner",
                           "next_step": "Bind the intended GitHub Project owner and number in the repository board configuration."},
                          summary["onboarding"]["unmet_conditions"])
        finally:
            board_file.write_text(original_board_env, encoding="utf-8")

    def test_acp_check_uses_fallback_endpoint_and_credential(self):
        self.configure_loopback_fallback()
        cp = self.acp("--json", script="scripts/acp-check.py",
                      env={"ACP_GATEWAY_TOKEN_FALLBACK": FALLBACK_TOKEN})
        self.assertEqual(cp.returncode, 0, cp.stderr)
        summary = json.loads(cp.stdout)
        self.assertEqual(summary["selected_endpoint"], "titan")
        auth = next(item for item in Stub.seen if item["path"] == "/internal/app-status")
        self.assertEqual(auth["authorization"], "Bearer " + FALLBACK_TOKEN)

    def test_local_owner_override_is_branch_scoped_audited_and_does_not_cover_remote_actions(self):
        grant = self.acp("override", "grant", "--scope", "branch", "--environment", "local",
                         "--expires-in", "3600", "--reason", "local experiment", "--authorized-by", OWNER)
        self.assertEqual(grant.returncode, 0, grant.stderr)
        override = json.loads(grant.stdout)
        self.assertEqual((override["branch"], override["environment"], override["actions"]),
                         ("main", "local", ["*"]))

        Stub.seen.clear()
        cp = self.acp("--json", script="scripts/acp-check.py")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(json.loads(cp.stdout)["checks"]["owner_override"], "ACTIVE")
        self.assertEqual(Stub.seen, [], "the local override must work without a gateway call")

        local = self.acp("authorize", "--action", "local.test", "--record")
        self.assertEqual(local.returncode, 0, local.stderr)
        decision_value = json.loads(local.stdout)
        jsonschema.validate(decision_value, self.schema)
        self.assertEqual(decision_value["reason"], "OWNER_LOCAL_OVERRIDE")
        self.assertIsNone(decision_value["capability_token"])
        self.assertEqual(Stub.seen, [])

        Stub.routes["/internal/authorize"] = (200, decision())
        remote = self.acp("authorize", "--action", "git.protected_ref.update", "--ref", MAIN,
                          "--old-sha", OLD, "--new-sha", NEW)
        self.assertEqual(remote.returncode, 0, remote.stderr)
        self.assertEqual(Stub.seen[-1]["path"], "/internal/authorize",
                         "an offline local override must not authorize a remote effect")

        revoked = self.acp("override", "revoke", override["override_id"], "--authorized-by", OWNER)
        self.assertEqual(revoked.returncode, 0, revoked.stderr)
        self.configure_endpoint_set("test-down", [
            {"name": "vercel", "url": "http://127.0.0.1:9",
             "keychainAccount": "ACP_GATEWAY_TOKEN", "localOnly": True},
        ])
        inactive = self.acp("--json", script="scripts/acp-check.py")
        self.assertNotEqual(inactive.returncode, 0)

    def test_shared_owner_override_uses_admin_credential_and_exact_context(self):
        identifier = "owner_override_example"
        Stub.routes["/internal/overrides"] = (201, {
            "authorization_id": identifier, "resource": {"owner": OWNER, "name": NAME,
                                                            "canonical_remote": f"https://github.com/{OWNER}/{NAME}.git"},
            "ref": MAIN, "environment": "preview", "actions": ["git.protected_ref.update"],
            "max_uses": 2, "uses": 0, "authorized_by": OWNER, "reason": "test", "expires_at": "2099-01-01T00:00:00Z",
            "created_at": "2098-01-01T00:00:00Z", "grant_signature": "a" * 64})
        cp = self.acp("override", "shared-grant", "--scope", "branch", "--environment", "preview",
                      "--action", "git.protected_ref.update", "--reason", "test",
                      "--authorized-by", OWNER, env={"ACP_POLICY_ADMIN_TOKEN": "stub-admin-secret"})
        self.assertEqual(cp.returncode, 0, cp.stderr)
        sent = Stub.seen[-1]
        self.assertEqual(sent["path"], "/internal/overrides")
        self.assertEqual(sent["authorization"], "Bearer " + TOKEN)
        self.assertEqual(sent["admin_authorization"], "Bearer stub-admin-secret")
        self.assertEqual(sent["body"]["resource"], {"owner": OWNER, "name": NAME,
                                                     "canonical_remote": f"https://github.com/{OWNER}/{NAME}.git"})

        Stub.routes["/internal/authorize"] = (200, decision())
        authorized = self.acp("authorize", "--action", "git.protected_ref.update", "--environment", "preview",
                              "--ref", MAIN, "--old-sha", OLD, "--new-sha", NEW,
                              "--owner-override-id", identifier)
        self.assertEqual(authorized.returncode, 0, authorized.stderr)
        context = Stub.seen[-1]["body"]["context"]
        self.assertEqual(context, {"ref": MAIN, "old_sha": OLD, "new_sha": NEW,
                                   "environment": "preview", "owner_override_id": identifier})

        Stub.routes["/internal/overrides/revoke"] = (200, {"authorization_id": identifier, "revoked": True,
                                                            "revoked_at": "2098-01-01T00:00:00Z",
                                                            "authorized_by": OWNER, "reason": "test"})
        revoked = self.acp("override", "shared-revoke", identifier, "--reason", "test",
                           "--authorized-by", OWNER,
                           env={"ACP_POLICY_ADMIN_TOKEN": "stub-admin-secret"})
        self.assertEqual(revoked.returncode, 0, revoked.stderr)
        self.assertEqual(Stub.seen[-1]["path"], "/internal/overrides/revoke")
        self.assertNotIn("stub-admin-secret", cp.stdout + cp.stderr + authorized.stdout + authorized.stderr + revoked.stdout + revoked.stderr)


if __name__ == "__main__":
    unittest.main()
