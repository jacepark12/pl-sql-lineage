"""MCP stdio and --ui HTTP share one process; a tool call updates /focus."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

from plsqllineage.focus import digest_file

ROOT = pathlib.Path(__file__).resolve().parent
ENGINE_ROOT = ROOT.parent
FIXTURE = ROOT / "fixtures" / "engine_sample.json"
SERVE_WRAPPER = ENGINE_ROOT.parent / ".cursor" / "lineage-serve.sh"
MCP_JSON = ENGINE_ROOT.parent / ".cursor" / "mcp.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait(url: str, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 — poll until up
            last = exc
        time.sleep(0.05)
    raise TimeoutError(f"{url} did not come up: {last}")


class ProjectMcpConfigTests(unittest.TestCase):
    def test_mcp_json_points_at_wrapper(self):
        payload = json.loads(MCP_JSON.read_text(encoding="utf-8"))
        server = payload["mcpServers"]["plsql-lineage"]
        self.assertEqual(server["command"], "bash")
        self.assertEqual(server["args"], [".cursor/lineage-serve.sh"])
        self.assertTrue(SERVE_WRAPPER.is_file())
        self.assertTrue(os.access(SERVE_WRAPPER, os.X_OK))

    def test_wrapper_ui_only_serves_engine(self):
        port = _free_port()
        env = os.environ.copy()
        env["PLSQL_LINEAGE_ENGINE"] = str(FIXTURE)
        env["PLSQL_LINEAGE_UI"] = f"127.0.0.1:{port}"
        env["PLSQL_LINEAGE_PYTHON"] = sys.executable
        proc = subprocess.Popen(
            ["bash", str(SERVE_WRAPPER), "--ui-only"],
            cwd=str(ENGINE_ROOT.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            _wait(f"http://127.0.0.1:{port}/health")
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/engine.json", timeout=3) as resp:
                body = resp.read()
            self.assertEqual(body, FIXTURE.read_bytes())
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)


class McpStdioUiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            self.skipTest("mcp extra is not installed")
        self.ClientSession = ClientSession
        self.StdioServerParameters = StdioServerParameters
        self.stdio_client = stdio_client

    async def test_stdio_query_updates_http_focus(self):
        port = _free_port()
        params = self.StdioServerParameters(
            command=sys.executable,
            args=["-m", "plsqllineage.serve",
                  "--input", str(FIXTURE),
                  "--ui", f"127.0.0.1:{port}"],
            env={
                "PYTHONPATH": str(ENGINE_ROOT),
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
            },
            cwd=str(ENGINE_ROOT),
        )
        async with self.stdio_client(params) as (read, write):
            async with self.ClientSession(read, write) as session:
                await session.initialize()
                await asyncio.to_thread(
                    _wait, f"http://127.0.0.1:{port}/health")
                result = await session.call_tool(
                    "query_lineage", {"column": "OUT_ALLOC.ORD_QTY"})
                self.assertFalse(getattr(result, "is_error", False))
                text = result.content[0].text
                self.assertIn("EDGE DIRECT", text)
                self.assertNotIn("{", text.splitlines()[0])

                def _focus() -> dict:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/focus", timeout=3) as resp:
                        return json.loads(resp.read())

                focus = await asyncio.to_thread(_focus)
                self.assertEqual(focus["tool"], "query_lineage")
                self.assertEqual(focus["seed"], "SYNWMS.OUT_ALLOC.ORD_QTY")
                self.assertEqual(focus["graph"], digest_file(FIXTURE))
                self.assertTrue(any(
                    edge["source"].endswith("OUT_ORDER_D.ORD_QTY")
                    for edge in focus["edges"]))


if __name__ == "__main__":
    unittest.main()
