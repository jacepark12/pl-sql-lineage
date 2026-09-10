"""Source wrapping (ALL_SOURCE.TEXT) and encoding fallbacks."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from plsqllineage.parser import parse_text, read_source, wrap_create


class WrapCreateTests(unittest.TestCase):
    def test_procedure_without_create_is_prefixed(self):
        src = "PROCEDURE FOO IS\nBEGIN\n  NULL;\nEND;"
        out = wrap_create(src)
        self.assertTrue(out.startswith("CREATE OR REPLACE PROCEDURE"))
        self.assertEqual(out.count("CREATE OR REPLACE"), 1)
        # Same-line insert: body line numbers must not shift.
        self.assertEqual(src.splitlines()[2], out.splitlines()[2])

    def test_function_package_body_and_trigger(self):
        self.assertTrue(
            wrap_create("FUNCTION F RETURN NUMBER IS BEGIN NULL; END;")
            .startswith("CREATE OR REPLACE FUNCTION"))
        self.assertTrue(
            wrap_create("PACKAGE BODY P IS\nEND P;")
            .startswith("CREATE OR REPLACE PACKAGE BODY"))
        self.assertTrue(
            wrap_create("TRIGGER TRG BEFORE INSERT ON T FOR EACH ROW\nBEGIN NULL; END;")
            .startswith("CREATE OR REPLACE TRIGGER"))

    def test_existing_create_is_left_alone(self):
        src = "CREATE OR REPLACE PROCEDURE FOO IS BEGIN NULL; END;"
        self.assertEqual(wrap_create(src), src)

    def test_skips_leading_comment(self):
        src = "-- dump\nPROCEDURE FOO IS BEGIN NULL; END;"
        out = wrap_create(src)
        self.assertIn("CREATE OR REPLACE PROCEDURE", out)
        self.assertTrue(out.startswith("-- dump\n"))

    def test_edit_marker_is_not_wrapped(self):
        src = "!! 여기\nPROCEDURE BROKEN IS BEGIN NULL; END;"
        self.assertEqual(wrap_create(src), src)

    def test_editionable_procedure(self):
        src = "EDITIONABLE PROCEDURE FOO IS BEGIN NULL; END;"
        self.assertTrue(wrap_create(src).startswith(
            "CREATE OR REPLACE EDITIONABLE PROCEDURE"))


class EncodingTests(unittest.TestCase):
    def test_cp949_snippet_is_readable(self):
        text = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "  v VARCHAR2(100) := '한글';\n"
            "BEGIN\n"
            "  NULL;\n"
            "END;\n"
        )
        data = text.encode("cp949")
        with self.assertRaises(UnicodeDecodeError):
            data.decode("utf-8")
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as handle:
            handle.write(data)
            path = pathlib.Path(handle.name)
        try:
            decoded, encoding = read_source(path)
            self.assertEqual(encoding, "cp949")
            self.assertIn("한글", decoded)
        finally:
            path.unlink()

    def test_utf8_is_preferred(self):
        text = "CREATE OR REPLACE PROCEDURE p IS BEGIN NULL; END;\n"
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as handle:
            handle.write(text.encode("utf-8"))
            path = pathlib.Path(handle.name)
        try:
            decoded, encoding = read_source(path)
            self.assertEqual(encoding, "utf-8")
            self.assertEqual(decoded, text)
        finally:
            path.unlink()


class WrapCreateParseTests(unittest.TestCase):
    def test_bare_units_parse(self):
        for src in (
            "PROCEDURE FOO IS BEGIN NULL; END;",
            "FUNCTION F RETURN NUMBER IS BEGIN NULL; END;",
            """TRIGGER TRG_FOO
BEFORE INSERT ON TGT
FOR EACH ROW
BEGIN
  NULL;
END;""",
        ):
            parsed = parse_text(src)
            self.assertTrue(parsed.ok, (src, parsed.problems))
            self.assertTrue(parsed.text.startswith("CREATE OR REPLACE"))
            self.assertEqual(parsed.profile.mode, "SLL")
            self.assertEqual(parsed.profile.ll_s, 0.0)


class TwoStageParseTests(unittest.TestCase):
    def test_valid_package_stays_on_sll(self):
        src = """
CREATE OR REPLACE PACKAGE BODY P IS
  PROCEDURE RUN IS
  BEGIN
    INSERT INTO TGT (A) SELECT s.X FROM SRC s;
  END;
END P;
"""
        parsed = parse_text(src)
        self.assertTrue(parsed.ok, parsed.problems)
        self.assertEqual(parsed.profile.mode, "SLL")
        self.assertGreater(parsed.profile.sll_s, 0.0)
        self.assertEqual(parsed.profile.ll_s, 0.0)
        self.assertAlmostEqual(parsed.profile.antlr_s, parsed.profile.sll_s)

    def test_sll_bail_retries_ll_on_junk(self):
        src = "!! 여기\nPROCEDURE BROKEN IS BEGIN NULL; END;"
        parsed = parse_text(src)
        self.assertFalse(parsed.ok)
        self.assertTrue(parsed.problems)
        self.assertEqual(parsed.profile.mode, "LL")
        self.assertGreaterEqual(parsed.profile.sll_s, 0.0)
        self.assertGreater(parsed.profile.ll_s, 0.0)
        self.assertGreater(parsed.profile.antlr_s, 0.0)

    def test_mid_file_junk_does_not_keep_sll_recovery_tree_as_ok(self):
        src = """
CREATE OR REPLACE PACKAGE BODY P IS
  PROCEDURE RUN IS
  BEGIN
    NULL;
    !! SYNTAX_BOMB;
    NULL;
  END;
END P;
"""
        parsed = parse_text(src)
        self.assertFalse(parsed.ok)
        self.assertEqual(parsed.profile.mode, "LL")
        self.assertGreaterEqual(len(parsed.problems), 1)


if __name__ == "__main__":
    unittest.main()
