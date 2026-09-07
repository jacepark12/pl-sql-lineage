"""Parse-completion report: phase times, accuracy counters, bottleneck notes.

The engine already records per-file parse vs rest. This module turns those
samples into a single report printed when a run finishes, so a later pass can
target the slowest phase or the diagnostic codes that actually move F1.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Analysis, FileTiming, StatementTiming

_SLOW_FILES = 8
_SLOW_STATEMENTS = 8


@dataclass
class PhaseShare:
    name: str
    seconds: float
    share: float


@dataclass
class ParseReport:
    started_at: str
    input: str
    elapsed_s: float
    files: int
    parsed: int
    lines: int
    tokens: int
    statements: int
    edges: int
    diagnostics: int
    catalog_s: float
    catalog_tables: int
    phases: list[PhaseShare] = field(default_factory=list)
    warmup_file: str = ""
    warmup_s: float = 0.0
    warmup_lines_per_s: float = 0.0
    warm_files: int = 0
    warm_s: float = 0.0
    warm_lines_per_s: float = 0.0
    lines_per_s: float = 0.0
    parse_failed: int = 0
    decode_failed: int = 0
    diagnostic_counts: dict[str, int] = field(default_factory=dict)
    edge_kinds: dict[str, int] = field(default_factory=dict)
    slow_files: list[dict] = field(default_factory=list)
    slow_statements: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    complete_line: str = ""

    @property
    def parse_rate(self) -> float:
        return (self.parsed / self.files) if self.files else 0.0


def _pct(part: float, whole: float) -> float:
    return part / whole if whole > 0 else 0.0


def _rate(lines: int, seconds: float) -> float:
    return lines / seconds if seconds > 0 else 0.0


def _phase_total(timings: list[FileTiming]) -> dict[str, float]:
    keys = ("decode_s", "wrap_s", "lex_s", "antlr_s",
            "extract_s", "sqlmap_s", "dataflow_s")
    out = {k: 0.0 for k in keys}
    for t in timings:
        for k in keys:
            out[k] += getattr(t, k)
    return out


def _recommendations(report: ParseReport, phases: dict[str, float],
                     parse_s: float, rest_s: float) -> list[str]:
    notes: list[str] = []
    parse_share = _pct(parse_s, report.elapsed_s)
    sqlmap_share = _pct(phases.get("sqlmap_s", 0.0), report.elapsed_s)
    antlr_share = _pct(phases.get("antlr_s", 0.0), report.elapsed_s)
    if report.warmup_s and report.warm_s and report.warm_lines_per_s:
        warmup_ratio = report.warm_lines_per_s / max(report.warmup_lines_per_s, 1e-9)
    else:
        warmup_ratio = 0.0

    if parse_share >= 0.7:
        notes.append(
            f"ANTLR 파싱(decode+wrap+lex+parse)이 벽시계의 {parse_share:.0%}입니다. "
            "한 프로세스에서 파일을 연속 처리해 DFA 캐시를 유지하세요.")
    if antlr_share >= 0.5:
        notes.append(
            f"sql_script() SLL 파싱이 {antlr_share:.0%}입니다. "
            "문법 결정 DFA 워밍업과 큰 패키지가 여기로 모입니다.")
    if warmup_ratio >= 5:
        notes.append(
            f"첫 파일은 이후보다 {warmup_ratio:.0f}배 느립니다. "
            "DFA 워밍업은 앞쪽 몇 파일에 걸쳐 퍼지므로, 작은 파일이 "
            "벽시계 상단에 있어도 라인/s 가 낮으면 워밍업입니다. "
            "파일별 서브프로세스는 이 비용을 매번 다시 냅니다.")
    extract_share = _pct(phases.get("extract_s", 0.0), report.elapsed_s)
    if extract_share >= 0.1:
        notes.append(
            f"structure.extract 가 벽시계의 {extract_share:.0%}입니다. "
            "ANTLR 트리 보행이 sqlglot 문장 분석보다 큽니다.")
    if sqlmap_share >= 0.15:
        notes.append(
            f"sqlmap(문장 분석)이 벽시계의 {sqlmap_share:.0%}입니다. "
            "아래 느린 문장부터 sqlglot 비용을 점검하세요.")
    if rest_s > parse_s and report.elapsed_s > 0:
        notes.append(
            "sqlmap+dataflow 가 파싱보다 깁니다. 문장 수와 카탈로그 전개가 병목일 수 있습니다.")
    if report.parse_failed:
        notes.append(
            f"PARSE_FAILED {report.parse_failed}건 — 문법 커버리지 또는 "
            "ALL_SOURCE CREATE 접두를 확인하세요.")
    if report.decode_failed:
        notes.append(
            f"DECODE_FAILED {report.decode_failed}건 — utf-8/cp949 밖 인코딩입니다.")
    sql_na = report.diagnostic_counts.get("SQL_NOT_ANALYZED", 0)
    if sql_na:
        notes.append(
            f"SQL_NOT_ANALYZED {sql_na}건 — B층이 문장을 포기했습니다. 정확도 개선 대상입니다.")
    unresolved = report.diagnostic_counts.get("UNRESOLVED", 0)
    if unresolved:
        notes.append(
            f"UNRESOLVED {unresolved}건 — 시퀀스·전역·레코드 필드 등 미해소 이름입니다.")
    params = report.diagnostic_counts.get("PARAMETER_UNRESOLVED", 0)
    if params:
        notes.append(
            f"PARAMETER_UNRESOLVED {params}건 — 파일 밖 호출자 분석이 필요합니다.")
    dynamic = report.diagnostic_counts.get("DYNAMIC_SQL", 0)
    if dynamic:
        notes.append(
            f"DYNAMIC_SQL {dynamic}건 — 정적 컬럼 엣지를 만들지 않은 것이 정상입니다.")
    if report.parsed == report.files and not sql_na and report.files:
        notes.append(
            "이 입력에서 파싱은 전부 성공했고 문장 포기도 없습니다. "
            "다음 정확도 개선은 미해소 이름과 고유쌍 F1 쪽입니다.")
    if not notes:
        notes.append("측정된 실패가 없습니다. 단계 비율을 보고 다음 최적화를 고르세요.")
    return notes


def build_report(analysis: Analysis, elapsed_s: float, *,
                 input_path: str = "",
                 started_at: str | None = None) -> ParseReport:
    timings = analysis.timings
    lines = sum(t.lines for t in timings)
    tokens = sum(t.tokens for t in timings)
    statements = sum(t.statements for t in timings)
    phases = _phase_total(timings)
    phases["catalog_s"] = analysis.catalog_s
    parse_s = sum(t.parse_s for t in timings)
    rest_s = sum(t.rest_s for t in timings)

    diag_counts = Counter(d.code for d in analysis.diagnostics)
    edge_kinds = Counter(e.get("kind", "?") for e in analysis.edges)

    first = timings[0] if timings else None
    rest = timings[1:] if timings else []
    warmup_s = first.total_s if first else 0.0
    warm_s = sum(t.total_s for t in rest)
    warm_lines = sum(t.lines for t in rest)

    named = (
        ("decode", phases["decode_s"]),
        ("wrap", phases["wrap_s"]),
        ("lex", phases["lex_s"]),
        ("antlr", phases["antlr_s"]),
        ("extract", phases["extract_s"]),
        ("sqlmap", phases["sqlmap_s"]),
        ("dataflow", phases["dataflow_s"]),
        ("catalog", phases["catalog_s"]),
    )
    shares = [PhaseShare(name, sec, _pct(sec, elapsed_s)) for name, sec in named
              if sec > 0 or name in ("antlr", "sqlmap")]

    warm_rate = _rate(warm_lines, warm_s)
    slow_files = []
    for t in sorted(timings, key=lambda x: x.total_s, reverse=True)[:_SLOW_FILES]:
        rate = _rate(t.lines, t.total_s)
        slow_files.append({
            "file": t.file,
            "lines": t.lines,
            "total_s": round(t.total_s, 4),
            "parse_s": round(t.parse_s, 4),
            "lex_s": round(t.lex_s, 4),
            "antlr_s": round(t.antlr_s, 4),
            "sqlmap_s": round(t.sqlmap_s, 4),
            "dataflow_s": round(t.dataflow_s, 4),
            "lines_per_s": round(rate, 1),
            "ok": t.ok,
            "syntax_problems": t.syntax_problems,
            "warmup": bool(warm_rate > 0 and rate < warm_rate * 0.2),
        })

    slow_statements = []
    for s in sorted(analysis.statement_timings,
                    key=lambda x: x.seconds, reverse=True)[:_SLOW_STATEMENTS]:
        slow_statements.append({
            "file": s.file,
            "line": s.line,
            "kind": s.kind,
            "chars": s.chars,
            "seconds": round(s.seconds, 4),
            "error": s.error,
        })

    report = ParseReport(
        started_at=started_at or _dt.datetime.now(tz=_dt.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        input=input_path,
        elapsed_s=elapsed_s,
        files=analysis.files,
        parsed=analysis.parsed,
        lines=lines,
        tokens=tokens,
        statements=statements,
        edges=len(analysis.edges),
        diagnostics=len(analysis.diagnostics),
        catalog_s=analysis.catalog_s,
        catalog_tables=analysis.catalog_tables,
        phases=shares,
        warmup_file=first.file if first else "",
        warmup_s=warmup_s,
        warmup_lines_per_s=_rate(first.lines, warmup_s) if first else 0.0,
        warm_files=len(rest),
        warm_s=warm_s,
        warm_lines_per_s=_rate(warm_lines, warm_s),
        lines_per_s=_rate(lines, elapsed_s),
        parse_failed=diag_counts.get("PARSE_FAILED", 0),
        decode_failed=diag_counts.get("DECODE_FAILED", 0),
        diagnostic_counts=dict(diag_counts),
        edge_kinds=dict(edge_kinds),
        slow_files=slow_files,
        slow_statements=slow_statements,
    )
    report.recommendations = _recommendations(report, phases, parse_s, rest_s)
    report.complete_line = (
        f"PARSE_COMPLETE files={report.parsed}/{report.files} "
        f"lines={report.lines} elapsed={elapsed_s:.3f}s "
        f"parse={parse_s:.3f}s rest={rest_s:.3f}s "
        f"edges={report.edges} diagnostics={report.diagnostics} "
        f"ok={int(report.parse_failed == 0 and report.decode_failed == 0)}")
    return report


def format_report(report: ParseReport) -> str:
    rate = f"{report.parse_rate:.1%}"
    lines = [
        "======== PL/SQL 리니지 파싱 완료 보고서 ========",
        f"시각: {report.started_at}",
        f"입력: {report.input or '-'}",
        "상태: 완료",
        "",
        "요약",
        f"  파일     {report.parsed}/{report.files} 파싱 ({rate})",
        f"  라인     {report.lines:,}",
        f"  토큰     {report.tokens:,}",
        f"  문장     {report.statements:,}",
        f"  엣지     {report.edges:,}",
        f"  진단     {report.diagnostics:,}",
        f"  카탈로그 {report.catalog_tables:,} 테이블 ({report.catalog_s:.3f}s)",
        f"  벽시계   {report.elapsed_s:.3f}s  ({report.lines_per_s:.1f} 라인/s)",
        "",
        "단계별 시간 (병목)",
    ]
    bottleneck = max(report.phases, key=lambda p: p.seconds, default=None)
    for phase in report.phases:
        mark = "  << 병목" if bottleneck and phase.name == bottleneck.name else ""
        lines.append(
            f"  {phase.name:<10} {phase.seconds:8.3f}s  {phase.share:6.1%}{mark}")

    lines.extend(["", "워밍업"])
    if report.warmup_file:
        lines.append(
            f"  첫 파일 {report.warmup_file}: {report.warmup_s:.3f}s  "
            f"{report.warmup_lines_per_s:.1f} 라인/s")
    if report.warm_files:
        lines.append(
            f"  이후 {report.warm_files} 파일: {report.warm_s:.3f}s  "
            f"{report.warm_lines_per_s:.1f} 라인/s (DFA 웜)")

    lines.extend(["", "정확도"])
    lines.append(f"  PARSE_FAILED          {report.parse_failed}")
    lines.append(f"  DECODE_FAILED         {report.decode_failed}")
    for code in sorted(report.diagnostic_counts):
        if code in ("PARSE_FAILED", "DECODE_FAILED"):
            continue
        lines.append(f"  {code:<22} {report.diagnostic_counts[code]}")
    if report.edge_kinds:
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(report.edge_kinds.items()))
        lines.append(f"  엣지 종류             {kinds}")

    if report.slow_files:
        lines.extend(["", "가장 느린 파일"])
        for item in report.slow_files:
            status = "ok" if item["ok"] else "FAIL"
            tag = "  (워밍업)" if item.get("warmup") else ""
            lines.append(
                f"  {item['total_s']:7.3f}s  {item['lines']:6} lines  "
                f"{item['lines_per_s']:7.0f} 라인/s  "
                f"antlr {item['antlr_s']:.3f}s  sqlmap {item['sqlmap_s']:.3f}s  "
                f"{status}  {item['file']}{tag}")

    if report.slow_statements:
        lines.extend(["", "가장 느린 문장"])
        for item in report.slow_statements:
            err = f"  {item['error']}" if item["error"] else ""
            lines.append(
                f"  {item['seconds']:7.3f}s  {item['chars']:5}c  "
                f"{item['kind']:<12} {item['file']}:{item['line']}{err}")

    lines.extend(["", "권고"])
    for note in report.recommendations:
        lines.append(f"  - {note}")

    lines.extend(["", report.complete_line,
                  "=============================================="])
    return "\n".join(lines) + "\n"


def report_to_dict(report: ParseReport) -> dict:
    payload = asdict(report)
    payload["phases"] = [asdict(p) for p in report.phases]
    return payload
