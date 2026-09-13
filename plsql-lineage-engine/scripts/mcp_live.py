#!/usr/bin/env python3
"""Call lineage MCP tools over stdio — the same path Cursor uses.

Spawns ``plsqllineage.serve --ui`` as a child. Chat-shaped text comes back on
stdout; the viewer at ``?live=`` paints the walk. Not a substitute for
Cursor: it exists so tests can drive the stdio channel without the IDE.

Examples::

    PYTHONPATH=plsql-lineage-engine python3 scripts/mcp_live.py \\
        --input tests/fixtures/engine_sample.json \\
        query_lineage OUT_ALLOC.ORD_QTY

    # Keep the server up and send further calls, one per line:
    #   query_lineage IF_STOCK_SND.QTY
    #   explain_column OUT_ALLOC.ORD_QTY
    #   shortest_path OUT_ORDER_D.ORD_QTY OUT_ALLOC.ORD_QTY
    PYTHONPATH=plsql-lineage-engine python3 scripts/mcp_live.py --input engine.json --repl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _tool_text(result) -> str:
    content = getattr(result, "content", None) or []
    if content:
        return content[0].text
    return str(result)


def _wait_http(base: str, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        time.sleep(0.1)
    raise RuntimeError(f"UI HTTP did not start at {base}: {last}")


async def _call(session: ClientSession, tool: str, arguments: dict) -> str:
    result = await session.call_tool(tool, arguments)
    if getattr(result, "is_error", False):
        raise RuntimeError(_tool_text(result) or "MCP tool error")
    return _tool_text(result)


def _parse_line(line: str) -> tuple[str, dict] | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    if raw in {"quit", "exit"}:
        raise EOFError
    parts = raw.split()
    tool = parts[0]
    if tool == "query_lineage":
        if len(parts) < 2:
            raise ValueError("query_lineage <column>")
        args: dict = {"column": parts[1]}
        if len(parts) > 2:
            args["kind"] = parts[2]
        return tool, args
    if tool == "explain_column":
        if len(parts) < 2:
            raise ValueError("explain_column <column>")
        return tool, {"column": parts[1]}
    if tool == "shortest_path":
        if len(parts) < 3:
            raise ValueError("shortest_path <source> <target>")
        return tool, {"source": parts[1], "target": parts[2]}
    if tool in {"diagnose", "graph_stats"}:
        return tool, {}
    raise ValueError(f"unknown tool: {tool}")


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mcp_live")
    ap.add_argument("--input", "-i", type=Path, required=True)
    ap.add_argument("--ui", default="127.0.0.1:8765")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--cwd", type=Path, default=None)
    ap.add_argument("--repl", action="store_true",
                    help="Read further tool calls from stdin after the first.")
    ap.add_argument("tool", nargs="?", default=None)
    ap.add_argument("args", nargs="*")
    opts = ap.parse_args(argv)
    if not opts.input.exists():
        print(f"engine JSON not found: {opts.input}", file=sys.stderr)
        return 1
    engine_dir = Path(__file__).resolve().parents[1]
    cwd = str(opts.cwd or engine_dir)
    env = {
        "PYTHONPATH": str(engine_dir),
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    params = StdioServerParameters(
        command=opts.python,
        args=["-m", "plsqllineage.serve",
              "--input", str(opts.input.resolve()),
              "--ui", opts.ui],
        env=env,
        cwd=cwd,
    )
    first = None
    if opts.tool:
        first = _parse_line(" ".join([opts.tool, *opts.args]))

    host, _, port = opts.ui.rpartition(":")
    base = f"http://{host or '127.0.0.1'}:{port}"

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await asyncio.to_thread(_wait_http, base)
            print(f"READY live={base} viewer=http://127.0.0.1:4173/?live={base}",
                  flush=True)
            if first:
                text = await _call(session, first[0], first[1])
                print(text, flush=True)
            if opts.repl or not first:
                print("# stdin: query_lineage COL | explain_column COL | "
                      "shortest_path A B | diagnose | graph_stats | quit",
                      file=sys.stderr, flush=True)
                loop = asyncio.get_running_loop()
                while True:
                    try:
                        line = await loop.run_in_executor(None, sys.stdin.readline)
                    except KeyboardInterrupt:
                        break
                    if line == "":
                        break
                    try:
                        parsed = _parse_line(line)
                    except EOFError:
                        break
                    except ValueError as exc:
                        print(f"# {exc}", file=sys.stderr, flush=True)
                        continue
                    if parsed is None:
                        continue
                    text = await _call(session, parsed[0], parsed[1])
                    print(text, flush=True)
                    snap = urllib.request.urlopen(base + "/focus", timeout=3).read()
                    focus = json.loads(snap)
                    print(f"# focus seed={focus.get('seed')} seq={focus.get('seq')}",
                          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
