"""Tie the layers together and emit lineage for a tree of PL/SQL files.

    A  structure.extract   subprograms, declarations, statement extents
    B  sqlmap.analyze      column lineage inside each statement
    C  dataflow.Scope      values carried across statements through variables

Output matches the corpus truth format so ``synplsql.score --format generic``
can read it directly.

Files are independent (no cross-file dataflow), so a persistent worker pool
can cut wall clock. ANTLR still caches its decision DFA on the parser class:
the first file in a process pays a large warm-up and the rest run roughly ten
times faster. Spawn a process per file and that cost repeats; ``--jobs N``
keeps N processes alive. On fork the parent parses the first few real files
so children inherit a populated DFA. New DFA states stop being recorded at
``--dfa-max-states`` (default 4096).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import multiprocessing
import os
import pathlib
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import sqlmap
from .catalog import load_catalog
from .dataflow import Scope, assignment_binding, resolve_edges
from .dynamic import recover_dynamic_sql
from .tablemap import statement_relations
from .dfa import (
    DEFAULT_PARSER_DFA_MAX_STATES,
    parser_dfa_max_states,
    set_parser_dfa_max_states,
)
from .parser import parse_file, read_source, warmup_parser
from .report import build_report, format_report, report_to_dict
from .structure import Subprogram, extract, parse_rowtype_anchor

_SLOW_STATEMENT_KEEP = 24


@dataclass
class Diagnostic:
    severity: str
    code: str
    message: str
    location: dict


@dataclass
class FileTiming:
    file: str
    lines: int
    parse_s: float
    rest_s: float
    ok: bool
    decode_s: float = 0.0
    wrap_s: float = 0.0
    lex_s: float = 0.0
    antlr_s: float = 0.0
    extract_s: float = 0.0
    sqlmap_s: float = 0.0
    dataflow_s: float = 0.0
    tokens: int = 0
    statements: int = 0
    edges: int = 0
    diagnostics: int = 0
    syntax_problems: int = 0
    encoding: str | None = None
    parse_mode: str = "SLL"
    sll_s: float = 0.0
    ll_s: float = 0.0

    @property
    def total_s(self) -> float:
        return self.parse_s + self.rest_s


@dataclass
class StatementTiming:
    file: str
    line: int
    kind: str
    chars: int
    seconds: float
    error: str | None = None


@dataclass
class Analysis:
    edges: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    files: int = 0
    parsed: int = 0
    timings: list[FileTiming] = field(default_factory=list)
    statement_timings: list[StatementTiming] = field(default_factory=list)
    catalog_s: float = 0.0
    catalog_tables: int = 0
    jobs: int = 1


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


def _relation(source: str, target: str, operation: str, method: str,
              location: dict) -> dict:
    return {
        "source": source,
        "target": target,
        "operation": operation,
        "method": method,
        "location": location,
    }


def _record_table_relations(analysis: Analysis, sql: str, method: str,
                            location: dict) -> bool:
    """Append table relations. Return whether any relation was recorded."""
    result = statement_relations(sql)
    if result.error:
        return False
    for code, message in result.diagnostics:
        analysis.diagnostics.append(Diagnostic(
            "warning", code, message, location))
    wrote = False
    for relation in result.relations:
        analysis.relations.append(_relation(
            relation.source, relation.target, relation.operation, method,
            location))
        wrote = True
    return wrote


def _describe_dynamic_sql(sql: str) -> str:
    """Literal vs variable vs bind, for statements whose tables stay unknown."""
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


def _record_statement(analysis: Analysis, item: StatementTiming) -> None:
    held = analysis.statement_timings
    if len(held) < _SLOW_STATEMENT_KEEP:
        held.append(item)
        return
    slowest = min(held, key=lambda s: s.seconds)
    if item.seconds > slowest.seconds:
        held.remove(slowest)
        held.append(item)


def _file_timing(relative: str, lines: int, parse_s: float, rest_s: float,
                 ok: bool, parsed, *, extract_s: float = 0.0,
                 sqlmap_s: float = 0.0, dataflow_s: float = 0.0,
                 statements: int = 0, edges: int = 0,
                 diagnostics: int = 0) -> FileTiming:
    profile = parsed.profile
    return FileTiming(
        relative, lines, parse_s, rest_s, ok,
        decode_s=profile.decode_s, wrap_s=profile.wrap_s,
        lex_s=profile.lex_s, antlr_s=profile.antlr_s,
        extract_s=extract_s, sqlmap_s=sqlmap_s, dataflow_s=dataflow_s,
        tokens=profile.tokens, statements=statements, edges=edges,
        diagnostics=diagnostics, syntax_problems=len(parsed.problems),
        encoding=parsed.encoding, parse_mode=profile.mode,
        sll_s=profile.sll_s, ll_s=profile.ll_s)


def analyze_file(path: pathlib.Path, root: pathlib.Path,
                 analysis: Analysis,
                 catalog: dict[str, list[str]] | None = None) -> None:
    catalog = catalog or {}
    relative = _relpath(path, root)
    t_parse = time.perf_counter()
    parsed = parse_file(path)
    parse_s = time.perf_counter() - t_parse
    lines = parsed.text.count("\n") + 1 if parsed.text else 0
    t_rest = time.perf_counter()
    diag_before = len(analysis.diagnostics)
    edge_before = len(analysis.edges)

    analysis.files += 1
    if parsed.decode_error:
        analysis.diagnostics.append(Diagnostic(
            "error", "DECODE_FAILED",
            f"utf-8/cp949 로 읽지 못했습니다 ({parsed.decode_error})",
            {"file": relative, "line": 1}))
        analysis.timings.append(_file_timing(
            relative, lines, parse_s, time.perf_counter() - t_rest, False,
            parsed, diagnostics=1))
        return
    if not parsed.ok:
        first = parsed.problems[0]
        analysis.diagnostics.append(Diagnostic(
            "error", "PARSE_FAILED",
            f"{len(parsed.problems)}건의 구문 오류 (첫 오류: {first.message})",
            {"file": relative, "line": first.line}))
        analysis.timings.append(_file_timing(
            relative, lines, parse_s, time.perf_counter() - t_rest, False,
            parsed, diagnostics=1))
        return
    analysis.parsed += 1

    t_extract = time.perf_counter()
    packages = extract(parsed.tree, parsed.text)
    extract_s = time.perf_counter() - t_extract
    sqlmap_s = 0.0
    dataflow_s = 0.0
    statements = 0

    for package in packages:
        for subprogram in package.subprograms:
            variables = _variables(subprogram)
            scope = Scope(catalog=catalog)
            t_sql = time.perf_counter()
            _bind_loop_records(subprogram, scope, variables, catalog)
            _bind_rowtypes(subprogram, scope, variables, catalog)
            sqlmap_s += time.perf_counter() - t_sql
            for statement in subprogram.statements:
                statements += 1
                location = {"file": relative, "package": package.name,
                            "procedure": subprogram.name, "line": statement.line}

                if statement.kind == "dynamic_sql":
                    recovered = recover_dynamic_sql(statement.sql)
                    wrote = False
                    if recovered.sql:
                        wrote = _record_table_relations(
                            analysis, recovered.sql, "dynamic-literal",
                            location)
                    if wrote and recovered.partial:
                        analysis.diagnostics.append(Diagnostic(
                            "warning", "DYNAMIC_SQL_PARTIAL",
                            "변수 조각은 테이블로 해석하지 않았습니다. "
                            "리터럴에 이름이 있는 테이블만 관계로 남겼습니다",
                            location))
                    elif not wrote:
                        analysis.diagnostics.append(Diagnostic(
                            "warning", "DYNAMIC_SQL",
                            _describe_dynamic_sql(statement.sql), location))
                    continue

                if statement.kind == "assignment":
                    t_df = time.perf_counter()
                    bound = assignment_binding(statement.sql, scope)
                    if bound is not None:
                        name, sources, hops = bound
                        if sources:
                            # The assignment is itself a boundary the value crossed.
                            scope.bind(name, sources, hops + 1, "TRANSFORM")
                        elif "." in name:
                            scope.bind(name, [], 0, "TRANSFORM", empty_ok=True)
                    dataflow_s += time.perf_counter() - t_df
                    continue

                t_sql = time.perf_counter()
                result = sqlmap.analyze(statement.sql, variables, catalog)
                elapsed_sql = time.perf_counter() - t_sql
                sqlmap_s += elapsed_sql
                _record_statement(analysis, StatementTiming(
                    relative, statement.line, statement.kind,
                    len(statement.sql), elapsed_sql, result.error))
                if result.error:
                    analysis.diagnostics.append(Diagnostic(
                        "warning", "SQL_NOT_ANALYZED", result.error, location))
                    continue
                for code, message in result.diagnostics:
                    analysis.diagnostics.append(Diagnostic(
                        "warning", code, message, location))

                # A SELECT ... INTO fills names rather than writing a table, so
                # it must reach the scope before any later statement reads them.
                t_df = time.perf_counter()
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
                _record_table_relations(
                    analysis, statement.sql, "static", location)
                dataflow_s += time.perf_counter() - t_df

    analysis.timings.append(_file_timing(
        relative, lines, parse_s, time.perf_counter() - t_rest, True, parsed,
        extract_s=extract_s, sqlmap_s=sqlmap_s, dataflow_s=dataflow_s,
        statements=statements,
        edges=len(analysis.edges) - edge_before,
        diagnostics=len(analysis.diagnostics) - diag_before))


def _absorb(dst: Analysis, src: Analysis) -> None:
    """Merge one file's result into the run. Order is the caller's job."""
    dst.files += src.files
    dst.parsed += src.parsed
    dst.edges.extend(src.edges)
    dst.relations.extend(src.relations)
    dst.diagnostics.extend(src.diagnostics)
    dst.timings.extend(src.timings)
    for item in src.statement_timings:
        _record_statement(dst, item)


def _relpath(path: pathlib.Path, root: pathlib.Path) -> str:
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


# Set in ``_init_worker``: (nfiles, started, done, lock, progress).
_WORKER_STATE: tuple | None = None


def _init_worker(nfiles: int, started, done, lock, progress: bool,
                 dfa_max_states: int | None = None) -> None:
    global _WORKER_STATE
    if dfa_max_states is not None:
        set_parser_dfa_max_states(dfa_max_states)
    warmup_parser()
    _WORKER_STATE = (nfiles, started, done, lock, progress)


def _bump(counter, lock) -> int:
    with lock:
        counter.value += 1
        return int(counter.value)


def _log_parse_run(nfiles: int, jobs: int) -> None:
    print(f"PARSE_RUN pid={os.getpid()} files={nfiles} jobs={jobs}",
          file=sys.stderr, flush=True)


def _log_parse_start(relative: str, started: int, nfiles: int) -> None:
    print(f"PARSE_START pid={os.getpid()} started={started}/{nfiles} "
          f"file={relative}",
          file=sys.stderr, flush=True)


def _log_parse_done(relative: str, done: int, nfiles: int,
                    last: FileTiming) -> None:
    status = "ok" if last.ok else "FAIL"
    print(f"PARSE_DONE pid={os.getpid()} done={done}/{nfiles} "
          f"file={relative}  {last.lines} lines  "
          f"lex {last.lex_s:.2f}s  antlr {last.antlr_s:.2f}s  "
          f"{last.parse_mode}  sqlmap {last.sqlmap_s:.2f}s  "
          f"total {last.total_s:.2f}s  {status}",
          file=sys.stderr, flush=True)


def _analyze_one(spec: tuple[str, str, dict[str, list[str]]]) -> Analysis:
    """Worker entry: one file, pickleable, no ANTLR tree in the return value."""
    path_s, root_s, catalog = spec
    path = pathlib.Path(path_s)
    root = pathlib.Path(root_s)
    relative = _relpath(path, root)
    state = _WORKER_STATE
    if state and state[4]:
        nfiles, started, _done, lock, _progress = state
        _log_parse_start(relative, _bump(started, lock), nfiles)
    analysis = Analysis()
    analyze_file(path, root, analysis, catalog)
    if state and state[4] and analysis.timings:
        nfiles, _started, done, lock, _progress = state
        _log_parse_done(relative, _bump(done, lock), nfiles,
                        analysis.timings[-1])
    return analysis


def _mp_context():
    methods = multiprocessing.get_all_start_methods()
    name = "fork" if "fork" in methods else "spawn"
    return multiprocessing.get_context(name)


def resolve_jobs(jobs: int, nfiles: int) -> int:
    """Clamp ``--jobs`` so a single file never starts a pool."""
    if nfiles <= 1:
        return 1
    if jobs == 0:
        jobs = os.cpu_count() or 1
    return max(1, min(jobs, nfiles))


# How many input files the parent parses before forking. A tiny synthetic
# unit does not fill PlSqlParser.decisionsToDFA; the first real files do.
# Leave at least ``jobs`` files for the pool.
_DFA_WARM_FILES = 8


def _parent_warmup_count(nfiles: int, jobs: int) -> int:
    if jobs <= 1:
        return nfiles
    return min(_DFA_WARM_FILES, max(0, nfiles - jobs))


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


def analyze_path(target: pathlib.Path, *, progress: bool = False,
                 jobs: int = 1) -> Analysis:
    analysis = Analysis()
    catalog: dict[str, list[str]] = {}
    catalog_path = _find_catalog(target)
    if catalog_path is not None:
        t_cat = time.perf_counter()
        try:
            catalog_text, _ = read_source(catalog_path)
        except UnicodeDecodeError:
            catalog_text = catalog_path.read_text(encoding="utf-8", errors="replace")
        catalog = load_catalog(catalog_text)
        analysis.catalog_s = time.perf_counter() - t_cat
        analysis.catalog_tables = len(catalog)
    root, files = _iter_sql_files(target)
    jobs = resolve_jobs(jobs, len(files))
    analysis.jobs = jobs
    nfiles = len(files)
    if progress:
        _log_parse_run(nfiles, jobs)
    warm_n = _parent_warmup_count(nfiles, jobs)
    started = 0
    done = 0
    for path in files[:warm_n]:
        relative = _relpath(path, root)
        if progress:
            started += 1
            _log_parse_start(relative, started, nfiles)
        analyze_file(path, root, analysis, catalog)
        if progress and analysis.timings:
            done += 1
            _log_parse_done(relative, done, nfiles, analysis.timings[-1])
    rest = files[warm_n:]
    if jobs <= 1 or not rest:
        return analysis

    ctx = _mp_context()
    work = sorted(rest, key=lambda p: p.stat().st_size, reverse=True)
    started_c = ctx.Value("i", started)
    done_c = ctx.Value("i", done)
    lock = ctx.Lock()
    parts: dict[str, Analysis] = {}
    with ProcessPoolExecutor(
            max_workers=jobs, mp_context=ctx,
            initializer=_init_worker,
            initargs=(nfiles, started_c, done_c, lock, progress,
                      parser_dfa_max_states())) as pool:
        futures = {
            pool.submit(
                _analyze_one,
                (str(path), str(root), catalog),
            ): path
            for path in work
        }
        for future in as_completed(futures):
            path = futures[future]
            part = future.result()
            relative = _relpath(path, root)
            parts[relative] = part
    for path in rest:
        _absorb(analysis, parts[_relpath(path, root)])
    return analysis


def _print_timing_summary(analysis: Analysis, elapsed: float,
                          input_path: str = "") -> None:
    report = build_report(analysis, elapsed, input_path=input_path)
    print(format_report(report), end="", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="plsqllineage",
                                 description="Oracle PL/SQL 컬럼 리니지 추출")
    ap.add_argument("--input", required=True, type=pathlib.Path,
                    help=".sql 파일 또는 디렉터리")
    ap.add_argument("--out", type=pathlib.Path, help="결과 JSON 경로")
    ap.add_argument("--format", choices=("generic", "viewer"), default="generic",
                    help="generic=정답셋 edges (기본), viewer=web/index.html 계약")
    ap.add_argument("--progress", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="파일 파싱 시작/완료를 stderr 에 실시간 출력 "
                         "(기본 on, --no-progress 로 끔)")
    ap.add_argument("--timings", type=pathlib.Path,
                    help="파일별 시간 JSON (edges 출력과 분리)")
    ap.add_argument("--report", type=pathlib.Path,
                    help="파싱 완료 보고서(텍스트) 경로")
    ap.add_argument("--report-json", type=pathlib.Path,
                    help="파싱 완료 보고서 JSON 경로")
    ap.add_argument("--jobs", type=int, default=1, metavar="N",
                    help="파일 워커 수 (기본 1). 0 이면 CPU 개수. "
                         "파일마다 프로세스를 새로 만들지 않고 워커마다 DFA 를 유지")
    ap.add_argument("--dfa-max-states", type=int,
                    default=DEFAULT_PARSER_DFA_MAX_STATES,
                    metavar="N",
                    help="파서 DFA 기록 상한 (기본 4096). 0 이면 무제한. "
                         "한도에 닿으면 기존 캐시는 유지하고 새 state 는 남기지 않습니다")
    args = ap.parse_args(argv)

    if not args.input.exists():
        print(f"입력을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        return 1
    if args.dfa_max_states < 0:
        print(f"--dfa-max-states 는 0 이상이어야 합니다: {args.dfa_max_states}",
              file=sys.stderr)
        return 1
    set_parser_dfa_max_states(args.dfa_max_states)

    started = time.time()
    analysis = analyze_path(args.input, progress=args.progress, jobs=args.jobs)
    elapsed = time.time() - started
    report = build_report(analysis, elapsed, input_path=str(args.input))

    payload = {
        "edges": analysis.edges,
        "relations": analysis.relations,
        "diagnostics": [dataclasses.asdict(d) for d in analysis.diagnostics],
    }
    if args.format == "viewer":
        from .export import to_viewer
        payload = to_viewer(payload)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    if args.timings:
        args.timings.parent.mkdir(parents=True, exist_ok=True)
        args.timings.write_text(json.dumps(
            [{**dataclasses.asdict(t), "total_s": t.total_s}
             for t in analysis.timings],
            ensure_ascii=False, indent=2), encoding="utf-8")
    text = format_report(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
            encoding="utf-8")

    print(f"파일 {analysis.parsed}/{analysis.files} 파싱  "
          f"컬럼 엣지 {len(analysis.edges):,}  "
          f"테이블 관계 {len(analysis.relations):,}  "
          f"진단 {len(analysis.diagnostics)}  "
          f"{elapsed:.1f}s")
    if args.format == "viewer":
        print(f"뷰어 객체 {len(payload['objects']):,}  "
              f"관계 {len(payload['relationships']):,}")
    if elapsed > 0:
        total_lines = sum(t.lines for t in analysis.timings)
        if total_lines:
            print(f"라인 {total_lines:,}  {total_lines / elapsed:.1f} 라인/s")
    print(text, end="", file=sys.stderr)
    if args.out:
        print(f"기록: {args.out}")
    if args.report:
        print(f"보고서: {args.report}")
    if args.report_json:
        print(f"보고서 JSON: {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
