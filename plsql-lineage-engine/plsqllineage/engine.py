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
import re
import sys
import time
from dataclasses import dataclass, field

from . import sqlmap
from .catalog import load_catalog
from .dataflow import Scope, assignment_binding, resolve_edges
from .parser import parse_file, read_source
from .structure import Subprogram, extract, parse_rowtype_anchor


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
    out = {"table": ref.table, "column": ref.column}
    if ref.dblink:
        out["dblink"] = ref.dblink
    return out


_PARAM_PREFIXES = ("I_", "O_", "P_")


def _variables(subprogram: Subprogram) -> frozenset[str]:
    """Every name declared in scope, folded for case-insensitive lookup."""
    return frozenset(d.name.upper() for d in subprogram.declarations)


def _short_name(name: str) -> str:
    return name.upper().split(".")[-1]


def _is_parameter_name(name: str, subprogram: Subprogram) -> bool:
    """True when a dangling identifier is a procedure parameter, not a local."""
    folded = name.upper()
    short = _short_name(folded)
    decl = subprogram.declaration(folded) or subprogram.declaration(short)
    if decl is not None:
        return decl.is_parameter
    return short.startswith(_PARAM_PREFIXES)


def _describe_dynamic_sql(sql: str) -> str:
    """Literal vs variable vs bind, without turning the SQL string into edges."""
    parts = ["EXECUTE IMMEDIATE / 동적 SQL 은 정적 컬럼 리니지를 만들지 않습니다"]
    rest = re.sub(r"(?is)^\s*EXECUTE\s+IMMEDIATE\s+", "", sql).rstrip(";").strip()
    if re.match(r"(?is)^OPEN\b", sql.strip()):
        parts = ["OPEN FOR 동적 SQL 은 정적 컬럼 리니지를 만들지 않습니다"]
        rest = re.sub(r"(?is)^.*?FOR\s+", "", sql, count=1).rstrip(";").strip()
    if rest[:1] in "'\"" or rest[:2].upper() in ("Q'", "NQ", "N'"):
        parts.append("SQL 이 문자열 리터럴입니다")
    else:
        token = re.match(r"[A-Za-z][\w$#]*", rest)
        if token:
            parts.append(f"SQL 이 변수 {token.group(0)} 에서 조립됩니다")
        else:
            parts.append("SQL 이 표현식에서 조립됩니다")
    if re.search(r"(?i)\bUSING\b", sql):
        parts.append("USING 바인드가 있습니다")
    return ". ".join(parts)


def _empty_source_diagnostic(edge: sqlmap.Edge, subprogram: Subprogram,
                             location: dict) -> Diagnostic | None:
    """Diagnose a dropped edge. Literals stay quiet; parameters need a caller."""
    names = [n for n in edge.unresolved if n]
    if not names:
        return None
    params = [n for n in names if _is_parameter_name(n, subprogram)]
    if params:
        shown = ", ".join(params)
        return Diagnostic(
            "warning", "PARAMETER_UNRESOLVED",
            f"{shown} 는 이 파일 밖의 호출자에서 공급되는 매개변수입니다. "
            "호출자 분석이 필요합니다",
            {**location, "names": params})
    shown = ", ".join(names)
    return Diagnostic(
        "warning", "UNRESOLVED",
        f"소스 없는 엣지 (미해소 이름: {shown})",
        {**location, "names": names})


def _bind_loop_records(subprogram: Subprogram, scope: Scope,
                       variables: frozenset[str],
                       catalog: dict[str, list[str]]) -> None:
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
        result = sqlmap.analyze_projections(sql, variables, catalog)
        for name, sources, kind in result:
            scope.bind(f"{loop.record}.{name}", sources, 1, kind)


def _bind_rowtypes(subprogram: Subprogram, scope: Scope,
                   variables: frozenset[str],
                   catalog: dict[str, list[str]]) -> None:
    """Register ``r T%ROWTYPE`` so later ``r.COL`` reads T.COL.

    Loop records are bound first by the caller; names already in ``scope.held``
    are left alone. ``c%ROWTYPE`` for a known cursor uses that cursor's
    projection rather than inventing a table named ``c``.

    ``%TYPE`` anchors are intentionally not bound. ``v T.COL%TYPE`` is a type,
    not a value that flowed from T.COL — using it as a source invents edges
    when the variable is a parameter, a literal, or filled from another column.
    """
    for decl in subprogram.declarations:
        table = decl.rowtype or parse_rowtype_anchor(decl.type_text)
        if not table:
            continue
        cursor = (subprogram.cursor(table)
                  or subprogram.cursor(table.split(".")[-1]))
        if cursor is not None:
            for name, sources, kind in sqlmap.analyze_projections(
                    cursor.sql, variables, catalog):
                key = f"{decl.name}.{name}"
                if key.upper() not in scope.held:
                    scope.bind(key, sources, 1, kind)
            continue
        scope.rowtypes.setdefault(decl.name.upper(), table)


