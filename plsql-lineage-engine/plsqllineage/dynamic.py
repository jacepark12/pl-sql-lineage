"""Recover a dynamic SQL string when its table names are literals.

``EXECUTE IMMEDIATE`` and ``OPEN ... FOR`` carry the statement as an expression.
A single string literal, or a concatenation of string literals, is the same
evidence as static SQL. A non-literal piece is replaced with ``NULL`` only so
the surrounding literal text can be parsed. If that parse does not yield a
table relation, the statement stays unresolved: a table name built from a
variable is not guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EXECUTE = re.compile(r"(?is)^\s*EXECUTE\s+IMMEDIATE\s+(.*)$")
_OPEN_FOR = re.compile(r"(?is)^\s*OPEN\b.*?\bFOR\s+(.*)$")
_USING = re.compile(r"(?is)\bUSING\b")

_QUOTE_CLOSE = {"[": "]", "{": "}", "(": ")", "<": ">"}


@dataclass(frozen=True)
class RecoveredSql:
    """``sql`` is set when a parseable statement was recovered.

    ``partial`` is true when a non-literal fragment was replaced and must not
    be treated as a fully static statement.
    """

    sql: str | None = None
    partial: bool = False


def recover_dynamic_sql(text: str) -> RecoveredSql:
    """Return the SQL text hidden in a dynamic statement, if tables can be read."""
    argument = _argument(text)
    if argument is None:
        return RecoveredSql()
    pieces = _pieces(argument)
    if not pieces:
        return RecoveredSql()
    literals = [kind == "lit" for kind, _ in pieces]
    if not any(literals):
        return RecoveredSql()
    if all(literals):
        sql = "".join(body for _, body in pieces).strip()
        return RecoveredSql(sql=sql or None, partial=False)
    stitched = "".join(body if kind == "lit" else " NULL " for kind, body in pieces)
    sql = " ".join(stitched.split())
    return RecoveredSql(sql=sql or None, partial=True)


def _argument(text: str) -> str | None:
    body = text.strip().rstrip(";").strip()
    match = _EXECUTE.match(body) or _OPEN_FOR.match(body)
    if match is None:
        return None
    argument = match.group(1).strip()
    cut = _cut_using(argument)
    return cut.strip() or None


def _cut_using(argument: str) -> str:
    """Drop a top-level ``USING`` clause. It binds values, not table names."""
    depth = 0
    in_string = False
    i = 0
    while i < len(argument):
        char = argument[i]
        if in_string:
            if char == "'":
                if i + 1 < len(argument) and argument[i + 1] == "'":
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if char == "'":
            in_string = True
            i += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif depth == 0 and _USING.match(argument, i):
            return argument[:i]
        i += 1
    return argument


def _pieces(argument: str) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    i = 0
    length = len(argument)
    while i < length:
        while i < length and argument[i].isspace():
            i += 1
        if i >= length:
            break
        literal = _read_literal(argument, i)
        if literal is not None:
            body, i = literal
            pieces.append(("lit", body))
        else:
            start = i
            depth = 0
            while i < length:
                if argument[i] == "'":
                    skipped = _read_literal(argument, i)
                    if skipped is None:
                        i += 1
                        continue
                    _, i = skipped
                    continue
                if argument[i] == "(":
                    depth += 1
                elif argument[i] == ")" and depth:
                    depth -= 1
                elif depth == 0 and argument.startswith("||", i):
                    break
                i += 1
            body = argument[start:i].strip()
            if body:
                pieces.append(("expr", body))
        while i < length and argument[i].isspace():
            i += 1
        if argument.startswith("||", i):
            i += 2
    return pieces


def _read_literal(text: str, index: int) -> tuple[str, int] | None:
    """Read one Oracle string literal starting at ``index``. ``None`` if not one."""
    length = len(text)
    cursor = index
    if cursor < length and text[cursor] in "nN":
        cursor += 1
    if (cursor + 1 < length and text[cursor] in "qQ" and text[cursor + 1] == "'"
            and cursor + 2 < length):
        opener = text[cursor + 2]
        closer = _QUOTE_CLOSE.get(opener, opener)
        end = text.find(closer + "'", cursor + 3)
        if end < 0:
            return None
        return text[cursor + 3:end], end + 2
    if cursor >= length or text[cursor] != "'":
        return None
    chars: list[str] = []
    cursor += 1
    while cursor < length:
        if text[cursor] == "'":
            if cursor + 1 < length and text[cursor + 1] == "'":
                chars.append("'")
                cursor += 2
                continue
            return "".join(chars), cursor + 1
        chars.append(text[cursor])
        cursor += 1
    return None
