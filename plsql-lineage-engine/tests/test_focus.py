"""Focus events parsed from the same COL/EDGE text the agent sees."""

from __future__ import annotations

import pathlib
import unittest

from plsqllineage.agent import load_engine_path, render_path, render_query
from plsqllineage.focus import (
    cap_focus,
    digest_file,
    focus_event_from_text,
    parse_projection,
    projection_is_focusable,
)
from plsqllineage.serve import LineageSession

ROOT = pathlib.Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "engine_sample.json"


class ProjectionParseTests(unittest.TestCase):
    def test_query_columns_and_direct_edge(self):
        graph = load_engine_path(FIXTURE)
        text = render_query(graph, "SYNWMS.OUT_ALLOC.ORD_QTY")
        seed, columns, edges, truncated = parse_projection(text)
        self.assertFalse(truncated)
        self.assertEqual(seed, "SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertIn("SYNWMS.OUT_ALLOC.ORD_QTY", columns)
        self.assertIn("SYNWMS.OUT_ORDER_D.ORD_QTY", columns)
        self.assertEqual(
            edges,
            [{
                "kind": "DIRECT",
                "source": "SYNWMS.OUT_ORDER_D.ORD_QTY",
                "target": "SYNWMS.OUT_ALLOC.ORD_QTY",
            }],
        )

    def test_multi_source_edge(self):
        text = (
            "Column: SYNIF.IF_STOCK_SND.QTY\n\n"
            "COL SYNIF.IF_STOCK_SND.QTY\n"
            "EDGE AGGREGATE SYNWMS.STK_ONHAND.ONHAND_QTY, "
            "SYNWMS.STK_ONHAND.ALLOC_QTY --> SYNIF.IF_STOCK_SND.QTY\n"
        )
        seed, columns, edges, _ = parse_projection(text)
        self.assertEqual(seed, "SYNIF.IF_STOCK_SND.QTY")
        self.assertEqual(len(edges), 2)
        self.assertEqual(
            {edge["source"] for edge in edges},
            {"SYNWMS.STK_ONHAND.ONHAND_QTY", "SYNWMS.STK_ONHAND.ALLOC_QTY"},
        )
        self.assertIn("SYNWMS.STK_ONHAND.ALLOC_QTY", columns)

    def test_path_without_col_lines(self):
        graph = load_engine_path(FIXTURE)
        text = render_path(
            graph, "SYNWMS.OUT_ORDER_D.ORD_QTY", "SYNWMS.OUT_ALLOC.ORD_QTY")
        seed, columns, edges, _ = parse_projection(text)
        self.assertEqual(seed, "SYNWMS.OUT_ORDER_D.ORD_QTY")
        self.assertIn("SYNWMS.OUT_ALLOC.ORD_QTY", columns)
        self.assertEqual(edges[0]["kind"], "DIRECT")

    def test_unresolved_source_skipped(self):
        text = (
            "COL SYNWMS.STK_TRX.TRX_QTY\n"
            "EDGE UNRESOLVED (unresolved) --> SYNWMS.STK_TRX.TRX_QTY\n"
        )
        _, columns, edges, _ = parse_projection(text)
        self.assertEqual(columns, ["SYNWMS.STK_TRX.TRX_QTY"])
        self.assertEqual(edges, [])

    def test_errors_are_not_focusable(self):
        self.assertFalse(projection_is_focusable("No column matching 'X'."))
        self.assertFalse(projection_is_focusable("Ambiguous: 'QTY' matches 2 columns."))
        self.assertFalse(projection_is_focusable("No engine JSON. Pass engine_path"))
        self.assertTrue(projection_is_focusable("Column: T.C\n\nCOL T.C\n"))

    def test_cap_keeps_seed_neighbors(self):
        seed = "T.SEED"
        columns = [seed] + [f"T.C{i}" for i in range(200)]
        edges = (
            [{"kind": "DIRECT", "source": "T.C0", "target": seed}]
            + [{"kind": "DIRECT", "source": f"T.C{i}", "target": f"T.C{i+1}"}
               for i in range(1, 180)]
        )
        kept_cols, kept_edges, omitted_c, omitted_e = cap_focus(
            seed, columns, edges, max_columns=8, max_edges=3)
        self.assertIn(seed, kept_cols)
        self.assertIn("T.C0", kept_cols)
        self.assertLessEqual(len(kept_cols), 8)
        self.assertLessEqual(len(kept_edges), 3)
        self.assertEqual(kept_edges[0]["target"], seed)
        self.assertGreater(omitted_c, 0)
        self.assertGreater(omitted_e, 0)


class SessionPublishTests(unittest.TestCase):
    def setUp(self):
        self.session = LineageSession(FIXTURE)

    def test_query_publishes_focus(self):
        text = self.session.query_lineage("OUT_ALLOC.ORD_QTY")
        self.assertIn("EDGE DIRECT", text)
        snap = self.session.hub.snapshot()
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.tool, "query_lineage")
        self.assertEqual(snap.seed, "SYNWMS.OUT_ALLOC.ORD_QTY")
        self.assertEqual(snap.graph, digest_file(FIXTURE))
        self.assertTrue(
            any(edge["source"].endswith("OUT_ORDER_D.ORD_QTY") for edge in snap.edges))

    def test_error_does_not_clear_focus(self):
        self.session.query_lineage("OUT_ALLOC.ORD_QTY")
        first = self.session.hub.snapshot()
        miss = self.session.query_lineage("NO_SUCH_COLUMN")
        self.assertIn("No column matching", miss)
        self.assertIs(self.session.hub.snapshot(), first)

    def test_diagnose_publishes_empty_columns(self):
        self.session.diagnose()
        snap = self.session.hub.snapshot()
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.tool, "diagnose")
        self.assertEqual(snap.columns, [])
        self.assertTrue(snap.note)

    def test_event_json_roundtrip_fields(self):
        event = focus_event_from_text(
            "Column: T.C\n\nCOL T.C\nEDGE DIRECT T.A --> T.C\n",
            tool="query_lineage",
            graph="sha256:abc",
        )
        assert event is not None
        payload = event.to_json()
        self.assertEqual(payload["v"], 1)
        self.assertEqual(payload["columns"], ["T.C", "T.A"])
        self.assertEqual(payload["edges"][0]["kind"], "DIRECT")


if __name__ == "__main__":
    unittest.main()
