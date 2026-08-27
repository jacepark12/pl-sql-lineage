"""Layer B: MERGE, CTE passthrough, SELECT * expansion, and regressions."""

from __future__ import annotations

import unittest

from plsqllineage.catalog import load_catalog
from plsqllineage.sqlmap import (
    DIRECT,
    FILTER,
    TRANSFORM,
    VIA_CTE,
    analyze,
)

STK_ONHAND = [
    "WH_CD", "LOC_CD", "ITEM_CD", "LOT_NO",
    "ONHAND_QTY", "ALLOC_QTY", "AVAIL_QTY", "WGT_TOT", "LAST_TRX_YMD", "UPD_DTM",
]
STK_TRX = [
    "TRX_SEQ", "WH_CD", "LOC_CD", "ITEM_CD", "LOT_NO",
    "TRX_TP_CD", "TRX_QTY", "BEF_QTY", "AFT_QTY", "TRX_WGT", "TRX_YMD", "REF_NO",
]
CATALOG = {
    "SYNWMS.STK_ONHAND": STK_ONHAND,
    "SYNARC.ARC_STK_ONHAND": list(STK_ONHAND),
    "SYNWMS.STK_TRX": STK_TRX,
}


def pairs(result, kind=None):
    out = []
    for edge in result.edges:
        if kind is not None and edge.kind != kind:
            continue
        tgt = f"{edge.target.table}.{edge.target.column}"
        for source in edge.sources:
            out.append((f"{source.table}.{source.column}", tgt, edge.kind))
    return out


class InsertUpdateRegression(unittest.TestCase):
    def test_insert_select_direct(self):
        result = analyze(
            "INSERT INTO SYNWMS.OUT_ALLOC (WH_CD, ORD_QTY) "
            "SELECT d.WH_CD, d.ORD_QTY FROM SYNWMS.OUT_ORDER_D d")
        self.assertIsNone(result.error)
        self.assertIn(
            ("SYNWMS.OUT_ORDER_D.WH_CD", "SYNWMS.OUT_ALLOC.WH_CD", DIRECT),
            pairs(result))

    def test_insert_values_unresolved_variable(self):
        result = analyze(
            "INSERT INTO SYNIF.IF_ORD (WH_CD) VALUES (V_WH)",
            frozenset({"V_WH"}))
        self.assertEqual(len(result.edges), 1)
        self.assertEqual(result.edges[0].unresolved, ["V_WH"])

    def test_update_transform(self):
        result = analyze(
            "UPDATE SYNWMS.MST_ITEM t SET t.ITEM_NM = NVL(TRIM(t.ITEM_NM), '-')")
        kinds = {edge.kind for edge in result.edges if edge.target.column == "ITEM_NM"}
        self.assertIn(TRANSFORM, kinds)


class MergeTests(unittest.TestCase):
    def test_matched_and_not_matched_read_using_base_table(self):
        result = analyze("""
            MERGE INTO SYNIF.IF_STOCK_SND t
            USING (
              SELECT s.WH_CD AS WH_CD, NVL(s.ONHAND_QTY, 0) AS QTY
                FROM SYNWMS.STK_ONHAND s
               WHERE s.ONHAND_QTY > 0
            ) q
            ON (t.WH_CD = q.WH_CD)
            WHEN MATCHED THEN UPDATE SET t.QTY = q.QTY
            WHEN NOT MATCHED THEN INSERT (WH_CD, QTY) VALUES (q.WH_CD, q.QTY)
        """)
        self.assertIsNone(result.error, result.error)
        got = pairs(result)
        self.assertIn(("SYNWMS.STK_ONHAND.ONHAND_QTY", "SYNIF.IF_STOCK_SND.QTY", DIRECT), got)
        self.assertIn(("SYNWMS.STK_ONHAND.WH_CD", "SYNIF.IF_STOCK_SND.WH_CD", DIRECT), got)
        fake = [p for p in got if p[0].upper().startswith("Q.")]
        self.assertEqual(fake, [])
        on_filters = [e for e in result.edges if e.kind == FILTER and "MERGE ON" in e.transform]
        self.assertTrue(on_filters)
        on_src = {(s.table, s.column) for e in on_filters for s in e.sources}
        self.assertIn(("SYNWMS.STK_ONHAND", "WH_CD"), on_src)

    def test_using_constant_is_not_invented_as_alias_table(self):
        result = analyze("""
            MERGE INTO SYNIF.IF_STOCK_SND t
            USING (
              SELECT s.WH_CD AS WH_CD, SYSDATE AS SND_DTM
                FROM SYNWMS.STK_ONHAND s
            ) q
            ON (t.WH_CD = q.WH_CD)
            WHEN MATCHED THEN UPDATE SET t.SND_DTM = q.SND_DTM
            WHEN NOT MATCHED THEN INSERT (WH_CD, SND_DTM) VALUES (q.WH_CD, q.SND_DTM)
        """)
        got = pairs(result)
        self.assertFalse(any(p[0].startswith("Q.") or p[0].startswith("q.") for p in got))
        self.assertIn(("SYNWMS.STK_ONHAND.WH_CD", "SYNIF.IF_STOCK_SND.WH_CD", DIRECT), got)

    def test_unhandled_merge_is_gone(self):
        result = analyze(
            "MERGE INTO t USING s ON (t.k = s.k) "
            "WHEN MATCHED THEN UPDATE SET t.a = s.a")
        self.assertIsNone(result.error)


