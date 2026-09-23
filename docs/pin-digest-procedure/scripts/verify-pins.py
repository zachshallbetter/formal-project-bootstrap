#!/usr/bin/env python3
"""Verify FORMAL_RESOURCE_MANIFEST.json pins against their canonical sources.

`docs/FORMAL_RESOURCES.md` says to prefer immutable revisions or content
digests, and the manifest schema carries `revisionOrDigest`. Neither says how a
content digest is computed. "Aggregate sha256 of the file sha256s over the
mount" does not determine an answer: it leaves open which files are walked,
which are excluded, in what order they are combined, and with what separator.

A digest whose procedure is unrecorded cannot be reproduced, so it cannot be
refuted. It reads as an integrity control and functions as a decoration. In the
adoption that motivated this script, 48 candidate procedures failed to
reproduce one recorded digest whose source was an immutable released package --
so drift could not explain the mismatch.

This file fixes one procedure and fails when a source drifts.

## Procedure `fpb-aggregate-v1`

  1. Walk the mount. Skip any path with a component in EXCLUDED_DIRS, and any
     file whose name is in EXCLUDED_NAMES.
  2. Take each file's relative POSIX path and the sha256 of its bytes.
  3. Sort by that path (byte order, not locale).
  4. digest = sha256("\n".join(f"{path}:{filehash}")), no trailing newline.

Step 4 is deliberately the aggregate `scripts/gen-context.py` already computes,
so the repository has one digest idea rather than two. Steps 1 and 3 are what
the prose left open, and they are the whole reason unstamped digests cannot be
reproduced. A pin without `digestProcedure` is reported UNREPRODUCIBLE rather
than quietly recomputed into agreement: restamping it silently would erase the
evidence that it never held.

## Where this can run

A pin whose `canonicalSource` is an absolute local path is verifiable only on a
machine that has that mount. A hosted CI runner does not, so such pins cannot be
gated in CI -- a property of the pinning scheme, not of this script. Projects
needing CI-verifiable pins should pin by git revision or published package.

    python3 scripts/verify-pins.py [MANIFEST]              # verify; nonzero on drift
    python3 scripts/verify-pins.py [MANIFEST] --update     # restamp under the procedure
    python3 scripts/verify-pins.py --self-test
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = "FORMAL_RESOURCE_MANIFEST.json"


def manifest_path(argv: list[str]) -> pathlib.Path:
    """First non-flag argument, else the manifest at the project root."""
    for arg in argv[1:]:
        if not arg.startswith("--"):
            return pathlib.Path(arg)
    return ROOT / DEFAULT_MANIFEST
PROCEDURE = "fpb-aggregate-v1"
EXCLUDED_DIRS = {".git", "node_modules"}
EXCLUDED_NAMES = {".DS_Store"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def aggregate(mount: pathlib.Path) -> tuple[str, int]:
    """Procedure fpb-aggregate-v1. Returns (digest, files hashed)."""
    entries = []
    for path in mount.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(mount)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.name in EXCLUDED_NAMES:
            continue
        entries.append((rel.as_posix(), sha(path.read_bytes())))
    entries.sort(key=lambda e: e[0].encode())
    return sha("\n".join(f"{p}:{h}" for p, h in entries).encode()), len(entries)


def is_remote(source: str) -> bool:
    return "://" in source


def check(resource: dict) -> tuple[str, str]:
    """Returns (status, detail). Status is OK, DRIFT, UNREPRODUCIBLE, REMOTE or ABSENT."""
    pin = resource.get("revisionOrDigest", "")
    source = resource.get("canonicalSource", "")

    if is_remote(source):
        return "REMOTE", f"{source} — no local mount; nothing here can verify it"

    mount = pathlib.Path(source)
    if not mount.exists():
        return "ABSENT", f"{source} does not exist"

    # A digest proves the mount did not change; it says nothing about whether the
    # mount still holds what the manifest claims to import. An observed pin ships
    # EMPTY schema and conformance directories while being cited as structural
    # authority, so hollowing is a real failure mode, not a hypothetical one.
    missing = [i for i in resource.get("inventory", []) if not (mount / i).exists()]
    if missing:
        return "DRIFT", f"declared inventory absent from the mount: {', '.join(missing)}"

    if pin.startswith("git:"):
        rev = pin[4:]
        if not (mount / ".git").exists():
            return "DRIFT", f"pinned to revision {rev} but {source} is not a git repository"
        ok = subprocess.run(["git", "-C", str(mount), "cat-file", "-e", f"{rev}^{{commit}}"],
                            capture_output=True).returncode == 0
        if not ok:
            return "DRIFT", f"revision {rev} is not in {source}"
        date = subprocess.run(["git", "-C", str(mount), "log", "-1", "--format=%cs", rev],
                              capture_output=True, text=True).stdout.strip()
        return "OK", f"revision {rev} present ({date})"

    if not pin.startswith("sha256:"):
        return "UNREPRODUCIBLE", f"unrecognised pin form {pin!r}"

    if resource.get("digestProcedure") != PROCEDURE:
        return ("UNREPRODUCIBLE",
                f"no digestProcedure — the recorded digest cannot be reproduced or refuted; "
                f"run --update to restamp under {PROCEDURE}")

    got, count = aggregate(mount)
    want = pin[len("sha256:"):]
    if got != want:
        return "DRIFT", f"expected {want[:16]}… got {got[:16]}… over {count} files"
    return "OK", f"{count} files, digest matches"


def update(path: pathlib.Path) -> int:
    """Restamp digest pins under PROCEDURE, preserving what was there before."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for r in manifest["resources"]:
        pin, source = r.get("revisionOrDigest", ""), r.get("canonicalSource", "")
        if not pin.startswith("sha256:") or is_remote(source):
            continue
        mount = pathlib.Path(source)
        if not mount.exists():
            continue
        digest, count = aggregate(mount)
        if r.get("digestProcedure") == PROCEDURE and pin == f"sha256:{digest}":
            continue
        # Keep the old value. It is the record of what was pinned on 2026-08-28,
        # and discarding it would erase the evidence that it was unreproducible.
        if "priorDigest" not in r:
            r["priorDigest"] = {
                "value": pin,
                "status": "procedure unrecorded; not reproducible when restamped",
            }
        r["revisionOrDigest"] = f"sha256:{digest}"
        r["digestProcedure"] = PROCEDURE
        r["digestFileCount"] = count
        changed += 1
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"restamped {changed} pin(s) under {PROCEDURE}")
    return 0


