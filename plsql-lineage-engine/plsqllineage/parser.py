"""Parse Oracle PL/SQL into an ANTLR tree.

The grammar (grammars-v4) matches keywords in upper case only. Upper-casing the
whole file before lexing would work for keywords but corrupts everything the
lineage needs to read back verbatim - string literals, and the original casing
of identifiers in expressions. ``CaseInsensitiveStream`` instead upper-cases
only the characters the lexer *compares*, leaving the text the tree reports
untouched.

Parsing runs in SLL mode, which is markedly faster than the default and falls
back to full LL only where SLL cannot decide. ANTLR caches its decision DFA on
the parser class, so the first file pays a one-time warm-up (tens of seconds on
this grammar) and later files run roughly an order of magnitude faster.

Production dumps from ``ALL_SOURCE.TEXT`` often omit ``CREATE OR REPLACE``.
``wrap_create`` prefixes it when the unit already looks like a PACKAGE /
PROCEDURE / FUNCTION / TRIGGER so ANTLR can parse; genuine junk is left
untouched and still surfaces as ``PARSE_FAILED``.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field

_GENERATED = pathlib.Path(__file__).resolve().parent / "_generated"
if str(_GENERATED) not in sys.path:
    sys.path.insert(0, str(_GENERATED))

try:
    from antlr4 import CommonTokenStream, InputStream
    from antlr4.atn.PredictionMode import PredictionMode
    from antlr4.error.ErrorListener import ErrorListener
except ImportError as exc:                                    # pragma: no cover
    raise ImportError(
        "antlr4-python3-runtime 이 필요합니다: pip install antlr4-python3-runtime"
    ) from exc

try:
    from PlSqlLexer import PlSqlLexer
    from PlSqlParser import PlSqlParser
except ImportError as exc:                                    # pragma: no cover
    raise ImportError(
        "생성된 파서가 없습니다. 먼저 실행하십시오:\n"
        "  python3 scripts/build_parser.py"
    ) from exc


# utf-8 first (BOM is a leading character the wrapper skips), then Korean
# legacy. A later encoding is only tried when the previous one raises.
SOURCE_ENCODINGS = ("utf-8", "cp949")

_CREATE_PREFIX = "CREATE OR REPLACE "

# Object kinds ALL_SOURCE.TEXT starts with. CREATE itself is left alone.
_UNIT_KINDS = ("PACKAGE", "PROCEDURE", "FUNCTION", "TRIGGER")
_EDITIONABLE = ("EDITIONABLE", "NONEDITIONABLE")


class CaseInsensitiveStream(InputStream):
    """Feed the lexer upper case while ``getText`` still returns the original."""

    def LA(self, offset: int) -> int:
        code = super().LA(offset)
        if code <= 0:            # EOF, or nothing to fold
            return code
        return ord(chr(code).upper())


@dataclass
class SyntaxProblem:
    line: int
    column: int
    message: str


@dataclass
class ParseResult:
    path: pathlib.Path | None
    tree: object
    problems: list[SyntaxProblem] = field(default_factory=list)
    text: str = ""
    encoding: str | None = None
    decode_error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.problems and self.decode_error is None


class _Collector(ErrorListener):
    def __init__(self) -> None:
        self.problems: list[SyntaxProblem] = []

    def syntaxError(self, recognizer, offending, line, column, msg, e) -> None:
        self.problems.append(SyntaxProblem(line, column, msg))


def read_source(path: str | pathlib.Path) -> tuple[str, str]:
    """Read a source file as ``(text, encoding)``.

    Tries utf-8 then cp949. Raises ``UnicodeDecodeError`` if none accept the
    bytes; callers that must not crash a whole run catch that.
    """
    path = pathlib.Path(path)
    data = path.read_bytes()
    last: UnicodeDecodeError | None = None
    for encoding in SOURCE_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last = exc
    assert last is not None
    raise last


def _skip_trivia(text: str, pos: int) -> int:
    """Advance past whitespace, BOM, and comments so wrapping sees the unit."""
    n = len(text)
    while pos < n:
        ch = text[pos]
        if ch in " \t\r\n\ufeff":
            pos += 1
            continue
        if text.startswith("--", pos):
            nl = text.find("\n", pos)
            pos = n if nl < 0 else nl + 1
            continue
        if text.startswith("/*", pos):
            end = text.find("*/", pos + 2)
            if end < 0:
                return n
            pos = end + 2
            continue
        break
    return pos


def _match_word(text: str, pos: int, word: str) -> bool:
    end = pos + len(word)
    if text[pos:end].upper() != word:
        return False
    if end < len(text) and (text[end].isalnum() or text[end] in "_$#"):
        return False
    return True


def wrap_create(text: str) -> str:
    """Prefix ``CREATE OR REPLACE`` when the unit looks like ALL_SOURCE.TEXT.

    Inserted on the same line as the object keyword so ANTLR line numbers of
    the body stay put. Sources that already start with CREATE, or with
    something that is not a unit keyword (edit markers, stray SQL), are
    returned unchanged.
    """
    pos = _skip_trivia(text, 0)
    if pos >= len(text):
        return text
    if _match_word(text, pos, "CREATE"):
        return text

    start = pos
    for flag in _EDITIONABLE:
        if _match_word(text, pos, flag):
            pos = _skip_trivia(text, pos + len(flag))
            break

    for kind in _UNIT_KINDS:
        if _match_word(text, pos, kind):
            return text[:start] + _CREATE_PREFIX + text[start:]
    return text


def parse_text(text: str, path: pathlib.Path | None = None,
               encoding: str | None = None) -> ParseResult:
    """Parse one PL/SQL source unit. Never raises on a syntax error."""
    wrapped = wrap_create(text)
    lexer = PlSqlLexer(CaseInsensitiveStream(wrapped))
    lexer.removeErrorListeners()
    parser = PlSqlParser(CommonTokenStream(lexer))
    parser._interp.predictionMode = PredictionMode.SLL
    collector = _Collector()
    parser.removeErrorListeners()
    parser.addErrorListener(collector)
    tree = parser.sql_script()
    return ParseResult(path=path, tree=tree, problems=collector.problems,
                       text=wrapped, encoding=encoding)


def parse_file(path: str | pathlib.Path) -> ParseResult:
    path = pathlib.Path(path)
    try:
        text, encoding = read_source(path)
    except UnicodeDecodeError as exc:
        return ParseResult(
            path=path, tree=None, problems=[], text="",
            decode_error=f"{exc.encoding}: {exc.reason}")
    return parse_text(text, path, encoding)
