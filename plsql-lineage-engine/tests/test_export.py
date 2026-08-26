"""Engine edges JSON → viewer objects/relationships contract."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from plsqllineage.export import (
    DIRECT_KINDS,
    main,
    object_id,
    relationship_type,
    to_viewer,
)

ROOT = pathlib.Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "engine_sample.json"
GOLDEN = ROOT / "fixtures" / "viewer_sample.json"

REQUIRED_OBJECT = {"id", "type", "name"}
REQUIRED_REL = {"type", "source", "target", "expression"}
REQUIRED_DIAG = {"severity", "code", "message", "spanText"}
VIEWER_REL_TYPES = {"direct", "indirect", "call", "dynamic_sql"}
VIEWER_OBJ_TYPES = {
    "table", "view", "column", "package", "procedure", "function",
    "parameter", "trigger", "dynamic_statement",
}

KIND_CASES = (
    ("DIRECT", "direct"),
    ("TRANSFORM", "direct"),
    ("AGGREGATE", "direct"),
    ("ANALYTIC", "direct"),
    ("VIA_VARIABLE", "direct"),
    ("VIA_CTE", "direct"),
    ("VIA_PIPELINE", "direct"),
    ("INDIRECT_FILTER", "indirect"),
    ("CONSTANT", "indirect"),
    ("SEVERED", "indirect"),
    ("UNRESOLVED", "dynamic_sql"),
    ("DYNAMIC_SQL", "dynamic_sql"),
    ("CALL", "call"),
    ("direct", "direct"),
    ("indirect", "indirect"),
)


def load_engine() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class KindMappingTests(unittest.TestCase):
    def test_kind_table(self):
        for kind, expected in KIND_CASES:
            with self.subTest(kind=kind):
                self.assertEqual(relationship_type(kind), expected)

    def test_unknown_indirect_prefix(self):
        self.assertEqual(relationship_type("INDIRECT_JOIN"), "indirect")

    def test_value_kinds_are_direct(self):
        for kind in DIRECT_KINDS:
            self.assertEqual(relationship_type(kind), "direct", kind)


class FixtureExportTests(unittest.TestCase):
    def setUp(self):
        self.viewer = to_viewer(load_engine())

    def test_top_level_arrays(self):
        for key in ("objects", "relationships", "diagnostics"):
            self.assertIsInstance(self.viewer[key], list, key)
        self.assertGreaterEqual(len(self.viewer["objects"]), 1)
        self.assertGreaterEqual(len(self.viewer["relationships"]), 1)

    def test_required_fields(self):
        for item in self.viewer["objects"]:
            self.assertTrue(REQUIRED_OBJECT <= item.keys(), item)
            self.assertIn(item["type"], VIEWER_OBJ_TYPES, item)
            self.assertTrue(item["id"], item)
            self.assertTrue(item["name"], item)
        for item in self.viewer["relationships"]:
            self.assertTrue(REQUIRED_REL <= item.keys(), item)
            self.assertIn(item["type"], VIEWER_REL_TYPES, item)
        for item in self.viewer["diagnostics"]:
            self.assertTrue(REQUIRED_DIAG <= item.keys(), item)

    def test_ids_are_stable(self):
        again = to_viewer(load_engine())
        self.assertEqual(self.viewer, again)
        ids = [item["id"] for item in self.viewer["objects"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_column_ids_match_viewer_prefix(self):
        columns = [o for o in self.viewer["objects"] if o["type"] == "column"]
        self.assertTrue(columns)
        for col in columns:
            self.assertTrue(col["id"].startswith("column."), col)
            table = next(
                o for o in self.viewer["objects"]
                if o["type"] == "table" and col["name"].startswith(o["name"] + "."))
            self.assertEqual(
                col["id"],
                object_id("column", table["name"], col["name"][len(table["name"]) + 1:]),
            )

    def test_direct_and_indirect_and_dynamic(self):
        types = {r["type"] for r in self.viewer["relationships"]}
        self.assertIn("direct", types)
        self.assertIn("indirect", types)
        self.assertIn("dynamic_sql", types)

    def test_transform_is_direct(self):
        rel = next(r for r in self.viewer["relationships"]
                   if r["expression"] == "NVL(d.WH_CD, '-')")
        self.assertEqual(rel["type"], "direct")
        self.assertEqual(rel["source"], "column.synwms.out_order_d.wh_cd")
        self.assertEqual(rel["target"], "column.synwms.out_alloc.wh_cd")

    def test_filter_to_table_uses_table_id(self):
        rel = next(r for r in self.viewer["relationships"]
                   if r["expression"] == "WHERE h.STATUS = 'OPEN'")
        self.assertEqual(rel["type"], "indirect")
        self.assertEqual(rel["source"], "column.synwms.out_order_h.status")
        self.assertEqual(rel["target"], "table.synwms.out_alloc")

    def test_multi_source_edge_explodes(self):
        expr = "SUM(s.ONHAND_QTY - s.ALLOC_QTY)"
        rels = [r for r in self.viewer["relationships"] if r["expression"] == expr]
        self.assertEqual(len(rels), 2)
        sources = {r["source"] for r in rels}
        self.assertEqual(sources, {
            "column.synwms.stk_onhand.onhand_qty",
            "column.synwms.stk_onhand.alloc_qty",
        })

    def test_packages_and_procedures_from_location(self):
        by_id = {o["id"]: o for o in self.viewer["objects"]}
        self.assertEqual(by_id["package.pkg_out_004"]["type"], "package")
        self.assertEqual(by_id["package.pkg_out_004"]["name"], "PKG_OUT_004")
        proc = by_id["procedure.pkg_out_004.sp_alloc_qty"]
        self.assertEqual(proc["type"], "procedure")
        self.assertEqual(proc["name"], "PKG_OUT_004.SP_ALLOC_QTY")
        self.assertTrue(proc["name"].startswith(
            by_id["package.pkg_out_004"]["name"] + "."))

    def test_unresolved_gets_dynamic_statement(self):
        rel = next(r for r in self.viewer["relationships"]
                   if r["type"] == "dynamic_sql")
        src = next(o for o in self.viewer["objects"] if o["id"] == rel["source"])
        self.assertEqual(src["type"], "dynamic_statement")
        self.assertEqual(rel["target"], "column.synwms.stk_trx.trx_qty")
        self.assertEqual(src["id"],
                         "dynamic_statement.pkg_stk_006.sp_dynamic_trx.120")

    def test_diagnostics_span_text(self):
        by_code = {d["code"]: d for d in self.viewer["diagnostics"]}
        self.assertEqual(
            by_code["SQL_NOT_ANALYZED"]["spanText"],
            "packages/SYNWMS.PKG_OUT_004.sql:55 PKG_OUT_004.SP_ALLOC_QTY")
        self.assertEqual(by_code["PARSE_FAILED"]["severity"], "error")
        self.assertEqual(
            by_code["PARSE_FAILED"]["spanText"],
            "packages/SYNWMS.PKG_BAD.sql:1")

    def test_golden_fixture(self):
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(self.viewer, expected)

    def test_passthrough_viewer_json(self):
        again = to_viewer(self.viewer)
        self.assertEqual(again["objects"], self.viewer["objects"])
        self.assertEqual(again["relationships"], self.viewer["relationships"])
        self.assertEqual(again["diagnostics"], self.viewer["diagnostics"])

    def test_hierarchy_grouping_names(self):
        tables = [o for o in self.viewer["objects"] if o["type"] == "table"]
        columns = [o for o in self.viewer["objects"] if o["type"] == "column"]
        for col in columns:
            owners = [t for t in tables if col["name"].startswith(t["name"] + ".")]
            self.assertTrue(owners, col)


class CliTests(unittest.TestCase):
    def test_export_cli_writes_viewer_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "viewer.json"
            rc = main(["--input", str(FIXTURE), "--out", str(out)])
            self.assertEqual(rc, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload, to_viewer(load_engine()))

    def test_missing_input(self):
        from io import StringIO
        from unittest.mock import patch
        with patch("sys.stderr", StringIO()):
            rc = main(["--input", "/tmp/does-not-exist-engine.json"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
