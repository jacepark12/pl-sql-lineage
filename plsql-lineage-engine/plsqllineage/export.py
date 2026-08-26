"""Project engine ``edges`` JSON onto the web viewer's contract.

The engine (and the corpus truth set) emit::

    {"edges": [...], "diagnostics": [...]}

``web/index.html`` reads::

    {"objects": [...], "relationships": [...], "diagnostics": [...]}

This module is that projection. It does not re-analyze SQL.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Value-carrying kinds collapse to viewer "direct". Filters and other non-value
# kinds become "indirect". Dynamic SQL, when the engine records it, is
# "dynamic_sql". A CALL kind would become "call".
DIRECT_KINDS = frozenset({
    "DIRECT", "TRANSFORM", "AGGREGATE", "ANALYTIC",
    "VIA_VARIABLE", "VIA_CTE", "VIA_PIPELINE",
})
INDIRECT_KINDS = frozenset({
    "INDIRECT_FILTER", "INDIRECT", "FILTER", "CONSTANT", "SEVERED",
})
DYNAMIC_KINDS = frozenset({
    "UNRESOLVED", "DYNAMIC", "DYNAMIC_SQL", "EXECUTE_IMMEDIATE",
})
CALL_KINDS = frozenset({"CALL"})

VIEWER_REL_TYPES = frozenset({"direct", "indirect", "call", "dynamic_sql"})

_TYPE_ORDER = {
    "package": 0,
    "procedure": 1,
    "function": 2,
    "parameter": 3,
    "table": 4,
    "view": 5,
    "column": 6,
    "trigger": 7,
    "dynamic_statement": 8,
}


def relationship_type(kind: str | None) -> str:
    """Map an engine (or already-viewer) edge kind onto the viewer contract."""
    raw = (kind or "DIRECT").strip()
    folded = raw.upper()
    if raw in VIEWER_REL_TYPES:
        return raw
    if folded in DIRECT_KINDS:
        return "direct"
    if folded in CALL_KINDS:
        return "call"
    if folded in DYNAMIC_KINDS or "DYNAMIC" in folded:
        return "dynamic_sql"
    if folded in INDIRECT_KINDS or folded.startswith("INDIRECT"):
        return "indirect"
    return "indirect"


def object_id(kind: str, *parts: str | None) -> str:
    """Stable lowercase id, e.g. ``column.synwms.out_alloc.ord_qty``."""
    tokens = [kind]
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if not text:
            continue
        tokens.append(text.lower())
    return ".".join(tokens)


def _display(*parts: str | None) -> str:
    return ".".join(str(p).strip().upper() for p in parts if p and str(p).strip())


def _span_text(location: object) -> str:
    if not location:
        return ""
    if isinstance(location, str):
        return location
    if not isinstance(location, dict):
        return str(location)
    file = str(location.get("file") or "")
    line = location.get("line")
    span = file
    if line is not None and line != "":
        span = f"{file}:{line}" if file else str(line)
    pkg = location.get("package") or ""
    routine = location.get("function") or location.get("procedure") or ""
    qualifier = _display(pkg, routine)
    if qualifier:
        span = f"{span} {qualifier}".strip()
    return span


def to_viewer(data: dict) -> dict:
    """Convert engine JSON (or pass through viewer JSON) to the viewer contract."""
    if not isinstance(data, dict):
        raise TypeError("analysis JSON must be an object")
    if "edges" in data:
        return _from_engine(data)
    if "objects" in data and "relationships" in data:
        diagnostics = data.get("diagnostics")
        if not isinstance(diagnostics, list):
            diagnostics = []
        return {
            "objects": list(data["objects"]),
            "relationships": list(data["relationships"]),
            "diagnostics": [_diagnostic(item) for item in diagnostics],
        }
    raise ValueError(
        "expected engine JSON with 'edges' or viewer JSON with "
        "'objects' and 'relationships'")


def _from_engine(data: dict) -> dict:
    objects: dict[str, dict] = {}
    relationships: list[dict] = []
    seen_rel: set[tuple[str, str, str, str]] = set()

    for edge in data.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        location = edge.get("location") or {}
        if isinstance(location, dict):
            _ensure_program(objects, location)

        rel_type = relationship_type(edge.get("kind"))
        expression = edge.get("transform") or ""
        target_id = _ensure_ref(objects, edge.get("target"))
        if target_id is None:
            continue

        sources = list(edge.get("sources") or [])
        if not sources:
            if rel_type == "dynamic_sql":
                source_id = _ensure_dynamic_statement(
                    objects, location if isinstance(location, dict) else {},
                    expression)
                _add_rel(relationships, seen_rel, rel_type, source_id,
                         target_id, expression)
            continue

        for source in sources:
            source_id = _ensure_ref(objects, source)
            if source_id is None:
                continue
            _add_rel(relationships, seen_rel, rel_type, source_id,
                     target_id, expression)

    diagnostics = [_diagnostic(item) for item in (data.get("diagnostics") or [])
                   if isinstance(item, dict)]

    ordered_objects = sorted(
        objects.values(),
        key=lambda item: (_TYPE_ORDER.get(item["type"], 99), item["id"]))
    relationships.sort(key=lambda item: (
        item["type"], item["source"], item["target"], item["expression"]))
    return {
        "objects": ordered_objects,
        "relationships": relationships,
        "diagnostics": diagnostics,
    }


def _add_rel(relationships: list[dict], seen: set[tuple[str, str, str, str]],
             rel_type: str, source: str, target: str, expression: str) -> None:
    key = (rel_type, source, target, expression)
    if key in seen:
        return
    seen.add(key)
    relationships.append({
        "type": rel_type,
        "source": source,
        "target": target,
        "expression": expression,
    })


def _put(objects: dict[str, dict], oid: str, type_: str, name: str) -> str:
    objects.setdefault(oid, {"id": oid, "type": type_, "name": name})
    return oid


def _ensure_ref(objects: dict[str, dict], ref: object) -> str | None:
    if not isinstance(ref, dict):
        return None
    table = ref.get("table")
    if not table:
        return None
    table = str(table).strip()
    column = ref.get("column")
    table_id = object_id("table", table)
    _put(objects, table_id, "table", table.upper())
    if column is None or column == "":
        return table_id
    column = str(column).strip()
    return _put(objects, object_id("column", table, column),
                "column", _display(table, column))


def _ensure_program(objects: dict[str, dict], location: dict) -> None:
    pkg = (location.get("package") or "").strip()
    func = (location.get("function") or "").strip()
    proc = (location.get("procedure") or "").strip()
    if pkg:
        _put(objects, object_id("package", pkg), "package", pkg.upper())
    if func:
        _put(objects, object_id("function", pkg, func), "function",
             _display(pkg, func))
        return
    if proc:
        _put(objects, object_id("procedure", pkg, proc), "procedure",
             _display(pkg, proc))


def _ensure_dynamic_statement(objects: dict[str, dict], location: dict,
                              expression: str) -> str:
    pkg = (location.get("package") or "").strip()
    routine = (location.get("function") or location.get("procedure") or "").strip()
    line = location.get("line")
    file = (location.get("file") or "").strip()
    if pkg or routine:
        oid = object_id("dynamic_statement", pkg, routine, str(line or ""))
    elif file:
        stem = file.replace("\\", "/").split("/")[-1]
        oid = object_id("dynamic_statement", stem, str(line or ""))
    else:
        oid = object_id("dynamic_statement", "unknown")
    name = expression.strip() or _display(pkg, routine) or file or "DYNAMIC SQL"
    return _put(objects, oid, "dynamic_statement", name)


def _diagnostic(item: dict) -> dict:
    span = item.get("spanText")
    if not span:
        span = _span_text(item.get("location") or item.get("span"))
    return {
        "severity": item.get("severity") or "",
        "code": item.get("code") or "",
        "message": item.get("message") or "",
        "spanText": span or "",
    }


def dumps(data: dict) -> str:
    return json.dumps(to_viewer(data), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="plsqllineage.export",
        description="엔진 edges JSON 을 웹 뷰어 objects/relationships JSON 으로 변환")
    ap.add_argument("--input", "-i", required=True, type=pathlib.Path,
                    help="엔진 JSON 경로")
    ap.add_argument("--out", "-o", type=pathlib.Path,
                    help="뷰어 JSON 경로 (생략하면 stdout)")
    args = ap.parse_args(argv)

    if not args.input.exists():
        print(f"입력을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        return 1

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    viewer = to_viewer(payload)
    text = json.dumps(viewer, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"객체 {len(viewer['objects']):,}  "
              f"관계 {len(viewer['relationships']):,}  "
              f"진단 {len(viewer['diagnostics']):,}")
        print(f"기록: {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
