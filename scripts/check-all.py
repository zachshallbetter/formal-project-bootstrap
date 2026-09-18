#!/usr/bin/env python3
"""Repository verification gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.check_call(args, cwd=ROOT)


def main() -> int:
    run(sys.executable, "scripts/validate-bootstrap.py", "--check-context")
    run(sys.executable, "scripts/validate-formal-files.py")
    run(sys.executable, "scripts/check-negative-results.py")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    run(sys.executable, "scripts/package-release.py", "--output", "dist", "--verify-reproducible")
    print("OK all gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
