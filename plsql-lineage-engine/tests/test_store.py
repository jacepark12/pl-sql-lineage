"""Sqlite stub: load engine-shaped edges and query a column's sources."""

from __future__ import annotations

import unittest

from plsqllineage.store import connect, load_edges, sources_for, split_table


ENGINE_EDGES = {
    "edges": [
        {
            "target": {"table": "SYNWMS.OUT_ALLOC", "column": "ORD_QTY"},
            "sources": [{"table": "SYNWMS.OUT_ORDER_D", "column": "ORD_QTY"}],
            "kind": "DIRECT",
            "transform": "d.ORD_QTY",
            "location": {
                "file": "packages/SYNWMS.PKG_OUT_004.sql",
                "package": "PKG_OUT_004",
                "procedure": "SP_ALLOC_QTY",
                "line": 42,
            },
        },
        {
            "target": {"table": "SYNWMS.OUT_ALLOC", "column": "ORD_QTY"},
            "sources": [
                {"table": "SYNWMS.STK_ONHAND", "column": "ONHAND_QTY"},
                {"table": "SYNWMS.STK_ONHAND", "column": "ALLOC_QTY"},
            ],
            "kind": "AGGREGATE",
            "transform": "SUM(s.ONHAND_QTY - s.ALLOC_QTY)",
            "location": {
                "file": "packages/SYNWMS.PKG_OUT_004.sql",
                "line": 50,
            },
        },
        {
            "target": {"table": "TGT", "column": "A"},
            "sources": [
                {"table": "SYN.T", "column": "X", "dblink": "REMOTE"},
            ],
            "kind": "DIRECT",
            "transform": "s.X",
        },
        {
            "target": {"table": "TGT", "column": "B"},
            "sources": [{"table": "SYN.T", "column": "X"}],
            "kind": "DIRECT",
            "transform": "s.X",
        },
        {
            "target": {"table": "SYNWMS.OUT_ALLOC", "column": None},
            "sources": [{"table": "SYNWMS.OUT_ORDER_H", "column": "STATUS"}],
            "kind": "INDIRECT_FILTER",
            "transform": "WHERE h.STATUS = 'OPEN'",
        },
    ],
}


class StoreSmokeTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        self.inserted = load_edges(self.conn, ENGINE_EDGES, source_rev="test")

    def tearDown(self):
        self.conn.close()

    def test_query_column_sources(self):
        sources = sources_for(self.conn, "SYNWMS", "OUT_ALLOC", "ORD_QTY")
        self.assertEqual(sources, [
            "SYNWMS.OUT_ORDER_D.ORD_QTY",
            "SYNWMS.STK_ONHAND.ALLOC_QTY",
            "SYNWMS.STK_ONHAND.ONHAND_QTY",
        ])

    def test_reload_is_idempotent(self):
        again = load_edges(self.conn, ENGINE_EDGES, source_rev="test")
        self.assertEqual(again, 0)
        self.assertEqual(
            sources_for(self.conn, "SYNWMS", "OUT_ALLOC", "ORD_QTY"),
            [
                "SYNWMS.OUT_ORDER_D.ORD_QTY",
                "SYNWMS.STK_ONHAND.ALLOC_QTY",
                "SYNWMS.STK_ONHAND.ONHAND_QTY",
            ],
        )

    def test_filter_kind_is_stored_as_filter(self):
        rows = self.conn.execute(
            "SELECT kind, to_fqn, from_fqn FROM column_lineage_edge "
            "WHERE kind = 'FILTER'"
        ).fetchall()
        self.assertTrue(rows)
        self.assertEqual(rows[0]["to_fqn"], "SYNWMS.OUT_ALLOC.*")
        self.assertEqual(rows[0]["from_fqn"], "SYNWMS.OUT_ORDER_H.STATUS")

    def test_dblink_is_not_collapsed_into_local_table(self):
        remote = sources_for(self.conn, "", "TGT", "A")
        local = sources_for(self.conn, "", "TGT", "B")
        self.assertEqual(remote, ["SYN.T@REMOTE.X"])
        self.assertEqual(local, ["SYN.T.X"])
        self.assertNotEqual(remote, local)

    def test_split_table_keeps_link_on_table(self):
        self.assertEqual(
            split_table({"table": "SYN.T", "dblink": "REMOTE"}),
            ("SYN", "T@REMOTE"),
        )
        self.assertEqual(split_table({"table": "SYN.T"}), ("SYN", "T"))


if __name__ == "__main__":
    unittest.main()
