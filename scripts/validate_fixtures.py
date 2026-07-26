#!/usr/bin/env python3
"""Validate fixture layout and expected JSON shape."""

from __future__ import annotations

import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SYNTHETIC_ROOT = ROOT / "fixtures" / "synthetic"
REQUIRED_FILES = (
    "input.sql",
    "expected.objects.json",
    "expected.relationships.json",
    "expected.diagnostics.json",
)


def load_json(path: pathlib.Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{path}: invalid JSON: {exc}") from exc


def validate_case(case_dir: pathlib.Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_FILES:
        if not (case_dir / name).exists():
            errors.append(f"{case_dir}: missing {name}")

    if errors:
        return errors

    input_text = (case_dir / "input.sql").read_text(encoding="utf-8").strip()
    if not input_text:
        errors.append(f"{case_dir}: input.sql is empty")

    objects = load_json(case_dir / "expected.objects.json")
    relationships = load_json(case_dir / "expected.relationships.json")
    diagnostics = load_json(case_dir / "expected.diagnostics.json")

    if not isinstance(objects, dict) or not isinstance(objects.get("objects"), list):
        errors.append(f"{case_dir}: expected.objects.json must contain an objects array")
    if not isinstance(relationships, dict) or not isinstance(relationships.get("relationships"), list):
        errors.append(f"{case_dir}: expected.relationships.json must contain a relationships array")
    if not isinstance(diagnostics, dict) or not isinstance(diagnostics.get("diagnostics"), list):
        errors.append(f"{case_dir}: expected.diagnostics.json must contain a diagnostics array")

    object_ids = {
        item.get("id")
        for item in objects.get("objects", [])
        if isinstance(item, dict)
    }
    for item in objects.get("objects", []):
        if not isinstance(item, dict):
            errors.append(f"{case_dir}: object entries must be objects")
            continue
        for field in ("id", "type", "name"):
            if not item.get(field):
                errors.append(f"{case_dir}: object entry missing {field}: {item}")

    allowed_external_prefixes = ("parameter.", "procedure.", "package.", "statement.dynamic.")
    for rel in relationships.get("relationships", []):
        if not isinstance(rel, dict):
            errors.append(f"{case_dir}: relationship entries must be objects")
            continue
        for field in ("type", "source", "target", "expression"):
            if not rel.get(field):
                errors.append(f"{case_dir}: relationship entry missing {field}: {rel}")
        for endpoint_field in ("source", "target"):
            endpoint = rel.get(endpoint_field)
            if not isinstance(endpoint, str):
                continue
            if endpoint not in object_ids and not endpoint.startswith(allowed_external_prefixes):
                errors.append(
                    f"{case_dir}: {endpoint_field} endpoint is neither an object id "
                    f"nor an allowed external id: {endpoint}"
                )

    return errors


def find_cases() -> list[pathlib.Path]:
    return sorted(path.parent for path in SYNTHETIC_ROOT.rglob("input.sql"))


def main() -> int:
    cases = find_cases()
    if not cases:
        print("no synthetic fixture cases found", file=sys.stderr)
        return 1

    errors: list[str] = []
    for case_dir in cases:
        errors.extend(validate_case(case_dir))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"validated {len(cases)} synthetic fixture cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

