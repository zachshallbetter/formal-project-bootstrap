#!/usr/bin/env python3
"""Validate JSON Schemas, formal JSON instances, and YAML when dependencies exist."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout import REPOSITORY_ROOT as ROOT, TEMPLATES  # noqa: E402


def main() -> int:
    try:
        import yaml
        from jsonschema import Draft202012Validator
    except ImportError:
        print("SKIP formal-file validation: install requirements-dev.txt for full gate")
        return 0

    schemas = {}
    schema_paths = sorted([*(ROOT / ".agents/bootstrap/schemas").glob("*.schema.json"),
                           *(ROOT / ".agents/acp/schemas").glob("*.schema.json")])
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema

    resource_template = json.loads((ROOT / TEMPLATES / "formal-resources.json").read_text(encoding="utf-8"))
    Draft202012Validator(schemas["formal-resource-manifest.schema.json"]).validate(resource_template)
    context_policy = json.loads((ROOT / TEMPLATES / "context-sources.json").read_text(encoding="utf-8"))
    Draft202012Validator(schemas["context-sources.schema.json"]).validate(context_policy)

    yaml_paths = list(ROOT.glob("*.yaml")) + list((ROOT / TEMPLATES).rglob("*.yaml"))
    yaml_paths += list((ROOT / ".agents/bootstrap/profiles").rglob("*.yaml")) + list((ROOT / ".github").rglob("*.yml"))
    for path in sorted(set(yaml_paths)):
        yaml.safe_load(path.read_text(encoding="utf-8"))

    print(f"OK formal files: {len(schema_paths)} schemas, 1 formal JSON instance, {len(set(yaml_paths))} yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
