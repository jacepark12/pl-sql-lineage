"""Engine integration: dynamic SQL, empty-source diagnostics, wrapping, DB links."""

from __future__ import annotations

import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from plsqllineage.engine import analyze_path
from plsqllineage.parser import parse_text
from plsqllineage.structure import extract


PKG_DYNAMIC = """
CREATE OR REPLACE PACKAGE BODY DYN IS
  PROCEDURE RUN IS
    v_sql VARCHAR2(400) := 'INSERT INTO TGT (A) SELECT X FROM SRC';
  BEGIN
    EXECUTE IMMEDIATE v_sql;
    EXECUTE IMMEDIATE 'INSERT INTO TGT (A) SELECT X FROM SRC';
    EXECUTE IMMEDIATE v_sql USING 1;
  END;
END DYN;
"""

PKG_PARAMS = """
CREATE OR REPLACE PACKAGE BODY ORD IS
  PROCEDURE APPLY(I_ORD_NO IN VARCHAR2, I_MODR_ID IN VARCHAR2,
                  O_ERRCODE OUT NUMBER) IS
  BEGIN
    O_ERRCODE := 404;
    INSERT INTO TGT (ORD_NO, MODR_ID) VALUES (I_ORD_NO, I_MODR_ID);
  END;
END ORD;
"""

PROC_BARE = """
PROCEDURE FOO IS
BEGIN
  INSERT INTO TGT (A) SELECT s.X FROM SRC s;
END;
"""

FUNC_BARE = """
FUNCTION F RETURN NUMBER IS
BEGIN
  INSERT INTO TGT (A) SELECT s.X FROM SRC s;
  RETURN 1;
END;
"""

TRIG_BARE = """
TRIGGER TRG_FOO
BEFORE INSERT ON TGT
FOR EACH ROW
BEGIN
  INSERT INTO LOG (A) SELECT s.X FROM SRC s;
END;
"""

PKG_DBLINK = """
CREATE OR REPLACE PACKAGE BODY LNK IS
  PROCEDURE RUN IS
  BEGIN
    INSERT INTO TGT (A) SELECT s.X FROM SYN.T@REMOTE s;
    INSERT INTO TGT (B) SELECT s.X FROM SYN.T s;
    MERGE INTO TGT t
    USING SYN.T@REMOTE r
    ON (t.k = r.k)
    WHEN MATCHED THEN UPDATE SET t.a = r.a;
  END;
END LNK;
"""


def _write_analyze(source: str, name: str = "pkg.sql"):
    tmp = tempfile.TemporaryDirectory()
    path = pathlib.Path(tmp.name) / name
    path.write_text(source, encoding="utf-8")
    analysis = analyze_path(path)
    return analysis, tmp


def _codes(analysis) -> list[str]:
    return [d.code for d in analysis.diagnostics]


