#!/usr/bin/env python3
"""Fetch the PL/SQL grammar and generate the Python parser.

The generated parser is ~10 MB and is not committed. Run this once before
using the engine; re-run it only to move to a new grammar or ANTLR version.

Two patches are applied to the grammar before generation. grammars-v4 writes
its embedded actions in Java syntax, which the Python target emits verbatim
and which then fails to import:

    {a() && b()}?   ->  {a() and b()}?     SyntaxError at import
    this.foo()      ->  self.foo()         NameError at parse time

Both are mechanical and are reapplied on every run, so the upstream grammar is
never edited in place.

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


def patch_grammar(path: pathlib.Path) -> int:
    """Rewrite Java-syntax actions into Python. Returns the number of edits."""
    text = original = path.read_text(encoding="utf-8")
    # {a() && b()}? -> {a() and b()}?  (only inside embedded actions)
    text = re.sub(r"(\{[^{}]*?)\s&&\s([^{}]*?\}\?)", r"\1 and \2", text)
    text = re.sub(r"(\{[^{}]*?)\s\|\|\s([^{}]*?\}\?)", r"\1 or \2", text)
    text = re.sub(r"\bthis\.", "self.", text)
    if text != original:
        path.write_text(text, encoding="utf-8")
    return sum(1 for a, b in zip(original.splitlines(), text.splitlines()) if a != b)


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

    for name in RUNTIME_FILES:
        fetch(f"{GRAMMAR_BASE}/{name}", out / pathlib.Path(name).name)
    (out / "__init__.py").write_text("", encoding="utf-8")

    total = sum(p.stat().st_size for p in out.glob("*.py"))
    print(f"완료: {out.relative_to(root)}  ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
