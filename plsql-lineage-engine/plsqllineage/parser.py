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

    @property
    def ok(self) -> bool:
        return not self.problems


class _Collector(ErrorListener):
    def __init__(self) -> None:
        self.problems: list[SyntaxProblem] = []

    def syntaxError(self, recognizer, offending, line, column, msg, e) -> None:
        self.problems.append(SyntaxProblem(line, column, msg))


def parse_text(text: str, path: pathlib.Path | None = None) -> ParseResult:
    """Parse one PL/SQL source unit. Never raises on a syntax error."""
    lexer = PlSqlLexer(CaseInsensitiveStream(text))
    lexer.removeErrorListeners()
    parser = PlSqlParser(CommonTokenStream(lexer))
    parser._interp.predictionMode = PredictionMode.SLL
    collector = _Collector()
    parser.removeErrorListeners()
    parser.addErrorListener(collector)
    tree = parser.sql_script()
    return ParseResult(path=path, tree=tree, problems=collector.problems)


def parse_file(path: str | pathlib.Path) -> ParseResult:
    path = pathlib.Path(path)
    return parse_text(path.read_text(encoding="utf-8"), path)
