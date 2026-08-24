"""Tie the layers together and emit lineage for a tree of PL/SQL files.

    A  structure.extract   subprograms, declarations, statement extents
    B  sqlmap.analyze      column lineage inside each statement
    C  dataflow.Scope      values carried across statements through variables

Output matches the corpus truth format so ``synplsql.score --format generic``
can read it directly.

Files are analyzed in one process on purpose. ANTLR caches its decision DFA on
the parser class, so the first file pays a large one-time warm-up and the rest
run roughly ten times faster; a per-file subprocess would pay it every time.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
import time
from dataclasses import dataclass, field

from . import sqlmap
from .dataflow import Scope, assignment_binding, resolve_edges
from .parser import parse_file
from .structure import Subprogram, extract


@dataclass
class Diagnostic:
    severity: str
    code: str
    message: str
    location: dict


@dataclass
class Analysis:
    edges: list[dict] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    files: int = 0
    parsed: int = 0


def _ref(ref: sqlmap.Ref) -> dict:
    return {"table": ref.table, "column": ref.column}


def _variables(subprogram: Subprogram) -> frozenset[str]:
    """Every name declared in scope, folded for case-insensitive lookup."""
    return frozenset(d.name.upper() for d in subprogram.declarations)


def _bind_loop_records(subprogram: Subprogram, scope: Scope,
                       variables: frozenset[str]) -> None:
    """Bind each loop record's fields to its query, before the body is read.

    ``FOR rec IN c_pick LOOP ... rec.PICK_QTY ...`` reads a projection of the
    cursor's SELECT. Binding is done up front rather than in statement order:
    a loop record is filled by its own query and by nothing else, so there is
    no earlier value it could shadow.
    """
    for loop in subprogram.loops:
        sql = loop.sql
        if sql is None and loop.cursor:
            cursor = subprogram.cursor(loop.cursor)
            sql = cursor.sql if cursor else None
        if not sql:
            continue
        result = sqlmap.analyze_projections(sql, variables)
        for name, sources, kind in result:
            scope.bind(f"{loop.record}.{name}", sources, 1, kind)


def analyze_file(path: pathlib.Path, root: pathlib.Path,
                 analysis: Analysis) -> None:
    text = path.read_text(encoding="utf-8")
    parsed = parse_file(path)
    relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)

    analysis.files += 1
    if not parsed.ok:
        first = parsed.problems[0]
        analysis.diagnostics.append(Diagnostic(
            "error", "PARSE_FAILED",
            f"{len(parsed.problems)}건의 구문 오류 (첫 오류: {first.message})",
            {"file": relative, "line": first.line}))
        return
    analysis.parsed += 1

    for package in extract(parsed.tree, text):
        for subprogram in package.subprograms:
            variables = _variables(subprogram)
            scope = Scope()
            _bind_loop_records(subprogram, scope, variables)
            for statement in subprogram.statements:
                location = {"file": relative, "package": package.name,
                            "procedure": subprogram.name, "line": statement.line}

                if statement.kind == "assignment":
                    bound = assignment_binding(statement.sql, scope)
                    if bound is not None:
                        name, sources, hops = bound
                        # The assignment is itself a boundary the value crossed.
                        scope.bind(name, sources, hops + 1, "TRANSFORM")
                    continue

                result = sqlmap.analyze(statement.sql, variables)
                if result.error:
                    analysis.diagnostics.append(Diagnostic(
                        "warning", "SQL_NOT_ANALYZED", result.error, location))
                    continue

                # A SELECT ... INTO fills names rather than writing a table, so
                # it must reach the scope before any later statement reads them.
                scope.apply(result.bindings)

                for edge in resolve_edges(result.edges, scope):
                    if not edge.sources:
                        continue          # nothing bound anywhere
                    analysis.edges.append({
                        "target": _ref(edge.target),
                        "sources": [_ref(s) for s in edge.sources],
                        "kind": edge.kind,
                        "transform": edge.transform,
                        "hops": edge.hops,
                        "location": location,
                    })


def analyze_path(target: pathlib.Path) -> Analysis:
    analysis = Analysis()
    if target.is_file():
        analyze_file(target, target.parent, analysis)
        return analysis
    for path in sorted(target.rglob("*.sql")):
        analyze_file(path, target, analysis)
    return analysis


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="plsqllineage",
                                 description="Oracle PL/SQL 컬럼 리니지 추출")
    ap.add_argument("--input", required=True, type=pathlib.Path,
                    help=".sql 파일 또는 디렉터리")
    ap.add_argument("--out", type=pathlib.Path, help="결과 JSON 경로")
    args = ap.parse_args(argv)

    if not args.input.exists():
        print(f"입력을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        return 1

    started = time.time()
    analysis = analyze_path(args.input)
    elapsed = time.time() - started

    payload = {
        "edges": analysis.edges,
        "diagnostics": [dataclasses.asdict(d) for d in analysis.diagnostics],
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    print(f"파일 {analysis.parsed}/{analysis.files} 파싱  "
          f"엣지 {len(analysis.edges):,}  진단 {len(analysis.diagnostics)}  "
          f"{elapsed:.1f}s")
    if args.out:
        print(f"기록: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
