#!/usr/bin/env python3
"""Measure what a statement-local parser can and cannot reach on the corpus.

Two questions, both answered against the synthetic corpus and its truth set:

1. Can sqlglot parse the statements the corpus emits, broken down by tier?
   sqlglot does not raise on unsupported PL/SQL - it falls back to a ``Command``
   node - so a plain try/except overstates success. Command results are counted
   separately.

2. What is the ceiling for an engine that only ever looks at one statement?
   Edges that cross a statement boundary (PL/SQL variables, multi-hop transfers,
   dynamic SQL) are removed from the truth set, and what remains is scored as if
   an engine had produced it perfectly. The result is an upper bound no
   statement-local engine can beat.

Usage:

    cd plsql-lineage-corpus && python3 -m synplsql.generate --out out
    python3 ../scripts/measure_parser_ceiling.py --out out

Requires sqlglot for part 1; part 2 runs without it.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import pathlib
import subprocess
import sys


def parse_rates(corpus_dir: pathlib.Path, packages: int, lines: int) -> None:
    """Part 1 - sqlglot parse outcome per tier and statement type."""
    try:
        import sqlglot
        from sqlglot import expressions as exp
    except ImportError:
        print("sqlglot 이 없어 파싱률 측정을 건너뜁니다 (pip install sqlglot)\n")
        return

    sys.path.insert(0, str(corpus_dir))
    from synplsql.core import render_stmt, walk
    from synplsql.generate import generate

    logging.disable(logging.CRITICAL)   # sqlglot logs every fallback
    profile = json.loads((corpus_dir / "profile.json").read_text(encoding="utf-8"))
    pkgs, _, _ = generate(20260812, packages, lines, [0, 1, 2, 3], profile)

    # [real parse, Command fallback, ParseError]
    stats: dict[tuple[int, str], list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for pkg in pkgs:
        for sub in pkg.subprograms:
            for stmt in walk(sub.stmts):
                sql = "\n".join(render_stmt(stmt).lines).strip().rstrip(";")
                if len(sql) < 12:
                    continue
                try:
                    tree = sqlglot.parse_one(sql, dialect="oracle")
                    slot = 1 if isinstance(tree, exp.Command) else 0
                except Exception:
                    slot = 2
                stats[(pkg.tier, type(stmt).__name__)][slot] += 1

    print(f"sqlglot {sqlglot.__version__} - 문장 단위 파싱 결과 "
          f"({packages} 패키지 / {lines:,} 라인 목표)")
    print(f"{'Tier':<5}{'문장 타입':<18}{'정상':>8}{'Command':>9}{'에러':>7}{'정상률':>9}")
    print("-" * 56)
    agg: dict[int, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for (tier, name), counts in sorted(stats.items()):
        for i in range(3):
            agg[tier][i] += counts[i]
        print(f"{tier:<5}{name:<18}{counts[0]:>8,}{counts[1]:>9,}"
              f"{counts[2]:>7,}{counts[0] / sum(counts) * 100:>8.1f}%")
    print("-" * 56)
    for tier, counts in sorted(agg.items()):
        print(f"Tier {tier} 합계{'':<9}{counts[0]:>8,}{counts[1]:>9,}"
              f"{counts[2]:>7,}{counts[0] / sum(counts) * 100:>8.1f}%")
    print()


def crosses_statement(edge: dict) -> str | None:
    """Why this edge is out of reach for a statement-local engine, or None."""
    if edge["kind"] == "UNRESOLVED":
        return "동적 SQL (원리적 불가)"
    if edge["kind"] == "VIA_VARIABLE" or "VARIABLE" in edge.get("via", []):
        return "PL/SQL 변수 경유"
    if edge["hops"] > 1:
        return f"다문장 전이 (hops={edge['hops']})"
    return None


def ceiling(out_dir: pathlib.Path, corpus_dir: pathlib.Path) -> None:
    """Part 2 - score a hypothetical perfect statement-local engine."""
    truth_path = out_dir / "lineage_truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    local, blocked = [], collections.Counter()
    for edge in truth["edges"]:
        reason = crosses_statement(edge)
        if reason:
            blocked[reason] += 1
        else:
            local.append(edge)

    total = len(truth["edges"])
    print(f"정답셋 엣지 {total:,}")
    print(f"  문장 단위로 도달 가능  {len(local):>6,}  ({len(local) / total * 100:.1f}%)")
    print(f"  문장 경계를 넘어야 함  {total - len(local):>6,}  "
          f"({(total - len(local)) / total * 100:.1f}%)")
    for reason, count in blocked.most_common():
        print(f"      {reason:<26}{count:>6,}  ({count / total * 100:>4.1f}%)")
    print()

    ideal = out_dir / "ideal_statement_local_engine.json"
    ideal.write_text(json.dumps({**truth, "edges": local}, ensure_ascii=False),
                     encoding="utf-8")
    print("완벽한 문장 단위 엔진(오답 0건)을 가정하고 채점합니다.")
    print("이 점수를 넘는 문장 단위 엔진은 존재할 수 없습니다.\n")
    subprocess.run(
        [sys.executable, "-m", "synplsql.score",
         "--truth", str(truth_path.resolve()),
         "--manifest", str((out_dir / "manifest.json").resolve()),
         "--engine", str(ideal.resolve()), "--format", "generic"],
        cwd=corpus_dir, check=True)
    ideal.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out"),
                    help="synplsql.generate 의 산출 디렉터리")
    ap.add_argument("--packages", type=int, default=40,
                    help="파싱률 측정에 쓸 패키지 수 (기본 40)")
    ap.add_argument("--lines", type=int, default=60000,
                    help="파싱률 측정에 쓸 라인 목표 (기본 60,000)")
    args = ap.parse_args()

    corpus_dir = (pathlib.Path(__file__).resolve().parents[1] / "plsql-lineage-corpus")
    out_dir = args.out if args.out.is_absolute() else (corpus_dir / args.out)
    if not (out_dir / "lineage_truth.json").exists():
        print(f"{out_dir}/lineage_truth.json 이 없습니다. 먼저 코퍼스를 생성하십시오:\n"
              f"  cd plsql-lineage-corpus && python3 -m synplsql.generate --out "
              f"{args.out}", file=sys.stderr)
        return 1

    parse_rates(corpus_dir, args.packages, args.lines)
    ceiling(out_dir, corpus_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
