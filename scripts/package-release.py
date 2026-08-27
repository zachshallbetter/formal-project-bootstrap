#!/usr/bin/env python3
"""Build a deterministic release ZIP plus manifest/checksum."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
EXCLUDE_DIRS = {".git", "dist", "build", "__pycache__", ".pytest_cache", ".venv", "venv"}
EXCLUDE_FILES = {"PACKAGE_MANIFEST.json"}
FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_files() -> list[tuple[str, bytes]]:
    items = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        parts = rel.split("/")
        if any(part in EXCLUDE_DIRS for part in parts[:-1]):
            continue
        if rel in EXCLUDE_FILES:
            continue
        items.append((rel, path.read_bytes()))
    return sorted(items, key=lambda item: item[0])


def build_zip(target: Path) -> tuple[dict, str]:
    files = release_files()
    manifest = {
        "format": "1",
        "package": "formal-project-bootstrap",
        "version": VERSION,
        "files": [
            {"path": rel, "bytes": len(data), "sha256": sha(data)} for rel, data in files
        ],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    prefix = f"formal-project-bootstrap-v{VERSION}/"

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, data in files + [("PACKAGE_MANIFEST.json", manifest_bytes)]:
            info = zipfile.ZipInfo(prefix + rel, FIXED_DATE)
            info.create_system = 3
            mode = 0o755 if rel.startswith("scripts/") and rel.endswith(".py") else 0o644
            info.external_attr = mode << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    digest = sha(target.read_bytes())
    return manifest, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist")
    parser.add_argument("--verify-reproducible", action="store_true")
    args = parser.parse_args()

    out = Path(args.output)
    if not out.is_absolute():
        out = ROOT / out
    zip_path = out / f"formal-project-bootstrap-v{VERSION}.zip"
    manifest, digest = build_zip(zip_path)
    (out / f"formal-project-bootstrap-v{VERSION}.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / f"formal-project-bootstrap-v{VERSION}.sha256").write_text(
        f"{digest}  {zip_path.name}\n", encoding="utf-8"
    )

    if args.verify_reproducible:
        with tempfile.TemporaryDirectory() as tmp:
            second = Path(tmp) / zip_path.name
            _, digest2 = build_zip(second)
            if digest2 != digest:
                raise SystemExit("NONDETERMINISTIC: release hashes differ")

    print(f"{zip_path} {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
