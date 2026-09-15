"""Parser DFA recording cap: intern up to N states, then stop growing."""

from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from plsqllineage.dfa import (
    DEFAULT_PARSER_DFA_MAX_STATES,
    parser_dfa_state_count,
    reset_parser_dfa,
    set_parser_dfa_max_states,
)
from plsqllineage.engine import main
from plsqllineage.parser import parse_text


SIMPLE = """
CREATE OR REPLACE PROCEDURE p IS
BEGIN
  NULL;
END;
"""

MERGE = """
CREATE OR REPLACE PROCEDURE p IS
BEGIN
  MERGE INTO t USING (SELECT 1 id FROM dual) s ON (t.id = s.id)
  WHEN MATCHED THEN UPDATE SET t.a = s.id
  WHEN NOT MATCHED THEN INSERT (id) VALUES (s.id);
END;
"""

PIVOT = """
CREATE OR REPLACE PACKAGE BODY pkg IS
  PROCEDURE p IS
  BEGIN
    SELECT * FROM t PIVOT (SUM(qty) FOR color IN ('R' AS red, 'B' AS blue));
  END;
END;
"""

XMLQUERY = """
CREATE OR REPLACE PROCEDURE p IS
BEGIN
  FOR rec IN (
    SELECT XMLQUERY('/a' PASSING xmlparse(content '<a/>') RETURNING CONTENT) x
    FROM dual
  ) LOOP
    NULL;
  END LOOP;
END;
"""


class ParserDfaCapTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_parser_dfa()
        set_parser_dfa_max_states(DEFAULT_PARSER_DFA_MAX_STATES)

    def tearDown(self) -> None:
        set_parser_dfa_max_states(DEFAULT_PARSER_DFA_MAX_STATES)
        reset_parser_dfa()

    def test_cap_stops_new_states_and_still_parses(self):
        set_parser_dfa_max_states(10)
        first = parse_text(SIMPLE)
        self.assertTrue(first.ok, first.problems)
        frozen = parser_dfa_state_count()
        self.assertEqual(frozen, 10)
        for src in (MERGE, PIVOT, XMLQUERY):
            parsed = parse_text(src)
            self.assertTrue(parsed.ok, (src, parsed.problems))
            self.assertEqual(parser_dfa_state_count(), frozen)

    def test_zero_is_unlimited(self):
        set_parser_dfa_max_states(0)
        self.assertTrue(parse_text(SIMPLE).ok)
        after_simple = parser_dfa_state_count()
        self.assertGreater(after_simple, 10)
        self.assertTrue(parse_text(MERGE).ok)
        self.assertGreater(parser_dfa_state_count(), after_simple)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            set_parser_dfa_max_states(-1)


class DfaCliTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_parser_dfa_max_states(DEFAULT_PARSER_DFA_MAX_STATES)
        reset_parser_dfa()

    def test_cli_rejects_negative_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "pkg.sql"
            src.write_text(SIMPLE, encoding="utf-8")
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                rc = main(["--input", str(src), "--dfa-max-states", "-3"])
            self.assertEqual(rc, 1)
            self.assertIn("--dfa-max-states", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
