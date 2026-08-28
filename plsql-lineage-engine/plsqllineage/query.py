"""CLI: budgeted lineage subgraph for agents.

Reads engine ``edges`` JSON (the same file ``plsqllineage.engine`` writes) and
prints COL / EDGE / DIAG text. Does not re-analyze SQL.

Examples::

    python3 -m plsqllineage.query --input engine.json SYNWMS.OUT_ALLOC.ORD_QTY
    python3 -m plsqllineage.query --input engine.json explain OUT_ALLOC.ORD_QTY
    python3 -m plsqllineage.query --input engine.json path OUT_ORDER_D.ORD_QTY OUT_ALLOC.ORD_QTY
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
    load_graph,
    parse_kinds,
    render_diagnose,
    render_explain,
    render_path,
    render_query,
)

COMMANDS = {"query", "explain", "path", "diagnose"}


def _load(path: pathlib.Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "edges" not in data:
        raise ValueError(
            "expected engine JSON with an 'edges' array "
            "(run plsqllineage.engine, not the viewer export)")
    return load_graph(data)


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
    ap.add_argument("--kind", default="value",
                    help="value | all | FILTER,UNRESOLVED | 콤마 구분 kind")
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
        graph = _load(opts.graph)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"그래프를 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 1

    kinds = parse_kinds(opts.kind)
    tokens = list(opts.args)
    cmd = "query"
    if tokens and tokens[0] in COMMANDS:
        cmd = tokens.pop(0)

    if cmd == "diagnose":
        print(render_diagnose(graph, token_budget=opts.budget))
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