class CteTests(unittest.TestCase):
    def test_cte_passthrough_is_via_cte(self):
        result = analyze("""
            INSERT INTO TGT (A)
            WITH c AS (SELECT s.X FROM SYN.S s)
            SELECT c.X FROM c
        """)
        self.assertIsNone(result.error, result.error)
        got = pairs(result)
        self.assertIn(("SYN.S.X", "TGT.A", VIA_CTE), got)
        self.assertFalse(any(p[0] in ("c.X", "C.X") for p in got))

    def test_cte_keeps_aggregate_kind_when_outer_is_not_direct(self):
        result = analyze("""
            INSERT INTO TGT (QTY)
            WITH w AS (
              SELECT SUM(s.ONHAND_QTY) AS QTY FROM SYNWMS.STK_ONHAND s
            )
            SELECT NVL(w.QTY, 0) FROM w
        """)
        qty = [e for e in result.edges if e.target.column == "QTY" and e.kind != FILTER]
        self.assertTrue(qty)
        self.assertEqual(qty[0].kind, TRANSFORM)
        self.assertEqual(qty[0].sources[0].table, "SYNWMS.STK_ONHAND")

    def test_inline_view_passthrough(self):
        result = analyze("""
            INSERT INTO TGT (A)
            SELECT v.A FROM (SELECT s.X AS A FROM SYN.S s) v
        """)
        self.assertIn(("SYN.S.X", "TGT.A", VIA_CTE), pairs(result))

    def test_recursive_cte_is_diagnosed(self):
        result = analyze("""
            INSERT INTO TGT (N)
            WITH rec (N) AS (
              SELECT 1 FROM dual
              UNION ALL
              SELECT rec.N + 1 FROM rec WHERE rec.N < 3
            )
            SELECT rec.N FROM rec
        """)
        codes = [c for c, _ in result.diagnostics]
        self.assertIn("UNSUPPORTED_CTE", codes)