def self_test() -> int:
    """The gate must be able to fail, or it certifies nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        mount = pathlib.Path(tmp) / "mount"
        (mount / "docs").mkdir(parents=True)
        (mount / "docs" / "SPEC.md").write_text("normative text\n")
        (mount / "VERSION").write_text("0.1.0\n")
        digest, count = aggregate(mount)
        assert count == 2, count

        base = {"id": "t", "kind": "protocol", "required": True, "canonicalSource": str(mount),
                "authorityRole": "test", "digestProcedure": PROCEDURE}

        ok = check({**base, "revisionOrDigest": f"sha256:{digest}"})
        assert ok[0] == "OK", ok

        # Drift: content changes, digest does not.
        (mount / "VERSION").write_text("0.2.0\n")
        drift = check({**base, "revisionOrDigest": f"sha256:{digest}"})
        assert drift[0] == "DRIFT", drift
        (mount / "VERSION").write_text("0.1.0\n")

        # A new file must move the digest — a procedure blind to additions would
        # have let the NaN file (NR-scms-024) through at the protocol layer too.
        (mount / "docs" / "EXTRA.md").write_text("added\n")
        assert check({**base, "revisionOrDigest": f"sha256:{digest}"})[0] == "DRIFT", "addition not caught"
        (mount / "docs" / "EXTRA.md").unlink()

        # Excluded paths must NOT move it, or every checkout would read as drift.
        (mount / ".git").mkdir()
        (mount / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (mount / ".DS_Store").write_bytes(b"\x00junk")
        assert check({**base, "revisionOrDigest": f"sha256:{digest}"})[0] == "OK", "exclusions not honoured"

        # An unstamped digest is unreproducible, never silently OK.
        unstamped = {k: v for k, v in base.items() if k != "digestProcedure"}
        assert check({**unstamped, "revisionOrDigest": f"sha256:{digest}"})[0] == "UNREPRODUCIBLE"

        # Sort order must be path-stable, not filesystem order.
        again, _ = aggregate(mount)
        assert again == aggregate(mount)[0] == digest, "procedure is not deterministic"

        # Inventory: a declared path that is not in the mount is drift, even when
        # the digest itself agrees.
        inv_ok = check({**base, "revisionOrDigest": f"sha256:{digest}", "inventory": ["docs/SPEC.md"]})
        assert inv_ok[0] == "OK", inv_ok
        inv_bad = check({**base, "revisionOrDigest": f"sha256:{digest}", "inventory": ["docs/GONE.md"]})
        assert inv_bad[0] == "DRIFT" and "GONE.md" in inv_bad[1], inv_bad

        assert check({**base, "revisionOrDigest": "sha256:x", "canonicalSource": "https://example/x"})[0] == "REMOTE"
        assert check({**base, "revisionOrDigest": "sha256:x", "canonicalSource": "/nope/nowhere"})[0] == "ABSENT"

    print("self-test ok (match, drift, addition, exclusions, unstamped, determinism, "
          "inventory, remote and absent sources all detected)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    path = manifest_path(sys.argv)
    if "--update" in sys.argv:
        return update(path)

    manifest = json.loads(path.read_text(encoding="utf-8"))
    tally, bad = {}, 0
    for r in manifest["resources"]:
        status, detail = check(r)
        tally[status] = tally.get(status, 0) + 1
        if status in ("DRIFT", "UNREPRODUCIBLE", "ABSENT"):
            bad += 1
        print(f"{status:<15} {r['id']:<12} {detail}")
    print("  " + " · ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    if tally.get("REMOTE"):
        print("  REMOTE pins are unverifiable from any machine; that is the pin's shape, not a pass.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
