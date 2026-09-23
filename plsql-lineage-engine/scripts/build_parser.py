#!/usr/bin/env python3
"""Fetch the PL/SQL grammar and generate the Python parser.

The generated parser is ~10 MB and is not committed. Run this once before
using the engine; re-run it only to move to a new grammar or ANTLR version.

Patches are reapplied on every run. The upstream ``.g4`` is never edited in
place and is not committed.

Java actions are rewritten for the Python target, which emits them verbatim:

    {a() && b()}?   ->  {a() and b()}?     SyntaxError at import
    {a() || b()}?   ->  {a() or b()}?
    this.foo()      ->  self.foo()         NameError at parse time

Two grammar narrowings cut prediction cost without accepting more PL/SQL.
``general_element_part`` takes at most one argument list, and ``block``
requires ``DECLARE`` so it is not a duplicate of ``body``. ``trigger_block``
keeps the optional ``DECLARE``. After generation, the two decision points
whose first token is unique are rewritten to LL(1) dispatch. A mismatch
raises; the build does not keep the unpatched parser.

Sources: the ANTLR tool comes from Maven Central and the grammar from
raw.githubusercontent - www.antlr.org is not always reachable.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.request

ANTLR_VERSION = "4.13.2"
GRAMMAR_REF = "master"

JAR_URL = (f"https://repo1.maven.org/maven2/org/antlr/antlr4/{ANTLR_VERSION}"
           f"/antlr4-{ANTLR_VERSION}-complete.jar")
GRAMMAR_BASE = (f"https://raw.githubusercontent.com/antlr/grammars-v4/"
                f"{GRAMMAR_REF}/sql/plsql")
GRAMMAR_FILES = ("PlSqlLexer.g4", "PlSqlParser.g4")
RUNTIME_FILES = ("Python3/PlSqlLexerBase.py", "Python3/PlSqlParserBase.py")


def fetch(url: str, dest: pathlib.Path) -> None:
    if dest.exists():
        print(f"  캐시됨  {dest.name}")
        return
    print(f"  받는 중  {dest.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response:
        dest.write_bytes(response.read())


# Anchored with the leading newline so ``trigger_block`` is not rewritten
# when ``block`` is. A cached grammar that already lost the optional DECLARE
# on ``trigger_block`` is restored.
_ACCIDENTAL_TRIGGER = "\ntrigger_block\n    : DECLARE declare_spec* body\n"
_TRIGGER_BLOCK = "\ntrigger_block\n    : (DECLARE declare_spec*)? body\n"
_AMBIGUOUS_BLOCK = "\nblock\n    : (DECLARE declare_spec*)? body\n"
_DECLARED_BLOCK = "\nblock\n    : DECLARE declare_spec* body\n"

_GEP_STAR = (
    "general_element_part\n"
    "    : (INTRODUCER char_set_name)? id_expression "
    "('@' link_name)? function_argument*\n"
)
_GEP_OPT = (
    "general_element_part\n"
    "    : (INTRODUCER char_set_name)? id_expression "
    "('@' link_name)? function_argument?\n"
)

_OPTIONAL_ARGUMENT_HELPER = re.compile(
    r"\noptional_function_argument\n"
    r"    : \{(self|this)\._input\.LA\(1\) == \1\.LEFT_PAREN\}\? function_argument\n"
    r"    \| \{(self|this)\._input\.LA\(1\) != \2\.LEFT_PAREN\}\?\n"
    r"    ;\n"
)


def _patch_parser_rules(text: str) -> str:
    """Narrow two rules. Raises if the upstream text is not one of the known forms."""
    text = _OPTIONAL_ARGUMENT_HELPER.sub("\n", text)
    if _GEP_STAR in text:
        text = text.replace(_GEP_STAR, _GEP_OPT, 1)
    elif _GEP_OPT not in text:
        raise RuntimeError(
            "general_element_part grammar changed; update the DFA patch")

    if _ACCIDENTAL_TRIGGER in text:
        text = text.replace(_ACCIDENTAL_TRIGGER, _TRIGGER_BLOCK, 1)
    if _AMBIGUOUS_BLOCK in text:
        text = text.replace(_AMBIGUOUS_BLOCK, _DECLARED_BLOCK, 1)
    elif _DECLARED_BLOCK not in text:
        raise RuntimeError("block grammar changed; update the DFA patch")
    if _TRIGGER_BLOCK not in text:
        raise RuntimeError("block grammar changed; update the DFA patch")
    return text


def patch_grammar(path: pathlib.Path) -> int:
    """Rewrite Java actions and, for the parser, the two prediction rules.

    Returns the number of changed lines. Idempotent on an already patched file.
    """
    text = original = path.read_text(encoding="utf-8")
    if path.name == "PlSqlParser.g4":
        text = _patch_parser_rules(text)
    # {a() && b()}? -> {a() and b()}?  (only inside embedded actions)
    text = re.sub(r"(\{[^{}]*?)\s&&\s([^{}]*?\}\?)", r"\1 and \2", text)
    text = re.sub(r"(\{[^{}]*?)\s\|\|\s([^{}]*?\}\?)", r"\1 or \2", text)
    text = re.sub(r"\bthis\.", "self.", text)
    if text != original:
        path.write_text(text, encoding="utf-8")
    return sum(1 for a, b in zip(original.splitlines(), text.splitlines()) if a != b)


def _indent_block(text: str, extra: str = "    ") -> str:
    return "".join(
        extra + line if line.strip() else line
        for line in text.splitlines(keepends=True)
    )


def _patch_general_element_part(text: str) -> str:
    """Replace the argument-list decision with an LL(1) test.

    ``LA(2) != PLUS_SIGN`` keeps ``column(+)`` on the outer-join path.
    """
    start = text.find("\n    def general_element_part(self):\n")
    end = text.find("\n    class Table_elementContext(", start if start >= 0 else 0)
    if start < 0 or end < 0:
        raise RuntimeError(
            "generated general_element_part changed; update parser patch")
    region = text[start:end]
    pattern = re.compile(
        r"(?P<indent>[ \t]+)self\.state = (?P<sync>\d+)\n"
        r"(?P=indent)self\._errHandler\.sync\(self\)\n"
        r"(?P=indent)la_ = self\._interp\.adaptivePredict"
        r"\(self\._input,\s*\d+\s*,\s*self\._ctx\)\n"
        r"(?P=indent)if la_ == 1:\n"
        r"(?P<body>[ \t]+)self\.state = (?P<state>\d+)\n"
        r"(?P=body)self\.function_argument\(\)[ \t]*\n"
        r"(?:(?P=body)pass\n)?"
    )
    found = list(pattern.finditer(region))
    if len(found) != 1:
        raise RuntimeError(
            "generated general_element_part changed; update parser patch")
    match = found[0]
    indent = match.group("indent")
    body = match.group("body")
    replacement = (
        f"{indent}self.state = {match.group('sync')}\n"
        f"{indent}self._errHandler.sync(self)\n"
        f"{indent}if (self._input.LA(1) == PlSqlParser.LEFT_PAREN and\n"
        f"{indent}        self._input.LA(2) != PlSqlParser.PLUS_SIGN):\n"
        f"{body}self.state = {match.group('state')}\n"
        f"{body}self.function_argument()\n"
    )
    region = region[:match.start()] + replacement + region[match.end():]
    return text[:start] + region + text[end:]


def _patch_statement(text: str) -> str:
    """Dispatch ``BEGIN`` to ``body`` and ``DECLARE`` to ``block``.

    Every other alternative still overlaps, so that ``adaptivePredict`` stays.
    """
    start = text.find("\n    def statement(self):\n")
    end = text.find("\n    class Assignment_statementContext(", start if start >= 0 else 0)
    if start < 0 or end < 0:
        raise RuntimeError("generated statement changed; update parser patch")
    region = text[start:end]
    match = re.search(
        r"(?P<indent>[ \t]+)self\.state = (?P<sync>\d+)\n"
        r"(?P=indent)self\._errHandler\.sync\(self\)\n"
        r"(?P<predict>(?P=indent)la_ = self\._interp\.adaptivePredict"
        r"\(self\._input,\s*\d+\s*,\s*self\._ctx\)\n)"
        r"(?P<chain>(?P=indent)if la_ == 1:\n.*?)"
        r"(?=\n[ \t]*except RecognitionException as re:)",
        region,
        re.DOTALL,
    )
    if match is None:
        raise RuntimeError("generated statement changed; update parser patch")
    chain = match.group("chain")
    body = re.search(
        r"if la_ == 1:\n"
        r"(?P<inner>[ \t]+)self\.enterOuterAlt\(localctx, 1\)\n"
        r"(?P=inner)self\.state = (?P<state>\d+)\n"
        r"(?P=inner)self\.body\(\)",
        chain,
    )
    block = re.search(
        r"elif la_ == 2:\n"
        r"(?P<inner>[ \t]+)self\.enterOuterAlt\(localctx, 2\)\n"
        r"(?P=inner)self\.state = (?P<state>\d+)\n"
        r"(?P=inner)self\.block\(\)",
        chain,
    )
    if body is None or block is None:
        raise RuntimeError("generated statement changed; update parser patch")
    indent = match.group("indent")
    inner = body.group("inner")
    rebuilt = (
        f"{indent}self.state = {match.group('sync')}\n"
        f"{indent}self._errHandler.sync(self)\n"
        f"{indent}_statement_start = self._input.LA(1)\n"
        f"{indent}if _statement_start == PlSqlParser.BEGIN:\n"
        f"{inner}self.enterOuterAlt(localctx, 1)\n"
        f"{inner}self.state = {body.group('state')}\n"
        f"{inner}self.body()\n"
        f"{indent}elif _statement_start == PlSqlParser.DECLARE:\n"
        f"{inner}self.enterOuterAlt(localctx, 2)\n"
        f"{inner}self.state = {block.group('state')}\n"
        f"{inner}self.block()\n"
        f"{indent}else:\n"
        f"{_indent_block(match.group('predict') + chain)}"
    )
    region = region[:match.start()] + rebuilt + region[match.end():]
    return text[:start] + region + text[end:]


def patch_generated_parser(path: pathlib.Path) -> int:
    """Apply both LL(1) dispatches. Returns the number of sites rewritten."""
    text = path.read_text(encoding="utf-8")
    text = _patch_general_element_part(text)
    text = _patch_statement(text)
    path.write_text(text, encoding="utf-8")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="캐시된 문법과 jar 을 버리고 다시 받는다")
    args = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parents[1]
    work = root / ".parser-build"
    out = root / "plsqllineage" / "_generated"

    if args.force and work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    if not shutil.which("java"):
        print("java 가 필요합니다 (ANTLR 도구 실행용).", file=sys.stderr)
        return 1

    print(f"ANTLR {ANTLR_VERSION} / grammars-v4 @ {GRAMMAR_REF}")
    jar = work / "antlr.jar"
    fetch(JAR_URL, jar)
    for name in GRAMMAR_FILES:
        fetch(f"{GRAMMAR_BASE}/{name}", work / name)

    print("문법 패치 (Java 문법 -> Python)")
    for name in GRAMMAR_FILES:
        edits = patch_grammar(work / name)
        print(f"  {name}: {edits} 줄")

    print("파서 생성")
    if out.exists():
        shutil.rmtree(out)
    result = subprocess.run(
        ["java", "-jar", str(jar), "-Dlanguage=Python3", "-visitor", "-no-listener",
         "-o", str(out), *GRAMMAR_FILES],
        cwd=work, capture_output=True, text=True)
    for line in (result.stderr or "").splitlines():
        if line.strip() and "Picked up" not in line:
            print(f"  {line}")
    if result.returncode != 0:
        return result.returncode

    generated = out / "PlSqlParser.py"
    sites = patch_generated_parser(generated)
    print(f"  PlSqlParser.py: {sites} generated dispatch patch")

    for name in RUNTIME_FILES:
        fetch(f"{GRAMMAR_BASE}/{name}", out / pathlib.Path(name).name)
    (out / "__init__.py").write_text("", encoding="utf-8")

    total = sum(p.stat().st_size for p in out.glob("*.py"))
    print(f"완료: {out.relative_to(root)}  ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