class DynamicSqlTests(unittest.TestCase):
    def test_execute_immediate_is_diagnosed_without_fake_edges(self):
        analysis, tmp = _write_analyze(PKG_DYNAMIC, "dyn.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            dyn = [d for d in analysis.diagnostics if d.code == "DYNAMIC_SQL"]
            self.assertGreaterEqual(len(dyn), 2)
            for item in dyn:
                self.assertEqual(item.location.get("file"), "dyn.sql")
                self.assertEqual(item.location.get("package"), "DYN")
                self.assertEqual(item.location.get("procedure"), "RUN")
                self.assertIsInstance(item.location.get("line"), int)
            tables = {e["target"]["table"] for e in analysis.edges}
            tables.update(s["table"] for e in analysis.edges for s in e["sources"])
            self.assertNotIn("TGT", tables)
            self.assertNotIn("SRC", tables)
            literal = [r for r in analysis.relations
                       if r["method"] == "dynamic-literal"]
            self.assertEqual(
                [(r["source"], r["target"], r["operation"]) for r in literal],
                [("SRC", "TGT", "INSERT")])
            self.assertEqual(literal[0]["location"]["procedure"], "RUN")
            self.assertTrue(any("변수 v_sql" in d.message for d in dyn))
            self.assertFalse(any("문자열 리터럴" in d.message for d in dyn))
            self.assertTrue(any("USING" in d.message for d in dyn))
        finally:
            tmp.cleanup()


class DynamicLiteralTests(unittest.TestCase):
    def test_partial_literal_keeps_tables_and_variable_name_does_not(self):
        source = """
CREATE OR REPLACE PACKAGE BODY P IS
  PROCEDURE RUN IS
  BEGIN
    EXECUTE IMMEDIATE 'INSERT INTO TGT (A) SELECT X FROM SRC WHERE ' || v_pred;
    EXECUTE IMMEDIATE 'UPDATE ' || v_tab || ' SET A = 1';
  END;
END P;
"""
        analysis, tmp = _write_analyze(source, "partial.sql")
        try:
            literal = [r for r in analysis.relations if r["method"] == "dynamic-literal"]
            self.assertEqual(
                [(r["source"], r["target"]) for r in literal],
                [("SRC", "TGT")])
            self.assertTrue(any(d.code == "DYNAMIC_SQL_PARTIAL" for d in analysis.diagnostics))
            self.assertTrue(any(d.code == "DYNAMIC_SQL" for d in analysis.diagnostics))
            self.assertFalse(any(r["target"] == "V_TAB" for r in analysis.relations))
        finally:
            tmp.cleanup()


class EmptySourceTests(unittest.TestCase):
    def test_parameter_drop_is_diagnosed_literal_is_quiet(self):
        analysis, tmp = _write_analyze(PKG_PARAMS, "ord.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            params = [d for d in analysis.diagnostics
                      if d.code == "PARAMETER_UNRESOLVED"]
            names = {n for d in params for n in d.location.get("names", [])}
            self.assertTrue({"I_ORD_NO", "I_MODR_ID"} <= names, names)
            for item in params:
                self.assertIn("호출자", item.message)
            noisy = [d for d in analysis.diagnostics
                     if "O_ERRCODE" in d.message
                     or "O_ERRCODE" in str(d.location.get("names", []))]
            self.assertEqual(noisy, [])
            self.assertFalse(analysis.edges)
        finally:
            tmp.cleanup()


class WrapCreateEngineTests(unittest.TestCase):
    def test_bare_procedure_parses_and_yields_edges(self):
        analysis, tmp = _write_analyze(PROC_BARE, "foo.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            self.assertFalse(any(c == "PARSE_FAILED" for c in _codes(analysis)))
            pairs = [(s["table"], s["column"], e["target"]["table"], e["target"]["column"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertIn(("SRC", "X", "TGT", "A"), pairs)
            relations = [(r["source"], r["target"], r["operation"], r["method"])
                         for r in analysis.relations]
            self.assertIn(("SRC", "TGT", "INSERT", "static"), relations)
            self.assertEqual(analysis.relations[0]["location"]["procedure"], "FOO")
        finally:
            tmp.cleanup()

    def test_bare_function_parses(self):
        parsed = parse_text(FUNC_BARE)
        self.assertTrue(parsed.ok, parsed.problems)
        units = extract(parsed.tree, parsed.text)
        self.assertTrue(units)
        self.assertTrue(any(s.name.upper() == "F" for u in units for s in u.subprograms))

    def test_bare_trigger_parses(self):
        parsed = parse_text(TRIG_BARE)
        self.assertTrue(parsed.ok, parsed.problems)
        analysis, tmp = _write_analyze(TRIG_BARE, "trg.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            self.assertFalse(any(c == "PARSE_FAILED" for c in _codes(analysis)))
        finally:
            tmp.cleanup()

    def test_edit_marker_still_fails(self):
        src = "!! 여기\nPROCEDURE BROKEN IS BEGIN NULL; END;"
        parsed = parse_text(src)
        self.assertFalse(parsed.ok)


class EncodingEngineTests(unittest.TestCase):
    def test_cp949_file_is_analyzed(self):
        text = (
            "PROCEDURE FOO IS\n"
            "BEGIN\n"
            "  -- 한글 주석\n"
            "  INSERT INTO TGT (A) SELECT s.X FROM SRC s;\n"
            "END;\n"
        )
        tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(tmp.name) / "foo.sql"
        path.write_bytes(text.encode("cp949"))
        try:
            with self.assertRaises(UnicodeDecodeError):
                path.read_bytes().decode("utf-8")
            analysis = analyze_path(path)
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            pairs = [(s["table"], e["target"]["table"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertIn(("SRC", "TGT"), pairs)
        finally:
            tmp.cleanup()


class DbLinkEngineTests(unittest.TestCase):
    def test_remote_and_local_are_distinct_in_edges(self):
        analysis, tmp = _write_analyze(PKG_DBLINK, "lnk.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            sources = [(s["table"], s.get("dblink"), s["column"])
                       for e in analysis.edges for s in e["sources"]]
            self.assertTrue(
                any(t == "SYN.T@REMOTE" and link == "REMOTE" for t, link, _ in sources),
                sources)
            self.assertTrue(
                any(t == "SYN.T" and not link for t, link, _ in sources),
                sources)
        finally:
            tmp.cleanup()


PKG_ROWTYPE = """
CREATE OR REPLACE PACKAGE BODY RT IS
  PROCEDURE RUN IS
    r SYNWMS.MST_ITEM%ROWTYPE;
    v_wgt NUMBER;
  BEGIN
    INSERT INTO SYNWMS.STK_ONHAND (ITEM_CD, UNIT_WGT)
      VALUES (r.ITEM_CD, r.UNIT_WGT);
    v_wgt := r.UNIT_WGT;
    UPDATE SYNWMS.STK_ONHAND t SET t.WGT_TOT = v_wgt;
  END;
END RT;
"""

PKG_TYPE_NOT_VALUE = """
CREATE OR REPLACE PACKAGE BODY TP IS
  PROCEDURE RUN IS
    v_qty SYNWMS.MST_ITEM.UNIT_WGT%TYPE;
  BEGIN
    -- %TYPE is a declared type, not a value that flowed from MST_ITEM.
    INSERT INTO SYNWMS.STK_ONHAND (ONHAND_QTY) VALUES (v_qty);
  END;
END TP;
"""

PKG_TYPE_SELECT_INTO_WINS = """
CREATE OR REPLACE PACKAGE BODY TP2 IS
  PROCEDURE RUN IS
    v_qty SYNWMS.MST_ITEM.UNIT_WGT%TYPE;
  BEGIN
    SELECT s.ONHAND_QTY INTO v_qty FROM SYNWMS.STK_ONHAND s;
    INSERT INTO SYNWMS.STK_TRX (TRX_QTY) VALUES (v_qty);
  END;
END TP2;
"""

PKG_CURSOR_LOOP = """
CREATE OR REPLACE PACKAGE BODY LP IS
  PROCEDURE RUN IS
    CURSOR c_pick IS SELECT j.ALLOC_QTY AS PICK_QTY FROM SYNWMS.OUT_ALLOC j;
  BEGIN
    FOR rec IN c_pick LOOP
      INSERT INTO SYNWMS.STK_TRX (TRX_QTY) VALUES (rec.PICK_QTY);
    END LOOP;
  END;
END LP;
"""

PKG_ROWTYPE_CATALOG = """
CREATE OR REPLACE PACKAGE BODY RTC IS
  PROCEDURE RUN IS
    r SYNWMS.MST_ITEM%ROWTYPE;
  BEGIN
    INSERT INTO TGT (A, B) VALUES (r.ITEM_CD, r.NO_SUCH_COL);
  END;
END RTC;
"""


class RowtypeTests(unittest.TestCase):
    def test_rowtype_field_in_dml_and_assignment(self):
        analysis, tmp = _write_analyze(PKG_ROWTYPE, "rt.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            pairs = [(s["table"], s["column"], e["target"]["table"], e["target"]["column"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertIn(("SYNWMS.MST_ITEM", "ITEM_CD", "SYNWMS.STK_ONHAND", "ITEM_CD"), pairs)
            self.assertIn(("SYNWMS.MST_ITEM", "UNIT_WGT", "SYNWMS.STK_ONHAND", "UNIT_WGT"), pairs)
            self.assertIn(("SYNWMS.MST_ITEM", "UNIT_WGT", "SYNWMS.STK_ONHAND", "WGT_TOT"), pairs)
        finally:
            tmp.cleanup()

    def test_catalog_unknown_column_is_not_invented(self):
        tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(tmp.name)
        (root / "packages").mkdir()
        (root / "ddl").mkdir()
        (root / "packages" / "rtc.sql").write_text(PKG_ROWTYPE_CATALOG, encoding="utf-8")
        (root / "ddl" / "catalog.sql").write_text(
            "CREATE TABLE SYNWMS.MST_ITEM (\n  ITEM_CD VARCHAR2(20)\n);\n",
            encoding="utf-8")
        try:
            analysis = analyze_path(root)
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            pairs = [(s["table"], s["column"], e["target"]["column"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertIn(("SYNWMS.MST_ITEM", "ITEM_CD", "A"), pairs)
            self.assertFalse(any(c == "NO_SUCH_COL" for _, c, _ in pairs), pairs)
        finally:
            tmp.cleanup()


class TypeAnchorTests(unittest.TestCase):
    def test_type_anchor_is_not_used_as_value_source(self):
        analysis, tmp = _write_analyze(PKG_TYPE_NOT_VALUE, "tp.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            pairs = [(s["table"], s["column"], e["target"]["table"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertFalse(
                any(t == "SYNWMS.MST_ITEM" and c == "UNIT_WGT" for t, c, _ in pairs),
                pairs)
        finally:
            tmp.cleanup()

    def test_select_into_still_fills_typed_variable(self):
        analysis, tmp = _write_analyze(PKG_TYPE_SELECT_INTO_WINS, "tp2.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            pairs = [(s["table"], s["column"], e["target"]["table"], e["target"]["column"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertIn(
                ("SYNWMS.STK_ONHAND", "ONHAND_QTY", "SYNWMS.STK_TRX", "TRX_QTY"),
                pairs)
            self.assertFalse(
                any(t == "SYNWMS.MST_ITEM" for t, _, _, _ in pairs), pairs)
        finally:
            tmp.cleanup()


class CursorLoopRegressionTests(unittest.TestCase):
    def test_for_rec_in_cursor_still_binds_projection(self):
        analysis, tmp = _write_analyze(PKG_CURSOR_LOOP, "lp.sql")
        try:
            self.assertEqual(analysis.parsed, 1, _codes(analysis))
            pairs = [(s["table"], s["column"], e["target"]["column"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertIn(("SYNWMS.OUT_ALLOC", "ALLOC_QTY", "TRX_QTY"), pairs)
        finally:
            tmp.cleanup()


def _canon(analysis):
    edges = sorted(json.dumps(e, sort_keys=True, ensure_ascii=False)
                   for e in analysis.edges)
    diags = sorted(
        (d.code, d.message, json.dumps(d.location, sort_keys=True,
                                       ensure_ascii=False))
        for d in analysis.diagnostics)
    return edges, diags


class JobPoolTests(unittest.TestCase):
    def test_resolve_jobs_never_exceeds_files(self):
        from plsqllineage.engine import _parent_warmup_count, resolve_jobs
        self.assertEqual(resolve_jobs(8, 1), 1)
        self.assertEqual(resolve_jobs(8, 3), 3)
        self.assertEqual(resolve_jobs(0, 2), min(os.cpu_count() or 1, 2))
        self.assertEqual(resolve_jobs(1, 40), 1)
        self.assertEqual(_parent_warmup_count(24, 4), 8)
        self.assertEqual(_parent_warmup_count(3, 2), 1)
        self.assertEqual(_parent_warmup_count(4, 4), 0)
        self.assertEqual(_parent_warmup_count(400, 4), 8)

    def test_two_workers_match_sequential_edges(self):
        tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(tmp.name)
        (root / "packages").mkdir()
        (root / "packages" / "a.sql").write_text(PKG_PARAMS, encoding="utf-8")
        (root / "packages" / "b.sql").write_text(PKG_DYNAMIC, encoding="utf-8")
        (root / "packages" / "c.sql").write_text(PROC_BARE, encoding="utf-8")
        try:
            sequential = analyze_path(root, jobs=1)
            parallel = analyze_path(root, jobs=2)
            self.assertEqual(sequential.parsed, 3)
            self.assertEqual(parallel.parsed, 3)
            self.assertEqual(parallel.jobs, 2)
            self.assertEqual(_canon(sequential), _canon(parallel))
            self.assertEqual(
                [t.file for t in sequential.timings],
                [t.file for t in parallel.timings])
        finally:
            tmp.cleanup()


class ParseProgressTests(unittest.TestCase):
    def test_sequential_logs_start_before_done(self):
        tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(tmp.name)
        (root / "packages").mkdir()
        (root / "packages" / "a.sql").write_text(PKG_PARAMS, encoding="utf-8")
        (root / "packages" / "b.sql").write_text(PROC_BARE, encoding="utf-8")
        buf = io.StringIO()
        try:
            with patch("sys.stderr", buf):
                analysis = analyze_path(root, progress=True, jobs=1)
            self.assertEqual(analysis.parsed, 2)
            lines = [ln for ln in buf.getvalue().splitlines()
                     if ln.startswith("PARSE_")]
            self.assertTrue(lines[0].startswith("PARSE_RUN"), lines[0])
            self.assertIn("files=2 jobs=1", lines[0])
            starts = [ln for ln in lines if ln.startswith("PARSE_START")]
            dones = [ln for ln in lines if ln.startswith("PARSE_DONE")]
            self.assertEqual(len(starts), 2, buf.getvalue())
            self.assertEqual(len(dones), 2, buf.getvalue())
            self.assertIn("file=packages/a.sql", starts[0])
            self.assertIn("started=1/2", starts[0])
            self.assertIn("file=packages/a.sql", dones[0])
            self.assertIn("done=1/2", dones[0])
            self.assertIn("file=packages/b.sql", starts[1])
            self.assertLess(lines.index(starts[0]), lines.index(dones[0]))
            self.assertLess(lines.index(dones[0]), lines.index(starts[1]))
        finally:
            tmp.cleanup()

    def test_worker_logs_start_and_done(self):
        from plsqllineage import engine
        tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(tmp.name)
        path = root / "pkg.sql"
        path.write_text(PROC_BARE, encoding="utf-8")
        ctx = engine._mp_context()
        started = ctx.Value("i", 0)
        done = ctx.Value("i", 0)
        lock = ctx.Lock()
        buf = io.StringIO()
        try:
            engine._init_worker(1, started, done, lock, True)
            with patch("sys.stderr", buf):
                part = engine._analyze_one((str(path), str(root), {}))
            text = buf.getvalue()
            self.assertIn("PARSE_START", text)
            self.assertIn("PARSE_DONE", text)
            self.assertIn("file=pkg.sql", text)
            self.assertIn("started=1/1", text)
            self.assertIn("done=1/1", text)
            self.assertEqual(part.parsed, 1)
            self.assertEqual(started.value, 1)
            self.assertEqual(done.value, 1)
        finally:
            engine._WORKER_STATE = None
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
