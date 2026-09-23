"""CLI: budgeted lineage subgraph for agents.

Reads engine ``edges`` JSON (the same file ``plsqllineage.engine`` writes) and
prints COL / EDGE / DIAG text. Does not re-analyze SQL.

Examples::

    python3 -m plsqllineage.query --input engine.json SYNWMS.OUT_ALLOC
    python3 -m plsqllineage.query --input engine.json explain OUT_ALLOC
    python3 -m plsqllineage.query --input engine.json path OUT_ORDER_D OUT_ALLOC
    python3 -m plsqllineage.query --input engine.json --grain column OUT_ALLOC.ORD_QTY
    python3 -m plsqllineage.query --input engine.json diagnose
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from plsqllineage.agent import (
    DEFAULT_BUDGET,
    DEFAULT_DEPTH,
    load_engine_path,
    parse_kinds,
    render_diagnose,
    render_explain,
    render_path,
    render_query,
)
from plsqllineage.tablequery import (
    load_relations,
    render_table_explain,
    render_table_path,
    render_table_query,
)

COMMANDS = {"query", "explain", "path", "diagnose"}


def _load_raw(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _use_tables(raw: dict, grain: str) -> bool:
    if grain == "column":
        return False
    if grain == "table":
        return True
    return bool(raw.get("relations"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="plsqllineage.query",
        description="엔진 edges JSON 을 에이전트용 부분 그래프 텍스트로 투영")
    ap.add_argument("--input", "-i", "--graph", dest="graph",
                    type=pathlib.Path, required=True,
                    help="엔진 JSON (edges / diagnostics)")
    ap.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                    help="상류/하류 홉 수 (query 기본 2)")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                    help="출력 토큰 상한 (약 3자/토큰)")
    ap.add_argument("--grain", choices=("auto", "table", "column"), default="auto",
                    help="auto 는 relations 가 있으면 테이블, 없으면 컬럼")
    ap.add_argument("--kind", default="value",
                    help="컬럼 grain 전용. value | all | FILTER,UNRESOLVED")
    ap.add_argument("--downstream", action="store_true",
                    help="기본(상류) 대신 하류로 걷는다")
    ap.add_argument("args", nargs="*",
                    help="COL, 또는 explain COL / path A B / diagnose")
    opts = ap.parse_args(argv)

    if not opts.graph.exists():
        print(f"입력을 찾을 수 없습니다: {opts.graph}", file=sys.stderr)
        print("먼저 plsqllineage.engine --out <파일> 로 그래프를 만드십시오.",
              file=sys.stderr)
        return 1

    try:
        raw = _load_raw(opts.graph)
        graph = load_engine_path(opts.graph)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"그래프를 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 1

    tables = load_relations(raw) if _use_tables(raw, opts.grain) else None
    kinds = parse_kinds(opts.kind)
    tokens = list(opts.args)
    cmd = "query"
    if tokens and tokens[0] in COMMANDS:
        cmd = tokens.pop(0)

    if cmd == "diagnose":
        print(render_diagnose(graph, token_budget=opts.budget))
        return 0
    if tables is not None and cmd == "explain":
        if not tokens:
            print("explain 에는 테이블 이름이 필요합니다.", file=sys.stderr)
            return 2
        print(render_table_explain(
            tables, tokens[0], token_budget=opts.budget,
            downstream=opts.downstream))
        return 0
    if tables is not None and cmd == "path":
        if len(tokens) < 2:
            print("path 에는 테이블 둘이 필요합니다.", file=sys.stderr)
            return 2
        print(render_table_path(
            tables, tokens[0], tokens[1], token_budget=opts.budget))
        return 0
    if tables is not None and cmd == "query":
        if not tokens:
            print("조회할 테이블 이름이 필요합니다.", file=sys.stderr)
            return 2
        print(render_table_query(
            tables, tokens[0], depth=opts.depth, token_budget=opts.budget,
            downstream=opts.downstream))
        return 0
    if cmd == "explain":
        if not tokens:
            print("Usage: plsqllineage.query --input FILE explain COL",
                  file=sys.stderr)
            return 2
        print(render_explain(
            graph, tokens[0], token_budget=opts.budget, kinds=kinds,
            downstream=opts.downstream))
        return 0
    if cmd == "path":
        if len(tokens) < 2:
            print("Usage: plsqllineage.query --input FILE path SRC TGT",
                  file=sys.stderr)
            return 2
        print(render_path(
            graph, tokens[0], tokens[1], kinds=kinds,
            token_budget=opts.budget))
        return 0
    if not tokens:
        print("Usage: plsqllineage.query --input FILE COL", file=sys.stderr)
        return 2
    print(render_query(
        graph, tokens[0], depth=opts.depth, token_budget=opts.budget,
        kinds=kinds, downstream=opts.downstream))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
