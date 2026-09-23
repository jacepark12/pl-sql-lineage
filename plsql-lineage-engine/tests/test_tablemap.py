"""Table relations: static statements and dynamic SQL whose tables are literals."""

from __future__ import annotations

import unittest

from plsqllineage.dynamic import recover_dynamic_sql
from plsqllineage.tablemap import statement_relations
from plsqllineage.tablequery import load_relations, render_table_query


class StatementRelationTests(unittest.TestCase):
    def test_insert_select_names_base_tables_not_columns(self):
        result = statement_relations(
            "INSERT INTO SYNWMS.OUT_ALLOC (WH_CD, ORD_QTY) "
            "SELECT d.WH_CD, d.ORD_QTY FROM SYNWMS.OUT_ORDER_D d")
        self.assertIsNone(result.error)
        self.assertEqual(
            [(r.source, r.target, r.operation) for r in result.relations],
            [("SYNWMS.OUT_ORDER_D", "SYNWMS.OUT_ALLOC", "INSERT")])

    def test_join_emits_one_relation_per_source_table(self):
        result = statement_relations(
            "INSERT INTO TGT (A) "
            "SELECT d.A FROM SRC d JOIN OTHER o ON o.ID = d.ID")
        pairs = {(r.source, r.target) for r in result.relations}
        self.assertEqual(pairs, {("SRC", "TGT"), ("OTHER", "TGT")})

    def test_cte_name_is_not_a_table(self):
        result = statement_relations(
            "INSERT INTO TGT (A) "
            "WITH s AS (SELECT x.A AS A FROM SRC x) "
            "SELECT s.A FROM s")
        self.assertEqual(
            [r.source for r in result.relations], ["SRC"])

    def test_select_into_and_literal_values_have_no_relation(self):
        into = statement_relations("SELECT s.A INTO v_a FROM SRC s")
        values = statement_relations("INSERT INTO TGT (A) VALUES ('x')")
        self.assertEqual(into.relations, [])
        self.assertEqual(values.relations, [])

    def test_merge_using_subquery_reaches_the_base_table(self):
        result = statement_relations(
            "MERGE INTO TGT t "
            "USING (SELECT r.A FROM SRC r) s ON (t.K = s.K) "
            "WHEN MATCHED THEN UPDATE SET t.A = s.A")
        self.assertEqual(
            [(r.source, r.target, r.operation) for r in result.relations],
            [("SRC", "TGT", "MERGE")])

    def test_delete_subquery_is_a_source(self):
        result = statement_relations(
            "DELETE FROM TGT t WHERE t.ID IN (SELECT s.ID FROM SRC s)")
        self.assertEqual(
            [(r.source, r.target, r.operation) for r in result.relations],
            [("SRC", "TGT", "DELETE")])

    def test_db_link_stays_on_the_table_name(self):
        result = statement_relations(
            "INSERT INTO TGT (A) SELECT s.X FROM SYN.T@REMOTE s")
        self.assertEqual(result.relations[0].source, "SYN.T@REMOTE")


class DynamicRecoveryTests(unittest.TestCase):
    def test_literal_statement_parses_as_sql(self):
        recovered = recover_dynamic_sql(
            "EXECUTE IMMEDIATE 'INSERT INTO TGT (A) SELECT X FROM SRC'")
        self.assertFalse(recovered.partial)
        result = statement_relations(recovered.sql or "")
        self.assertEqual(result.relations[0].source, "SRC")
        self.assertEqual(result.relations[0].target, "TGT")

    def test_q_quote_literal(self):
        recovered = recover_dynamic_sql(
            "EXECUTE IMMEDIATE q'[INSERT INTO TGT (A) SELECT X FROM SRC]'")
        self.assertEqual(recovered.sql, "INSERT INTO TGT (A) SELECT X FROM SRC")

    def test_predicate_fragment_keeps_literal_tables(self):
        recovered = recover_dynamic_sql(
            "EXECUTE IMMEDIATE 'INSERT INTO TGT (A) SELECT X FROM SRC WHERE ' "
            "|| v_pred")
        self.assertTrue(recovered.partial)
        result = statement_relations(recovered.sql or "")
        self.assertEqual(
            [(r.source, r.target) for r in result.relations],
            [("SRC", "TGT")])

    def test_variable_table_name_is_not_guessed(self):
        recovered = recover_dynamic_sql(
            "EXECUTE IMMEDIATE 'UPDATE ' || v_tab || ' SET A = 1'")
        self.assertTrue(recovered.partial)
        result = statement_relations(recovered.sql or "")
        self.assertEqual(result.relations, [])

    def test_variable_only_has_no_sql(self):
        recovered = recover_dynamic_sql("EXECUTE IMMEDIATE v_sql USING 1")
        self.assertIsNone(recovered.sql)


class TableQueryTests(unittest.TestCase):
    def test_render_includes_procedure(self):
        graph = load_relations({
            "relations": [{
                "source": "SYNWMS.OUT_ORDER_D",
                "target": "SYNWMS.OUT_ALLOC",
                "operation": "INSERT",
                "method": "static",
                "location": {
                    "file": "packages/SYNWMS.PKG_OUT.sql",
                    "line": 42,
                    "package": "PKG_OUT",
                    "procedure": "SP_ALLOC",
                },
            }],
            "diagnostics": [],
        })
        text = render_table_query(graph, "OUT_ALLOC", depth=1)
        self.assertIn("Table: SYNWMS.OUT_ALLOC", text)
        self.assertIn("REL INSERT SYNWMS.OUT_ORDER_D --> SYNWMS.OUT_ALLOC", text)
        self.assertIn("method=static", text)
        self.assertIn("at=packages/SYNWMS.PKG_OUT.sql:42 PKG_OUT.SP_ALLOC", text)
