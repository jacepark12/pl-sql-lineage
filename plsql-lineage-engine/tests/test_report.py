"""Parse-completion report and per-phase timings."""

from __future__ import annotations

import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from plsqllineage.engine import (
    Analysis,
    Diagnostic,
    FileTiming,
    StatementTiming,
    analyze_path,
    main,
)
from plsqllineage.parser import parse_text
from plsqllineage.report import build_report, format_report, report_to_dict


PKG = """
CREATE OR REPLACE PACKAGE BODY PROF IS
  PROCEDURE RUN IS
  BEGIN
    INSERT INTO TGT (A) SELECT s.X FROM SRC s;
  END;
END PROF;
"""

BROKEN = "!! 여기\nPROCEDURE BROKEN IS BEGIN NULL; END;"


class ParseProfileTests(unittest.TestCase):
    def test_successful_parse_records_lex_and_antlr(self):
        parsed = parse_text(PKG)
        self.assertTrue(parsed.ok, parsed.problems)
        self.assertGreater(parsed.profile.tokens, 10)
        self.assertGreaterEqual(parsed.profile.lex_s, 0.0)
        self.assertGreaterEqual(parsed.profile.antlr_s, 0.0)
        self.assertGreater(parsed.profile.parse_s, 0.0)

    def test_syntax_error_still_profiles(self):
        parsed = parse_text(BROKEN)
        self.assertFalse(parsed.ok)
        self.assertGreater(parsed.profile.tokens, 0)
        self.assertGreaterEqual(parsed.profile.antlr_s, 0.0)


class FilePhaseTests(unittest.TestCase):
    def test_analyze_path_fills_phase_fields_and_edges(self):
        tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(tmp.name) / "prof.sql"
        path.write_text(PKG, encoding="utf-8")
        try:
            analysis = analyze_path(path)
            self.assertEqual(analysis.parsed, 1)
            self.assertEqual(len(analysis.timings), 1)
            timing = analysis.timings[0]
            self.assertTrue(timing.ok)
            self.assertGreater(timing.tokens, 10)
            self.assertGreaterEqual(timing.antlr_s, 0.0)
            self.assertGreaterEqual(timing.sqlmap_s, 0.0)
            self.assertGreaterEqual(timing.extract_s, 0.0)
            self.assertGreaterEqual(timing.statements, 1)
            self.assertGreaterEqual(timing.edges, 1)
            self.assertTrue(analysis.statement_timings)
            pairs = [(s["table"], e["target"]["table"])
                     for e in analysis.edges for s in e["sources"]]
            self.assertIn(("SRC", "TGT"), pairs)
        finally:
            tmp.cleanup()

    def test_parse_failed_file_is_timed(self):
        tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(tmp.name) / "bad.sql"
        path.write_text(BROKEN, encoding="utf-8")
        try:
            analysis = analyze_path(path)
            self.assertEqual(analysis.parsed, 0)
            self.assertEqual(analysis.files, 1)
            timing = analysis.timings[0]
            self.assertFalse(timing.ok)
            self.assertGreater(timing.syntax_problems, 0)
            self.assertEqual(analysis.diagnostics[0].code, "PARSE_FAILED")
        finally:
            tmp.cleanup()


class ReportTests(unittest.TestCase):
    def _analysis(self) -> Analysis:
        analysis = Analysis()
        analysis.files = 2
        analysis.parsed = 1
        analysis.edges = [{
            "target": {"table": "TGT", "column": "A"},
            "sources": [{"table": "SRC", "column": "X"}],
            "kind": "DIRECT",
        }]
        analysis.diagnostics = [
            Diagnostic("error", "PARSE_FAILED", "boom", {"file": "bad.sql"}),
            Diagnostic("warning", "SQL_NOT_ANALYZED", "unhandled", {"file": "ok.sql"}),
        ]
        analysis.timings = [
            FileTiming("first.sql", 100, 2.0, 0.5, True,
                       antlr_s=1.8, lex_s=0.2, sqlmap_s=0.4),
            FileTiming("bad.sql", 20, 0.3, 0.0, False,
                       antlr_s=0.3, syntax_problems=2),
        ]
        analysis.statement_timings = [
            StatementTiming("first.sql", 10, "dml", 80, 0.4, None),
        ]
        analysis.catalog_s = 0.01
        analysis.catalog_tables = 3
        return analysis

    def test_format_contains_complete_line_and_bottleneck(self):
        report = build_report(self._analysis(), 2.6, input_path="/tmp/in")
        text = format_report(report)
        self.assertIn("PARSE_COMPLETE files=1/2", text)
        self.assertIn("파싱 완료 보고서", text)
        self.assertIn("<< 병목", text)
        self.assertIn("PARSE_FAILED", text)
        self.assertIn("SQL_NOT_ANALYZED", text)
        self.assertIn("권고", text)
        self.assertTrue(report.recommendations)
        payload = report_to_dict(report)
        self.assertEqual(payload["parsed"], 1)
        self.assertEqual(payload["parse_failed"], 1)
        self.assertIn("SQL_NOT_ANALYZED", payload["diagnostic_counts"])

    def test_cli_writes_report_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "pkg.sql"
            src.write_text(PKG, encoding="utf-8")
            report = pathlib.Path(tmp) / "parse-report.txt"
            report_json = pathlib.Path(tmp) / "parse-report.json"
            timings = pathlib.Path(tmp) / "timings.json"
            out = pathlib.Path(tmp) / "engine.json"
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                rc = main([
                    "--input", str(src),
                    "--out", str(out),
                    "--report", str(report),
                    "--report-json", str(report_json),
                    "--timings", str(timings),
                ])
            self.assertEqual(rc, 0)
            text = report.read_text(encoding="utf-8")
            self.assertIn("PARSE_COMPLETE files=1/1", text)
            self.assertIn("상태: 완료", text)
            self.assertIn("PARSE_COMPLETE", buf.getvalue())
            payload = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["parsed"], 1)
            self.assertGreaterEqual(payload["edges"], 1)
            self.assertTrue(payload["phases"])
            per_file = json.loads(timings.read_text(encoding="utf-8"))
            self.assertEqual(len(per_file), 1)
            self.assertIn("antlr_s", per_file[0])
            self.assertIn("sqlmap_s", per_file[0])


if __name__ == "__main__":
    unittest.main()
