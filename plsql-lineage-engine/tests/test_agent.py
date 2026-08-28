"""Engine edges JSON → budgeted agent COL/EDGE/DIAG text."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import unittest

from plsqllineage.agent import (
    load_graph,
    parse_kinds,
    render_diagnose,
    render_explain,
    render_path,
    render_query,
    VALUE_KINDS,
)
from plsqllineage.query import main as query_main

ROOT = pathlib.Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "engine_sample.json"


def load_sample() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class KindParseTests(unittest.TestCase):
    def test_default_value(self):
        self.assertEqual(parse_kinds(None), set(VALUE_KINDS))
        self.assertEqual(parse_kinds("value"), set(VALUE_KINDS))

    def test_filter_alias(self):
        self.assertEqual(parse_kinds("FILTER"), {"FILTER"})
        self.assertEqual(parse_kinds("INDIRECT_FILTER"), {"FILTER"})

    def test_union(self):
        kinds = parse_kinds("value,FILTER")
        self.assertTrue(VALUE_KINDS <= kinds)
        self.assertIn("FILTER", kinds)


class QueryRenderTests(unittest.TestCase):
    def setUp(self):
        self.graph = load_graph(load_sample())

    def test_query_column_default_hides_filter(self):
        text = render_query(self.graph, "SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertIn("COL SYNWMS.OUT_ALLOC.ORD_QTY", text)
        self.assertIn("EDGE DIRECT SYNWMS.OUT_ORDER_D.ORD_QTY --> SYNWMS.OUT_ALLOC.ORD_QTY", text)
        self.assertIn("expr=d.ORD_QTY", text)
        self.assertIn("at=packages/SYNWMS.PKG_OUT_004.sql:42 PKG_OUT_004.SP_ALLOC_QTY", text)
        self.assertNotIn("INDIRECT_FILTER", text)
        self.assertNotIn("EDGE FILTER", text)
        self.assertNotIn("WH_CD", text)
        self.assertNotIn("OUT_ORDER_H.STATUS", text)
        self.assertIn("kind=value", text)
        self.assertIn("Upstream depth=2", text)

    def test_query_kind_filter_shows_where(self):
        text = render_query(
            self.graph, "SYNWMS.OUT_ALLOC.ORD_QTY",
            kinds=parse_kinds("FILTER"))
        self.assertIn("EDGE FILTER SYNWMS.OUT_ORDER_D.WH_CD --> SYNWMS.OUT_ALLOC.ORD_QTY", text)
        self.assertIn("WHERE d.WH_CD = v_wh", text)
        self.assertIn("EDGE FILTER SYNWMS.OUT_ORDER_H.STATUS --> SYNWMS.OUT_ALLOC.*", text)

    def test_partial_fqn(self):
        text = render_query(self.graph, "OUT_ALLOC.ORD_QTY")
        self.assertIn("COL SYNWMS.OUT_ALLOC.ORD_QTY", text)

    def test_ambiguous_bare_column(self):
        text = render_query(self.graph, "ORD_QTY")
        self.assertTrue(text.startswith("Ambiguous:"))
        self.assertIn("SYNWMS.OUT_ALLOC.ORD_QTY", text)
        self.assertIn("SYNWMS.OUT_ORDER_D.ORD_QTY", text)
        self.assertNotIn("EDGE DIRECT", text)

    def test_missing_suggests_candidates(self):
        text = render_query(self.graph, "authentication")
        self.assertIn("No column matching 'authentication'", text)
        self.assertNotIn("EDGE ", text)

    def test_unresolved_always_shown_on_seed(self):
        text = render_query(self.graph, "STK_TRX.TRX_QTY")
        self.assertIn("COL SYNWMS.STK_TRX.TRX_QTY", text)
        self.assertIn("EDGE UNRESOLVED (unresolved) --> SYNWMS.STK_TRX.TRX_QTY", text)
        self.assertIn("DIAG UNRESOLVED", text)
        self.assertIn("EXECUTE IMMEDIATE v_sql", text)

    def test_query_does_not_leak_other_file_diagnostics(self):
        text = render_query(self.graph, "STK_TRX.TRX_QTY")
        self.assertNotIn("PKG_BAD.sql", text)
        self.assertNotIn("PARSE_FAILED", text)

    def test_sibling_procedure_diagnostic_is_included(self):
        text = render_query(self.graph, "OUT_ALLOC.ORD_QTY")
        self.assertIn("DIAG SQL_NOT_ANALYZED", text)
        self.assertIn("PKG_OUT_004.sql:55", text)

    def test_truncation_keeps_seed_and_banners_top(self):
        text = render_query(
            self.graph, "SYNIF.IF_STOCK_SND.QTY",
            depth=2, token_budget=20)
        self.assertTrue(
            text.startswith("[!] TRUNCATED") or text.startswith("[i] Complete"),
            text.splitlines()[0])
        self.assertIn("COL SYNIF.IF_STOCK_SND.QTY", text)

    def test_explain_one_hop(self):
        text = render_explain(self.graph, "IF_STOCK_SND.QTY")
        self.assertIn("1 hop", text)
        self.assertIn("VIA_VARIABLE", text)
        self.assertIn("AGGREGATE", text)
        self.assertIn("SUM(s.ONHAND_QTY - s.ALLOC_QTY)", text)

    def test_path(self):
        text = render_path(
            self.graph,
            "SYNWMS.OUT_ORDER_D.ORD_QTY",
            "SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertIn("Path (1 hop)", text)
        self.assertIn("EDGE DIRECT SYNWMS.OUT_ORDER_D.ORD_QTY --> SYNWMS.OUT_ALLOC.ORD_QTY", text)

    def test_path_same_node(self):
        text = render_path(self.graph, "OUT_ALLOC.ORD_QTY", "SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertIn("both resolved", text)

    def test_path_missing(self):
        text = render_path(self.graph, "OUT_ALLOC.ORD_QTY", "IF_STOCK_SND.QTY")
        self.assertIn("No path", text)

    def test_diagnose_lists_unresolved_first(self):
        text = render_diagnose(self.graph)
        unresolved_at = text.find("DIAG UNRESOLVED")
        parse_at = text.find("DIAG PARSE_FAILED")
        self.assertNotEqual(unresolved_at, -1)
        self.assertNotEqual(parse_at, -1)
        self.assertLess(unresolved_at, parse_at)
        self.assertIn("PKG_BAD.sql", text)


class QueryCliTests(unittest.TestCase):
    def test_cli_query(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = query_main(["--input", str(FIXTURE), "OUT_ALLOC.ORD_QTY"])
        self.assertEqual(code, 0)
        self.assertIn("EDGE DIRECT", buf.getvalue())

    def test_cli_missing_graph(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = query_main(["--input", "/no/such/engine.json", "X"])
        self.assertEqual(code, 1)
        self.assertIn("입력을 찾을 수 없습니다", err.getvalue())

    def test_cli_explain_and_path(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(
                query_main(["--input", str(FIXTURE), "explain", "IF_STOCK_SND.QTY"]),
                0)
            self.assertEqual(
                query_main([
                    "--input", str(FIXTURE), "path",
                    "OUT_ORDER_D.ORD_QTY", "OUT_ALLOC.ORD_QTY",
                ]),
                0)
            self.assertEqual(
                query_main(["--input", str(FIXTURE), "diagnose"]),
                0)
        self.assertIn("Path (1 hop)", buf.getvalue())
        self.assertIn("Diagnostics:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
