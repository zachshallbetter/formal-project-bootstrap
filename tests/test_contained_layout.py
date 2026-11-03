"""The contained layout (0.7): migration, the acp and bootstrap commands, and their edge cases."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / ".agents/bootstrap/scripts/init-project.py"
GIT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgSign=false",
       "-c", "tag.gpgSign=false"]


def run(*argv, cwd=None, check=True, env=None, input=None):
    environment = {k: v for k, v in os.environ.items() if not k.startswith("ACP_")}
    environment.update({"ACP_KEYCHAIN_LOOKUP": "0", "ACP_ENDPOINT_REGISTRY": "/nonexistent/acp-endpoints.json"})
    environment.update(env or {})
    return subprocess.run([str(a) for a in argv], cwd=cwd, text=True, capture_output=True, check=check,
                          env=environment, input=input)


def git(repo: Path, *argv, check=True):
    return run("git", "-C", repo, *GIT, *argv, check=check)


def commit_all(repo: Path, message: str = "x") -> None:
    git(repo, "add", "-f", "-A", ".")
    git(repo, "commit", "-q", "-m", message)


def new_project(tmp: str, name: str = "Fixture", git_init: bool = True) -> Path:
    out = Path(tmp) / name.lower()
    run(sys.executable, INIT, "--name", name, "--id", name.lower(), "--mode", "new", "--output", out, cwd=ROOT)
    if git_init:
        run("git", "init", "-q", "-b", "main", out)
        commit_all(out, "init")
    return out


HAS_LEGACY_TAG = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", "v0.6.3^{commit}"],
                                capture_output=True).returncode == 0


def legacy_release(tmp: str) -> Path:
    """The v0.6.3 release tree: the last legacy layout."""
    release = Path(tmp) / "release-0.6.3"
    release.mkdir()
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "v0.6.3"], capture_output=True,
                             check=True)
    subprocess.run(["tar", "-x", "-C", str(release)], input=archive.stdout, check=True)
    return release


def acp(project: Path, *argv, check=False):
    return run(sys.executable, project / ".agents/acp/acp", "--project-root", project, *argv, cwd=project, check=check)


class LayoutTests(unittest.TestCase):
    def test_project_root_stops_at_the_nearest_project_and_the_folder_above_agents(self):
        spec = importlib.util.spec_from_file_location("layout", ROOT / ".agents/bootstrap/scripts/layout.py")
        layout = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(layout)
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp) / "outer"
            nested = outer / "ui"
            worktree = outer / ".claude/worktrees/feature"
            for project in (outer, nested, worktree):
                (project / ".agents/project").mkdir(parents=True)
                (project / ".agents/project/profile.json").write_text("{}")
            (outer / ".git").mkdir()
            (nested / "src").mkdir()
            self.assertEqual(layout.find_project_root(nested / "src"), nested.resolve())
            self.assertEqual(layout.find_project_root(worktree), worktree.resolve())
            self.assertEqual(layout.find_project_root(outer / "docs"), outer.resolve())
            bare = Path(tmp) / "bare"
            (bare / ".agents/bootstrap/scripts").mkdir(parents=True)
            self.assertEqual(layout.find_project_root(bare / ".agents/bootstrap/scripts"), bare.resolve())

    def test_a_symlinked_agents_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "linked"
            out.mkdir()
            (Path(tmp) / "elsewhere").mkdir()
            (out / ".agents").symlink_to(Path(tmp) / "elsewhere")
            cp = run(sys.executable, INIT, "--name", "L", "--id", "l", "--mode", "existing", "--output", out,
                     cwd=ROOT, check=False)
            self.assertEqual(cp.returncode, 2)
            self.assertIn(".agents is a symbolic link", cp.stderr)


@unittest.skipUnless(HAS_LEGACY_TAG, "needs the v0.6.3 tag (fetch tags: git fetch --tags)")
class MigrationTests(unittest.TestCase):
    def test_a_legacy_project_moves_under_agents_reports_references_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = legacy_release(tmp)
            project = Path(tmp) / "legacy"
            run(sys.executable, release / "scripts/init-project.py", "--name", "Legacy", "--id", "legacy",
                "--mode", "new", "--output", project, cwd=release)
            (project / "records/benchmarks.jsonl").write_text('{"own": true}\n')
            (project / "scripts/check.sh").write_text("python3 scripts/gen-context.py --check\n")
            agents = (project / "AGENTS.md").read_text()
            (project / "AGENTS.md").write_text(agents + "\nSee PROJECT_INTENT.md and records/evidence.jsonl.\n")
            run("git", "init", "-q", "-b", "main", project)
            commit_all(project)
            before = sorted(git(project, "ls-files").stdout.split())

            upgrade = ROOT / ".agents/bootstrap/scripts/upgrade-project.py"
            cp = run(sys.executable, upgrade, "--project", project, "--from", ROOT, "--apply", check=False)
            self.assertEqual(cp.returncode, 0, cp.stdout[-2000:] + cp.stderr[-2000:])
            root = sorted(p.name for p in project.iterdir() if p.name != ".git")
            self.assertEqual(root, [".agents", ".gitignore", "AGENTS.md", "README.md", "records", "scripts"])
            self.assertEqual(sorted(p.name for p in (project / "records").iterdir()), ["benchmarks.jsonl"])
            self.assertEqual(sorted(p.name for p in (project / "scripts").iterdir()), ["check.sh"])
            self.assertTrue((project / ".agents/project/profile.json").is_file())
            self.assertTrue((project / ".agents/acp/lib/acp.py").is_file())
            text = (project / "AGENTS.md").read_text()
            self.assertIn("See .agents/project/intent.md and .agents/records/evidence.jsonl.", text)
            self.assertNotIn("profileVersion", json.loads((project / ".agents/project/profile.json").read_text()))
            self.assertIn("scripts/check.sh", cp.stderr)
            self.assertIn(".agents/bootstrap/scripts/gen-context.py --check", cp.stderr)
            self.assertEqual((project / "scripts/check.sh").read_text(), "python3 scripts/gen-context.py --check\n")
            run(sys.executable, project / ".agents/bootstrap/scripts/validate-bootstrap.py", "--check-context",
                cwd=project)

            run(sys.executable, project / ".agents/bootstrap/scripts/upgrade-project.py", "--project", project,
                "--from", ROOT, "--rollback")
            after = sorted(git(project, "ls-files").stdout.split())
            self.assertEqual(before, after)
            generated = (".agents/context-lock.json", ".agents/llms.txt", ".agents/llms-full.txt")
            dirty = [line for line in git(project, "status", "--porcelain").stdout.splitlines()
                     if not line.endswith(generated)]
            self.assertEqual(dirty, [])
            self.assertFalse((project / ".agents/project").exists())

    def test_bootstrap_upgrade_commit_leaves_unrelated_work_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = legacy_release(tmp)
            project = Path(tmp) / "wip"
            run(sys.executable, release / "scripts/init-project.py", "--name", "Wip", "--id", "wip",
                "--mode", "new", "--output", project, cwd=release)
            (project / "app.py").write_text("print('v1')\n")
            run("git", "init", "-q", "-b", "main", project)
            commit_all(project)
            (project / "app.py").write_text("print('work in progress')\n")
            cp = run(sys.executable, ROOT / ".agents/bootstrap/bootstrap", "--project", project, "upgrade",
                     "--from", ROOT, "--commit", cwd=project, check=False)
            self.assertEqual(cp.returncode, 0, cp.stdout[-1500:] + cp.stderr[-1500:])
            status = git(project, "status", "--porcelain").stdout.splitlines()
            self.assertEqual(status, [" M app.py"])
            committed = git(project, "show", "--name-only", "--no-renames", "--format=", "HEAD").stdout.split()
            self.assertNotIn("app.py", committed)
            self.assertIn(".agents/project/profile.json", committed)
            self.assertIn("PROJECT_PROFILE.json", committed)
            clean = Path(tmp) / "clean"
            git(project, "worktree", "add", "-q", "--detach", clean, "HEAD")
            run(sys.executable, clean / ".agents/bootstrap/scripts/validate-bootstrap.py", "--check-context",
                cwd=clean)


class AcpCommandTests(unittest.TestCase):
    def test_status_names_each_problem_with_its_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project(tmp)
            (project / "vercel.json").write_text("{}")
            cp = acp(project, "status", "--offline", "--json")
            report = json.loads(cp.stdout)
            codes = {item["code"]: item for item in report["checks"]}
            self.assertEqual(codes["S002"]["level"], "OK")
            self.assertEqual(codes["S012"]["level"], "WARN")
            self.assertIn("acp init", codes["S012"]["fix"])
            online = acp(project, "status")
            self.assertEqual(online.returncode, 2)
            self.assertIn("S005", online.stdout)
            self.assertIn("fix:", online.stdout)

    def test_init_is_idempotent_detects_auto_deploy_and_writes_no_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project(tmp)
            git(project, "remote", "add", "origin", "https://github.com/example/fixture.git")
            (project / "netlify.toml").write_text("")
            first = acp(project, "init", "--offline", check=True)
            self.assertIn("auto-deploy", first.stdout)
            profile = json.loads((project / ".agents/project/profile.json").read_text())
            self.assertEqual(profile["authorizationProvider"]["autoDeploy"],
                             [{"ref": "refs/heads/main", "environment": "production"}])
            self.assertIn("ACP_REMOTE_URL=https://github.com/example/fixture.git",
                          (project / ".agents/board.env").read_text())
            snapshot = {p: p.read_bytes() for p in project.rglob("*") if p.is_file() and ".git/" not in str(p)}
            second = acp(project, "init", "--offline", check=True)
            self.assertNotIn("wrote", second.stdout)
            self.assertEqual(snapshot, {p: p.read_bytes() for p in project.rglob("*")
                                        if p.is_file() and ".git/" not in str(p)})
            for path in (project / ".agents/board.env", project / ".agents/project/profile.json"):
                self.assertNotIn("TOKEN=", path.read_text())

    def test_push_dry_run_lists_each_approval_and_refuses_a_non_fast_forward(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = Path(tmp) / "remote.git"
            run("git", "init", "-q", "--bare", remote)
            project = new_project(tmp)
            git(project, "remote", "add", "origin", str(remote))
            git(project, "push", "-q", "origin", "main")
            profile_path = project / ".agents/project/profile.json"
            profile = json.loads(profile_path.read_text())
            profile["authorizationProvider"]["autoDeploy"] = [{"ref": "refs/heads/main", "environment": "production"}]
            profile_path.write_text(json.dumps(profile))
            commit_all(project, "declare auto-deploy")
            plan = acp(project, "push", "--dry-run", check=True)
            self.assertIn("git.remote.update", plan.stdout)
            self.assertIn("git.protected_ref.update", plan.stdout)
            self.assertIn("production.deploy", plan.stdout)
            git(project, "reset", "-q", "--hard", "HEAD~1")
            (project / "other.txt").write_text("diverged\n")
            commit_all(project, "diverge")
            other = Path(tmp) / "other"
            run("git", "clone", "-q", str(remote), other)
            (other / "theirs.txt").write_text("theirs\n")
            commit_all(other, "theirs")
            git(other, "push", "-q", "origin", "main")
            refused = acp(project, "push", "--dry-run")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("only fast-forwards", refused.stderr)

    def test_authorize_decisions_go_to_the_ignored_local_log_and_record_promotes_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project(tmp)
            acp(project, "authorize", "--action", "git.remote.update", "--ref", "refs/heads/x",
                "--old-sha", "0" * 40, "--new-sha", "a" * 40)
            log = project / ".agents/records/local/acp-decisions.jsonl"
            self.assertTrue(log.exists())
            self.assertEqual(git(project, "check-ignore", "-q", log.relative_to(project), check=False).returncode, 0)
            listing = acp(project, "record", check=True)
            self.assertIn("git.remote.update", listing.stdout)
            acp(project, "record", "--all", check=True)
            self.assertIn("git.remote.update", (project / ".agents/records/evidence.jsonl").read_text())

    def test_acp_uninstall_leaves_a_valid_bootstrap_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project(tmp)
            plan = acp(project, "uninstall", check=True)
            self.assertIn("dry run", plan.stdout)
            self.assertTrue((project / ".agents/acp/acp").exists())
            acp(project, "uninstall", "--apply", check=True)
            self.assertFalse((project / ".agents/acp").exists())
            profile = json.loads((project / ".agents/project/profile.json").read_text())
            self.assertEqual(profile["authorizationProvider"]["name"], "none")
            run(sys.executable, project / ".agents/bootstrap/scripts/gen-context.py", cwd=project)
            run(sys.executable, project / ".agents/bootstrap/scripts/validate-bootstrap.py", "--check-context",
                cwd=project)


class BootstrapCommandTests(unittest.TestCase):
    def test_repair_restores_edited_machinery_and_keeps_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project(tmp)
            client = project / ".agents/acp/lib/acp.py"
            original = client.read_bytes()
            client.write_bytes(original + b"# edited\n")
            tool = project / ".agents/bootstrap/bootstrap"
            listing = run(sys.executable, tool, "--project", project, "repair", "--from", ROOT, check=True)
            self.assertIn("edited:  .agents/acp/lib/acp.py", listing.stdout)
            run(sys.executable, tool, "--project", project, "repair", "--from", ROOT, "--apply", check=True)
            self.assertEqual(client.read_bytes(), original)
            copies = list((project / ".agents/.upgrades").glob("repair-*/.agents/acp/lib/acp.py"))
            self.assertEqual(len(copies), 1)

    def test_uninstall_keeps_project_files_and_modified_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project(tmp)
            skill = project / ".agents/skills/verify-outcome/SKILL.md"
            skill.write_text(skill.read_text() + "\nProject note.\n")
            tool = project / ".agents/bootstrap/bootstrap"
            run(sys.executable, tool, "--project", project, "uninstall", "--apply", "--export", Path(tmp) / "export",
                check=True)
            self.assertFalse((project / ".agents/acp").exists())
            self.assertFalse((project / ".agents/bootstrap").exists())
            self.assertTrue(skill.exists())
            self.assertFalse((project / ".agents/skills/compile-context").exists())
            self.assertTrue((project / ".agents/project/profile.json").exists())
            self.assertTrue((project / ".agents/records/evidence.jsonl").exists())
            self.assertTrue((Path(tmp) / "export/.agents/project/intent.md").exists())

    def test_a_fetched_release_with_a_tampered_file_is_refused(self):
        spec = importlib.util.spec_from_file_location(
            "bootstrap_cli", ROOT / ".agents/bootstrap/scripts/bootstrap_cli.py")
        sys.path.insert(0, str(ROOT / ".agents/bootstrap/scripts"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "dist", "build", "__pycache__"))
            target = source / ".agents/acp/lib/acp.py"
            target.write_text(target.read_text() + "# tampered after the manifest\n")
            run("git", "init", "-q", source)
            commit_all(source)
            git(source, "tag", "v9.9.9")
            cli.CACHE = Path(tmp) / "cache"
            with self.assertRaises(SystemExit) as unsigned:
                cli.fetch_release(str(source), "v9.9.9", allow_unverified=False)
            self.assertIn("signature could not be verified", str(unsigned.exception))
            with self.assertRaises(SystemExit) as tampered:
                cli.fetch_release(str(source), "v9.9.9", allow_unverified=True)
            self.assertIn("differ from its RELEASE.json", str(tampered.exception))


if __name__ == "__main__":
    unittest.main()
