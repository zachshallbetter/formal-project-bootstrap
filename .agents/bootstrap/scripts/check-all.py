#!/usr/bin/env python3
"""Repository verification gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout import REPOSITORY_ROOT as ROOT  # noqa: E402

SCRIPTS = ".agents/bootstrap/scripts"


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.check_call(args, cwd=ROOT)


def main() -> int:
    run(sys.executable, f"{SCRIPTS}/validate-bootstrap.py", "--check-context")
    run(sys.executable, f"{SCRIPTS}/release-manifest.py", "--check")
    run(sys.executable, f"{SCRIPTS}/validate-formal-files.py")
    run(sys.executable, f"{SCRIPTS}/check-negative-results.py")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    run(sys.executable, f"{SCRIPTS}/package-release.py", "--output", "dist", "--verify-reproducible")
    print("OK all gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