class StarTests(unittest.TestCase):
    def test_select_star_expands_with_catalog(self):
        result = analyze(
            "INSERT INTO SYNARC.ARC_STK_ONHAND "
            "SELECT s.* FROM SYNWMS.STK_ONHAND s WHERE s.ONHAND_QTY > 0",
            catalog=CATALOG)
        self.assertIsNone(result.error, result.error)
        got = pairs(result, DIRECT)
        self.assertIn(
            ("SYNWMS.STK_ONHAND.ONHAND_QTY", "SYNARC.ARC_STK_ONHAND.ONHAND_QTY", DIRECT),
            got)
        self.assertIn(
            ("SYNWMS.STK_ONHAND.WH_CD", "SYNARC.ARC_STK_ONHAND.WH_CD", DIRECT),
            got)
        self.assertGreaterEqual(len([p for p in got if p[2] == DIRECT]), len(STK_ONHAND))

    def test_star_without_catalog_is_diagnosed(self):
        result = analyze(
            "INSERT INTO SYNARC.ARC_STK_ONHAND "
            "SELECT s.* FROM SYNWMS.STK_ONHAND s")
        self.assertTrue(any(c == "STAR_UNRESOLVED" for c, _ in result.diagnostics))
        self.assertFalse(any(e.target.column for e in result.edges if e.kind == DIRECT))

    def test_alias_star_in_inline_view(self):
        result = analyze("""
            INSERT INTO SYNARC.ARC_STK_TRX
              (ARC_SEQ, TRX_SEQ, WH_CD, ITEM_CD, TRX_TP_CD, TRX_QTY, TRX_YMD, ARC_DTM)
            SELECT SEQ_ARC.NEXTVAL, v.TRX_SEQ, v.WH_CD, v.ITEM_CD,
                   v.TRX_TP_CD, v.TRX_QTY, v.TRX_YMD, SYSDATE
              FROM (SELECT x.* FROM SYNWMS.STK_TRX x) v
        """, catalog=CATALOG)
        got = pairs(result)
        self.assertIn(("SYNWMS.STK_TRX.TRX_SEQ", "SYNARC.ARC_STK_TRX.TRX_SEQ", VIA_CTE), got)
        self.assertIn(("SYNWMS.STK_TRX.WH_CD", "SYNARC.ARC_STK_TRX.WH_CD", VIA_CTE), got)


class CatalogParseTests(unittest.TestCase):
    def test_load_catalog_skips_number_scale_commas(self):
        sql = """
        CREATE TABLE SYNWMS.STK_ONHAND (
          WH_CD       VARCHAR2(10) NOT NULL,
          ONHAND_QTY  NUMBER(13,3),
          CONSTRAINT PK_STK_ONHAND PRIMARY KEY (WH_CD)
        );
        """
        catalog = load_catalog(sql)
        self.assertEqual(catalog["SYNWMS.STK_ONHAND"], ["WH_CD", "ONHAND_QTY"])


class DbLinkTests(unittest.TestCase):
    def test_select_from_remote_is_not_local_table(self):
        remote = analyze(
            "INSERT INTO TGT (A) SELECT s.X FROM SYN.T@REMOTE s")
        local = analyze(
            "INSERT INTO TGT (A) SELECT s.X FROM SYN.T s")
        self.assertIsNone(remote.error, remote.error)
        self.assertIsNone(local.error, local.error)
        remote_src = {(s.table, s.column, s.dblink)
                      for e in remote.edges for s in e.sources}
        local_src = {(s.table, s.column, s.dblink)
                     for e in local.edges for s in e.sources}
        self.assertIn(("SYN.T@REMOTE", "X", "REMOTE"), remote_src)
        self.assertIn(("SYN.T", "X", None), local_src)
        self.assertNotIn(("SYN.T", "X", None), remote_src)
        self.assertNotIn(("SYN.T@REMOTE", "X", "REMOTE"), local_src)

    def test_insert_into_remote_target(self):
        result = analyze(
            "INSERT INTO SYN.T@REMOTE (A) SELECT s.X FROM LOCAL.T s")
        self.assertIsNone(result.error, result.error)
        targets = {(e.target.table, e.target.column, e.target.dblink)
                   for e in result.edges if e.target.column}
        self.assertIn(("SYN.T@REMOTE", "A", "REMOTE"), targets)
        self.assertFalse(any(t[0] == "SYN.T" and t[2] is None for t in targets))

    def test_merge_using_remote_table(self):
        result = analyze("""
            MERGE INTO TGT t
            USING SYN.T@REMOTE s
            ON (t.K = s.K)
            WHEN MATCHED THEN UPDATE SET t.A = s.A
        """)
        self.assertIsNone(result.error, result.error)
        got = pairs(result)
        self.assertIn(("SYN.T@REMOTE.A", "TGT.A", DIRECT), got)
        self.assertFalse(any(p[0] == "SYN.T.A" for p in got))


