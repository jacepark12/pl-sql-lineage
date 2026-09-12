"""MCP session wraps the same render_* functions as the query CLI."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import unittest

from plsqllineage.agent import render_query, render_stats
from plsqllineage.serve import LineageSession, build_server, main as serve_main

ROOT = pathlib.Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "engine_sample.json"


def _text(result) -> str:
    content = getattr(result, "content", None) or []
    if content:
        return content[0].text
    return str(result)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.session = LineageSession(FIXTURE)

    def test_query_matches_cli_projection(self):
        text = self.session.query_lineage("SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertIn("EDGE DIRECT SYNWMS.OUT_ORDER_D.ORD_QTY --> SYNWMS.OUT_ALLOC.ORD_QTY", text)
        self.assertNotIn("EDGE FILTER", text)
        from plsqllineage.agent import load_engine_path
        self.assertEqual(
            text, render_query(load_engine_path(FIXTURE), "SYNWMS.OUT_ALLOC.ORD_QTY"))

    def test_kind_filter(self):
        text = self.session.query_lineage("OUT_ALLOC.ORD_QTY", kind="FILTER")
        self.assertIn("EDGE FILTER", text)
        self.assertIn("WHERE d.WH_CD = v_wh", text)

    def test_explain(self):
        text = self.session.explain_column("IF_STOCK_SND.QTY")
        self.assertIn("1 hop", text)
        self.assertIn("VIA_VARIABLE", text)

    def test_shortest_path(self):
        text = self.session.shortest_path(
            "SYNWMS.OUT_ORDER_D.ORD_QTY", "SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertIn("Path (1 hop)", text)

    def test_shortest_path_none(self):
        text = self.session.shortest_path("OUT_ALLOC.ORD_QTY", "IF_STOCK_SND.QTY")
        self.assertIn("No path", text)

    def test_diagnose(self):
        text = self.session.diagnose()
        self.assertIn("DIAG UNRESOLVED", text)
        self.assertIn("PARSE_FAILED", text)

    def test_graph_stats(self):
        text = self.session.graph_stats()
        self.assertIn("Columns:", text)
        self.assertIn("Assertions:", text)
        self.assertIn("DIRECT:", text)
        self.assertIn("PARSE_FAILED:", text)

    def test_missing_default(self):
        session = LineageSession()
        text = session.query_lineage("OUT_ALLOC.ORD_QTY")
        self.assertIn("No engine JSON", text)

    def test_engine_path_override(self):
        session = LineageSession()
        text = session.query_lineage(
            "OUT_ALLOC.ORD_QTY", engine_path=str(FIXTURE))
        self.assertIn("EDGE DIRECT", text)

    def test_rejects_viewer_json(self):
        viewer = ROOT / "fixtures" / "viewer_sample.json"
        session = LineageSession(viewer)
        text = session.graph_stats()
        self.assertIn("edges", text)

    def test_missing_file(self):
        session = LineageSession("/no/such/engine.json")
        text = session.diagnose()
        self.assertIn("not found", text.lower())

    def test_reload_on_change(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            path = tmp / "engine.json"
            shutil.copy(FIXTURE, path)
            session = LineageSession(path)
            first = session.query_lineage("OUT_ALLOC.ORD_QTY")
            self.assertIn("EDGE DIRECT", first)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["edges"] = []
            data["diagnostics"] = []
            path.write_text(json.dumps(data), encoding="utf-8")
            second = session.query_lineage("OUT_ALLOC.ORD_QTY")
            self.assertIn("No column matching", second)
        finally:
            shutil.rmtree(tmp)


class ServeCliTests(unittest.TestCase):
    def test_missing_input_file(self):
        code = serve_main(["--input", "/no/such/engine.json"])
        self.assertEqual(code, 1)

    def test_query_publishes_without_http(self):
        session = LineageSession(FIXTURE)
        session.query_lineage("OUT_ALLOC.ORD_QTY")
        snap = session.hub.snapshot()
        self.assertIsNotNone(snap)
        self.assertEqual(snap.tool, "query_lineage")


class McpServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            self.app = build_server(FIXTURE)
        except ImportError:
            self.skipTest("mcp extra is not installed")

    async def test_lists_expected_tools(self):
        tools = await self.app.list_tools()
        names = {t.name for t in tools}
        self.assertEqual(
            names,
            {
                "query_lineage",
                "explain_column",
                "shortest_path",
                "diagnose",
                "graph_stats",
            },
        )
        query = next(t for t in tools if t.name == "query_lineage")
        schema = query.input_schema or query.inputSchema
        self.assertIn("column", schema["properties"])
        self.assertEqual(schema["required"], ["column"])
        self.assertIsNone(getattr(query, "output_schema", None))

    async def test_call_query_lineage(self):
        result = await self.app.call_tool(
            "query_lineage", {"column": "OUT_ALLOC.ORD_QTY"})
        self.assertFalse(getattr(result, "is_error", False))
        text = _text(result)
        self.assertIn("EDGE DIRECT", text)
        self.assertNotIn("{", text.splitlines()[0])

    async def test_call_shortest_path(self):
        result = await self.app.call_tool(
            "shortest_path",
            {
                "source": "OUT_ORDER_D.ORD_QTY",
                "target": "OUT_ALLOC.ORD_QTY",
            },
        )
        self.assertIn("Path (1 hop)", _text(result))

    async def test_call_diagnose_and_stats(self):
        diag = _text(await self.app.call_tool("diagnose", {}))
        stats = _text(await self.app.call_tool("graph_stats", {}))
        self.assertIn("PARSE_FAILED", diag)
        self.assertIn("Assertions:", stats)


class StatsRenderTests(unittest.TestCase):
    def test_counts(self):
        from plsqllineage.agent import load_engine_path
        text = render_stats(load_engine_path(FIXTURE))
        self.assertIn("FILTER:", text)
        self.assertIn("UNRESOLVED:", text)


if __name__ == "__main__":
    unittest.main()
