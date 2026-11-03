#!/usr/bin/env python3
"""Write (or --check) .agents/bootstrap/RELEASE.json: the sha256 of every machinery file this release installs.

Installed projects use it to tell a released file from a locally edited one
(`bootstrap repair`, `bootstrap uninstall`, `acp status`), without the network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout import RELEASE_MANIFEST, REPOSITORY_ROOT, release_manifest  # noqa: E402


def main() -> int:
    target = REPOSITORY_ROOT / RELEASE_MANIFEST
    text = json.dumps(release_manifest(REPOSITORY_ROOT), indent=2) + "\n"
    if "--check" in sys.argv[1:]:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != text:
            print(f"STALE: {RELEASE_MANIFEST} does not match the machinery; run "
                  ".agents/bootstrap/scripts/release-manifest.py", file=sys.stderr)
            return 2
        print(f"OK {RELEASE_MANIFEST}")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"wrote {RELEASE_MANIFEST}: {len(json.loads(text)['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
