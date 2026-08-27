"""Unit tests for the DYNAMIC_SQL scoring bucket."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synplsql.core import UNRESOLVED
from synplsql.score import dynamic_sql_bucket, main, score


def _truth():
    return {
        "edges": [
            {
                "kind": UNRESOLVED,
                "target": {"table": "SYNWMS.STK_TRX", "column": "TRX_QTY"},
                "sources": [],
                "location": {"file": "packages/a.sql"},
            },
            {
                "kind": UNRESOLVED,
                "target": {"table": "SYNWMS.STK_TRX", "column": None},
                "sources": [],
                "location": {"file": "packages/a.sql"},
            },
            {
                "kind": "DIRECT",
                "target": {"table": "TGT", "column": "A"},
                "sources": [{"table": "SRC", "column": "X"}],
                "location": {"file": "packages/a.sql"},
            },
        ],
    }


def _manifest():
    return {"packages": [{"file": "packages/a.sql", "tier": 1}]}


class DynamicSqlBucketTests(unittest.TestCase):
    def test_counts_expected_unresolved_vs_engine_diagnostics(self):
        engine = {
            "edges": [
                {
                    "target": {"table": "TGT", "column": "A"},
                    "sources": [{"table": "SRC", "column": "X"}],
                    "kind": "DIRECT",
                    "location": {"file": "packages/a.sql"},
                },
            ],
            "diagnostics": [
                {"code": "DYNAMIC_SQL", "severity": "warning",
                 "message": "EXECUTE IMMEDIATE"},
                {"code": "DYNAMIC_SQL", "severity": "warning",
                 "message": "OPEN FOR"},
                {"code": "UNRESOLVED", "severity": "warning",
                 "message": "소스 없는 엣지"},
                {"code": "PARAMETER_UNRESOLVED", "severity": "warning",
                 "message": "호출자"},
                {"code": "SQL_NOT_ANALYZED", "severity": "warning"},
            ],
        }
        bucket = dynamic_sql_bucket(_truth(), engine)
        self.assertEqual(bucket["expected_unresolved"], 2)
        self.assertEqual(bucket["engine_dynamic_sql"], 2)
        self.assertEqual(bucket["engine_unresolved"], 1)
        self.assertEqual(bucket["engine"], 3)

    def test_unresolved_truth_is_excluded_from_prf(self):
        engine_pairs = {("SRC.X", "TGT.A"): {"DIRECT"}}
        result = score(_truth(), _manifest(), engine_pairs, ignore_schema=False)
        self.assertEqual(result["edges"]["expected"], 1)
        self.assertEqual(result["edges"]["true_positive"], 1)
        self.assertEqual(result["edges"]["false_negative"], 0)
        self.assertEqual(result["unresolved"]["count"], 2)

    def test_cli_prints_dynamic_sql_counts(self):
        truth = _truth()
        manifest = _manifest()
        engine = {
            "edges": [
                {
                    "target": {"table": "TGT", "column": "A"},
                    "sources": [{"table": "SRC", "column": "X"}],
                    "kind": "DIRECT",
                    "location": {"file": "packages/a.sql"},
                },
            ],
            "diagnostics": [
                {"code": "DYNAMIC_SQL", "severity": "warning", "message": "dyn"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "truth.json").write_text(
                json.dumps(truth), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8")
            (root / "engine.json").write_text(
                json.dumps(engine), encoding="utf-8")
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = main([
                    "--truth", str(root / "truth.json"),
                    "--manifest", str(root / "manifest.json"),
                    "--engine", str(root / "engine.json"),
                ])
            self.assertEqual(rc, 0)
            text = buf.getvalue()
            self.assertIn("DYNAMIC_SQL", text)
            self.assertIn("정답 UNRESOLVED 2건", text)
            self.assertIn("엔진 DYNAMIC_SQL 진단 1건", text)


if __name__ == "__main__":
    unittest.main()