def analyze_file(path: pathlib.Path, root: pathlib.Path,
                 analysis: Analysis,
                 catalog: dict[str, list[str]] | None = None) -> None:
    catalog = catalog or {}
    parsed = parse_file(path)
    relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)

    analysis.files += 1
    if parsed.decode_error:
        analysis.diagnostics.append(Diagnostic(
            "error", "DECODE_FAILED",
            f"utf-8/cp949 로 읽지 못했습니다 ({parsed.decode_error})",
            {"file": relative, "line": 1}))
        return
    if not parsed.ok:
        first = parsed.problems[0]
        analysis.diagnostics.append(Diagnostic(
            "error", "PARSE_FAILED",
            f"{len(parsed.problems)}건의 구문 오류 (첫 오류: {first.message})",
            {"file": relative, "line": first.line}))
        return
    analysis.parsed += 1

    for package in extract(parsed.tree, parsed.text):
        for subprogram in package.subprograms:
            variables = _variables(subprogram)
            scope = Scope(catalog=catalog)
            _bind_loop_records(subprogram, scope, variables, catalog)
            _bind_rowtypes(subprogram, scope, variables, catalog)
            for statement in subprogram.statements:
                location = {"file": relative, "package": package.name,
                            "procedure": subprogram.name, "line": statement.line}

                if statement.kind == "dynamic_sql":
                    analysis.diagnostics.append(Diagnostic(
                        "warning", "DYNAMIC_SQL",
                        _describe_dynamic_sql(statement.sql), location))
                    continue

                if statement.kind == "assignment":
                    bound = assignment_binding(statement.sql, scope)
                    if bound is not None:
                        name, sources, hops = bound
                        if sources:
                            # The assignment is itself a boundary the value crossed.
                            scope.bind(name, sources, hops + 1, "TRANSFORM")
                        elif "." in name:
                            scope.bind(name, [], 0, "TRANSFORM", empty_ok=True)
                    continue

                result = sqlmap.analyze(statement.sql, variables, catalog)
                if result.error:
                    analysis.diagnostics.append(Diagnostic(
                        "warning", "SQL_NOT_ANALYZED", result.error, location))
                    continue
                for code, message in result.diagnostics:
                    analysis.diagnostics.append(Diagnostic(
                        "warning", code, message, location))

                # A SELECT ... INTO fills names rather than writing a table, so
                # it must reach the scope before any later statement reads them.
                scope.apply(result.bindings)

                for edge in resolve_edges(result.edges, scope):
                    if not edge.sources:
                        note = _empty_source_diagnostic(edge, subprogram, location)
                        if note is not None:
                            analysis.diagnostics.append(note)
                        continue
                    analysis.edges.append({
                        "target": _ref(edge.target),
                        "sources": [_ref(s) for s in edge.sources],
                        "kind": edge.kind,
                        "transform": edge.transform,
                        "hops": edge.hops,
                        "location": location,
                    })


def _find_catalog(target: pathlib.Path) -> pathlib.Path | None:
    """Prefer ``ddl/catalog.sql`` next to a corpus root or a packages/ folder."""

    candidates: list[pathlib.Path] = []
    if target.is_file():
        candidates.extend((
            target.parent / "ddl" / "catalog.sql",
            target.parent.parent / "ddl" / "catalog.sql",
        ))
    else:
        candidates.extend((
            target / "ddl" / "catalog.sql",
            target.parent / "ddl" / "catalog.sql",
        ))
    for path in candidates:
        if path.is_file():
            return path
    return None


def _iter_sql_files(target: pathlib.Path) -> tuple[pathlib.Path, list[pathlib.Path]]:
    """Root used for relative paths, and the PL/SQL files to analyze.

    A corpus root contains ``packages/*.sql`` plus ``ddl/catalog.sql``. The
    catalog is DDL, not a package, so walking every ``*.sql`` would try to
    parse it as PL/SQL and emit a false PARSE_FAILED.
    """
    if target.is_file():
        return target.parent, [target]
    packages = target / "packages"
    if packages.is_dir():
        return target, sorted(packages.rglob("*.sql"))
    files = [path for path in sorted(target.rglob("*.sql"))
             if path.name.lower() != "catalog.sql"]
    return target, files


def analyze_path(target: pathlib.Path) -> Analysis:
    analysis = Analysis()
    catalog: dict[str, list[str]] = {}
    catalog_path = _find_catalog(target)
    if catalog_path is not None:
        try:
            catalog_text, _ = read_source(catalog_path)
        except UnicodeDecodeError:
            catalog_text = catalog_path.read_text(encoding="utf-8", errors="replace")
        catalog = load_catalog(catalog_text)
    root, files = _iter_sql_files(target)
    for path in files:
        analyze_file(path, root, analysis, catalog)
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