class ConnectByTests(unittest.TestCase):
    def test_prior_and_connect_columns_are_indirect_filter(self):
        result = analyze("""
            INSERT INTO TGT (ID, PARENT)
            SELECT e.ID, e.PARENT_ID FROM EMP e
            START WITH e.PARENT_ID IS NULL
            CONNECT BY PRIOR e.ID = e.PARENT_ID
        """)
        self.assertIsNone(result.error, result.error)
        got = pairs(result)
        self.assertIn(("EMP.ID", "TGT.ID", DIRECT), got)
        self.assertIn(("EMP.PARENT_ID", "TGT.PARENT", DIRECT), got)
        filters = [e for e in result.edges if e.kind == FILTER]
        self.assertTrue(any("CONNECT BY" in e.transform for e in filters),
                        [e.transform for e in filters])
        self.assertTrue(any("START WITH" in e.transform for e in filters),
                        [e.transform for e in filters])
        filter_src = {(s.table, s.column) for e in filters for s in e.sources}
        self.assertIn(("EMP", "ID"), filter_src)
        self.assertIn(("EMP", "PARENT_ID"), filter_src)


class PivotTests(unittest.TestCase):
    def test_pivot_value_and_key_columns(self):
        result = analyze("""
            INSERT INTO TGT (WH_CD, IN_QTY, OUT_QTY)
            SELECT WH_CD, IN_QTY, OUT_QTY
            FROM (
              SELECT WH_CD, TRX_TP_CD, TRX_QTY FROM SYNWMS.STK_TRX
            ) PIVOT (SUM(TRX_QTY) FOR TRX_TP_CD IN ('10' AS IN_QTY, '20' AS OUT_QTY))
        """)
        self.assertIsNone(result.error, result.error)
        got = pairs(result)
        self.assertIn(("SYNWMS.STK_TRX.TRX_QTY", "TGT.IN_QTY", VIA_CTE), got)
        self.assertIn(("SYNWMS.STK_TRX.TRX_QTY", "TGT.OUT_QTY", VIA_CTE), got)
        self.assertIn(("SYNWMS.STK_TRX.WH_CD", "TGT.WH_CD", VIA_CTE), got)
        self.assertFalse(any(p[0] == "SYNWMS.STK_TRX.IN_QTY" for p in got))
        filter_src = {(s.table, s.column) for e in result.edges
                      if e.kind == FILTER for s in e.sources}
        self.assertIn(("SYNWMS.STK_TRX", "TRX_TP_CD"), filter_src)

    def test_table_pivot_does_not_invent_output_column(self):
        result = analyze("""
            INSERT INTO TGT (WH_CD, IN_QTY)
            SELECT WH_CD, IN_QTY FROM SYNWMS.STK_TRX
            PIVOT (SUM(TRX_QTY) FOR TRX_TP_CD IN ('10' AS IN_QTY))
        """)
        self.assertIsNone(result.error, result.error)
        got = pairs(result)
        self.assertIn(("SYNWMS.STK_TRX.TRX_QTY", "TGT.IN_QTY", DIRECT), got)
        self.assertIn(("SYNWMS.STK_TRX.WH_CD", "TGT.WH_CD", DIRECT), got)
        self.assertFalse(any(p[0].endswith(".IN_QTY") and p[1] == "TGT.IN_QTY"
                             and p[0] != "SYNWMS.STK_TRX.TRX_QTY" for p in got))

    def test_unpivot_maps_value_to_source_columns(self):
        result = analyze("""
            INSERT INTO TGT (WH_CD, TP, QTY)
            SELECT WH_CD, TP, QTY FROM SYNWMS.STK_TRX
            UNPIVOT (QTY FOR TP IN (IN_QTY, OUT_QTY))
        """)
        self.assertIsNone(result.error, result.error)
        got = pairs(result)
        self.assertIn(("SYNWMS.STK_TRX.IN_QTY", "TGT.QTY", DIRECT), got)
        self.assertIn(("SYNWMS.STK_TRX.OUT_QTY", "TGT.QTY", DIRECT), got)
        self.assertIn(("SYNWMS.STK_TRX.WH_CD", "TGT.WH_CD", DIRECT), got)
        self.assertFalse(any(p[0] == "SYNWMS.STK_TRX.TP" for p in got))
        self.assertFalse(any(p[0] == "SYNWMS.STK_TRX.QTY" for p in got))


if __name__ == "__main__":
    unittest.main()
