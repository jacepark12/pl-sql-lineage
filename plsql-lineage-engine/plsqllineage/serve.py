"""MCP stdio server: the same COL/EDGE/DIAG projection as ``plsqllineage.query``.

Does not re-analyze SQL. Loads engine ``edges`` JSON and exposes addressable
column queries as tools. Optional extra::

    pip install mcp
    python3 -m plsqllineage.serve --input engine.json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import threading
from collections import OrderedDict

from plsqllineage.agent import (
    DEFAULT_BUDGET,
    DEFAULT_DEPTH,
    LineageGraph,
    load_engine_path,
    parse_kinds,
    render_diagnose,
    render_explain,
    render_path,
    render_query,
    render_stats,
)

MAX_DEPTH = 8
MIN_BUDGET = 64
MAX_BUDGET = 20_000
DEFAULT_MAX_CONTEXTS = 4

INSTRUCTIONS = (
    "Oracle PL/SQL column lineage. The server reads engine JSON (edges / "
    "diagnostics) and returns budgeted COL/EDGE/DIAG text — never the JSON "
    "itself. Call query_lineage before grepping SQL. Default walk is upstream "
    "value-flow; pass kind=FILTER for WHERE/JOIN influence, kind=all for "
    "everything. Cite at=file:line. If the graph is missing, tell the user to "
    "run python3 -m plsqllineage.engine --out engine.json; do not invent edges."
)


def _clamp_depth(depth: object) -> int:
    try:
        n = int(depth)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_DEPTH
    return max(0, min(n, MAX_DEPTH))


def _clamp_budget(budget: object) -> int:
    try:
        n = int(budget)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_BUDGET
    return max(MIN_BUDGET, min(n, MAX_BUDGET))


def _max_contexts() -> int:
    raw = os.environ.get("PLSQL_LINEAGE_MAX_CONTEXTS", "").strip()
    if not raw:
        return DEFAULT_MAX_CONTEXTS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_CONTEXTS


class _GraphCache:
    """Pinned default graph plus a small LRU of extra engine.json files."""

    def __init__(self, max_contexts: int | None = None):
        self._max_contexts = max_contexts or _max_contexts()
        self._entries: OrderedDict[str, tuple[tuple[int, int], LineageGraph]] = (
            OrderedDict())
        self._pinned: dict[str, tuple[tuple[int, int], LineageGraph]] = {}
        self._lock = threading.Lock()

    def get(self, path: pathlib.Path, *, pinned: bool = False) -> LineageGraph:
        resolved = str(path.resolve())
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            store = self._pinned if pinned else self._entries
            hit = store.get(resolved)
            if hit is not None and hit[0] == key:
                if not pinned:
                    self._entries.move_to_end(resolved)
                return hit[1]
        graph = load_engine_path(path)
        with self._lock:
            if pinned:
                self._pinned[resolved] = (key, graph)
            else:
                self._entries[resolved] = (key, graph)
                self._entries.move_to_end(resolved)
                while len(self._entries) > self._max_contexts:
                    self._entries.popitem(last=False)
        return graph


class LineageSession:
    """Tool handlers. Importable without the ``mcp`` package."""

    def __init__(self, default_path: pathlib.Path | str | None = None):
        self.default_path = (
            pathlib.Path(default_path).resolve() if default_path else None)
        self._cache = _GraphCache()

    def _load(self, engine_path: str | None) -> LineageGraph:
        if engine_path:
            path = pathlib.Path(engine_path)
            pinned = (
                self.default_path is not None
                and path.resolve() == self.default_path)
        elif self.default_path is not None:
            path = self.default_path
            pinned = True
        else:
            raise FileNotFoundError(
                "No engine JSON. Pass engine_path or start the server "
                "with --input engine.json.")
        if not path.exists():
            raise FileNotFoundError(f"Engine JSON not found: {path}")
        return self._cache.get(path, pinned=pinned)

    def _graph(self, engine_path: str | None) -> tuple[LineageGraph | None, str | None]:
        try:
            return self._load(engine_path), None
        except FileNotFoundError as exc:
            return None, str(exc)
        except json.JSONDecodeError as exc:
            return None, (
                f"Engine JSON is corrupted ({exc}). "
                "Re-run python3 -m plsqllineage.engine.")
        except (OSError, ValueError) as exc:
            return None, str(exc)

    def query_lineage(
        self,
        column: str,
        kind: str = "value",
        depth: int = DEFAULT_DEPTH,
        downstream: bool = False,
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        graph, err = self._graph(engine_path)
        if err:
            return err
        return render_query(
            graph, column,
            depth=_clamp_depth(depth),
            token_budget=_clamp_budget(token_budget),
            kinds=parse_kinds(kind),
            downstream=bool(downstream),
        )

    def explain_column(
        self,
        column: str,
        kind: str = "value",
        downstream: bool = False,
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        graph, err = self._graph(engine_path)
        if err:
            return err
        return render_explain(
            graph, column,
            token_budget=_clamp_budget(token_budget),
            kinds=parse_kinds(kind),
            downstream=bool(downstream),
        )

    def shortest_path(
        self,
        source: str,
        target: str,
        kind: str = "value",
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        graph, err = self._graph(engine_path)
        if err:
            return err
        return render_path(
            graph, source, target,
            kinds=parse_kinds(kind),
            token_budget=_clamp_budget(token_budget),
        )

    def diagnose(
        self,
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        graph, err = self._graph(engine_path)
        if err:
            return err
        return render_diagnose(graph, token_budget=_clamp_budget(token_budget))

    def graph_stats(self, engine_path: str | None = None) -> str:
        graph, err = self._graph(engine_path)
        if err:
            return err
        return render_stats(graph)


def _new_mcp_app(name: str, instructions: str):
    try:
        from mcp.server.mcpserver import MCPServer as cls
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as cls
        except ImportError as exc:
            raise ImportError(
                'mcp is not installed. Run: pip install "mcp>=1.2"'
            ) from exc
    try:
        return cls(name, instructions=instructions)
    except TypeError:
        return cls(name)


def _tool(mcp, description: str):
    try:
        return mcp.tool(description=description, structured_output=False)
    except TypeError:
        return mcp.tool(description=description)


def build_server(default_path: pathlib.Path | str | None = None):
    """Register tools/resources. Requires the ``mcp`` extra."""
    session = LineageSession(default_path)
    mcp = _new_mcp_app("plsql-lineage", INSTRUCTIONS)

    @_tool(
        mcp,
        "Trace a column's upstream (default) or downstream value-flow as "
        "budgeted COL/EDGE/DIAG text. column is an FQN or partial FQN "
        "(ORD_QTY, OUT_ALLOC.ORD_QTY, SCHEMA.TABLE.COL). kind=value "
        "hides WHERE/JOIN filters; pass FILTER or all when needed.",
    )
    def query_lineage(
        column: str,
        kind: str = "value",
        depth: int = DEFAULT_DEPTH,
        downstream: bool = False,
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        return session.query_lineage(
            column, kind=kind, depth=depth, downstream=downstream,
            token_budget=token_budget, engine_path=engine_path)

    @_tool(
        mcp,
        "One-hop neighbors of a column with expressions and file:line. "
        "Use when query_lineage is too wide.",
    )
    def explain_column(
        column: str,
        kind: str = "value",
        downstream: bool = False,
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        return session.explain_column(
            column, kind=kind, downstream=downstream,
            token_budget=token_budget, engine_path=engine_path)

    @_tool(
        mcp,
        "Directed value-flow path from source column to target column. "
        "Use when you already know two FQNs and need to know whether "
        "(and how) they connect. Returns No path if they do not.",
    )
    def shortest_path(
        source: str,
        target: str,
        kind: str = "value",
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        return session.shortest_path(
            source, target, kind=kind,
            token_budget=token_budget, engine_path=engine_path)

    @_tool(
        mcp,
        "DYNAMIC_SQL, PARSE_FAILED, and unresolved edges for the loaded "
        "graph. Call when coverage is in question.",
    )
    def diagnose(
        token_budget: int = DEFAULT_BUDGET,
        engine_path: str | None = None,
    ) -> str:
        return session.diagnose(
            token_budget=token_budget, engine_path=engine_path)

    @_tool(
        mcp,
        "Column / assertion / kind / diagnostic counts for the loaded "
        "engine JSON.",
    )
    def graph_stats(engine_path: str | None = None) -> str:
        return session.graph_stats(engine_path=engine_path)

    resource = getattr(mcp, "resource", None)
    if callable(resource):
        try:
            @resource(
                "lineage://stats",
                name="Graph stats",
                description="Column/assertion/kind/diagnostic counts",
                mime_type="text/plain",
            )
            def stats_resource() -> str:
                return session.graph_stats()

            @resource(
                "lineage://diagnose",
                name="Diagnostics",
                description="DYNAMIC_SQL / PARSE_FAILED / UNRESOLVED",
                mime_type="text/plain",
            )
            def diagnose_resource() -> str:
                return session.diagnose()
        except TypeError:
            pass

    return mcp


def serve(default_path: pathlib.Path | str | None = None) -> None:
    """Start the MCP server over stdio."""
    mcp = build_server(default_path)
    run = getattr(mcp, "run", None)
    if callable(run):
        run(transport="stdio")
        return
    stdio = getattr(mcp, "run_stdio_async", None)
    if callable(stdio):
        stdio()
        return
    raise RuntimeError("mcp server has no stdio run method")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="plsqllineage.serve",
        description="Serve engine JSON over MCP stdio (same text as query).")
    ap.add_argument(
        "--input", "-i", "--graph", dest="graph",
        type=pathlib.Path, default=None,
        help="Default engine JSON (edges / diagnostics). Optional if every "
             "tool call passes engine_path.")
    opts = ap.parse_args(argv)
    if opts.graph is not None and not opts.graph.exists():
        print(f"입력을 찾을 수 없습니다: {opts.graph}", file=sys.stderr)
        print("먼저 plsqllineage.engine --out <파일> 로 그래프를 만드십시오.",
              file=sys.stderr)
        return 1
    try:
        serve(opts.graph)
    except ImportError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
