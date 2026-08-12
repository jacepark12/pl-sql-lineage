"""Self-check for a generated corpus.

The plan lists "a generator bug corrupts the truth set" as the risk that would
mislead engine development the most, because a wrong label looks exactly like a
correct one. This module is the guard: it re-derives what it can from the
*rendered text* and confronts it with the emitted truth, rather than trusting
the IR twice.

    python -m synplsql.validate --out out
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

from . import schema as S
from .core import UNRESOLVED, VALUE_KINDS

WINDOW_BEFORE = 3
WINDOW_AFTER = 4

# INDIRECT_FILTER transforms carry a clause label that says where the predicate
# came from. The label is truth metadata, not rendered text, so it is stripped
# before the transform is looked for in the source.
CLAUSE_LABELS = ("UPDATE WHERE ", "DELETE WHERE ", "MERGE ON ", "START WITH ",
                 "CONNECT BY ", "GROUP BY ", "HAVING ", "WHERE ", "JOIN ")


def _norm(text: str) -> str:
    # The legacy outer-join marker is rendering syntax, not part of the
    # predicate the edge was built from, so it is normalised away.
    return " ".join(text.replace("(+)", "").split())


def _strip_clause_label(text: str) -> str:
    for label in CLAUSE_LABELS:
        if text.startswith(label):
            return text[len(label):]
    return text


def _base_table(fq: str) -> str:
    return fq.split("@")[0]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks: Counter[str] = Counter()

    def check(self, name: str, ok: bool, detail: str) -> None:
        self.checks[name] += 1
        if not ok and len(self.errors) < 60:
            self.errors.append(f"[{name}] {detail}")
        if not ok:
            self.checks[name + ":failed"] += 1


def validate(out_dir: pathlib.Path) -> Report:
    r = Report()
    truth = json.loads((out_dir / "lineage_truth.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    files: dict[str, list[str]] = {}
    for entry in manifest["packages"]:
        path = out_dir / entry["file"]
        files[entry["file"]] = path.read_text(encoding="utf-8").split("\n")
        r.check("manifest_line_count", entry["lines"] == len(files[entry["file"]]),
                f"{entry['file']}: manifest says {entry['lines']}, file has "
                f"{len(files[entry['file']])}")

    known_kinds = set(VALUE_KINDS) | {"INDIRECT_FILTER", UNRESOLVED}

    for e in truth["edges"]:
        loc = e["location"]
        where = f"{loc['file']}:{loc['line']}"
        lines = files.get(loc["file"])
        r.check("edge_file_exists", lines is not None, f"{where}: unknown file")
        if lines is None:
            continue

        r.check("edge_kind_known", e["kind"] in known_kinds,
                f"{where}: unknown kind {e['kind']}")
        r.check("edge_line_in_range", 1 <= loc["line"] <= len(lines),
                f"{where}: line out of range (file has {len(lines)})")
        if not (1 <= loc["line"] <= len(lines)):
            continue

        # 1. the anchored line really sits inside the named procedure
        r.check("edge_procedure_scope",
                _in_procedure(lines, loc["line"], loc["procedure"]),
                f"{where}: line is not inside {loc['procedure']}")

        # 2. the rendered text around the anchor contains the recorded transform
        window = _norm(" ".join(
            lines[max(0, loc["line"] - 1 - WINDOW_BEFORE): loc["line"] + WINDOW_AFTER]))
        transform = _strip_clause_label(_norm(e["transform"]))
        star_expanded = "전개" in (e.get("note") or "")
        if (e["kind"] != UNRESOLVED and transform and len(transform) < 400
                and not star_expanded):
            r.check("edge_transform_rendered", transform in window,
                    f"{where}: transform not found near anchor: {transform[:70]!r}")

        # 3. targets and sources resolve against the DDL catalog
        _check_ref(r, e["target"], where, "target", allow_null_column=True)
        for s in e["sources"]:
            _check_ref(r, s, where, "source", allow_null_column=False)

        # 4. only dynamic SQL is allowed to have no sources
        if e["kind"] == UNRESOLVED:
            r.check("unresolved_has_no_sources", not e["sources"],
                    f"{where}: UNRESOLVED edge carries sources")
        else:
            r.check("edge_has_sources", bool(e["sources"]),
                    f"{where}: {e['kind']} edge with no sources")

        # 5. a value edge must name the column it writes
        if e["kind"] in VALUE_KINDS:
            r.check("value_edge_has_target_column", e["target"]["column"] is not None,
                    f"{where}: {e['kind']} edge without a target column")
            r.check("edge_hops_positive", e["hops"] >= 1,
                    f"{where}: hops={e['hops']}")
            # Every source column must actually appear in the expression the
            # edge was derived from. This is the check that catches the failure
            # that matters most - an alias resolved to the wrong table, which
            # produces a plausible-looking but wrong source.
            # Skipped when the value travelled through a variable, a CTE, or a
            # MERGE USING projection: there the outer expression names the
            # projection, not the base column, and `via` says so.
            if not e.get("via") and not star_expanded and transform:
                missing = [s["column"] for s in e["sources"]
                           if s["column"] not in transform]
                r.check("edge_sources_in_transform", not missing,
                        f"{where}: sources {missing} absent from {transform[:60]!r}")

    for rc in truth["ref_cursors"]:
        for col in rc["columns"]:
            for s in col["sources"]:
                _check_ref(r, s, rc["location"]["file"], "ref_cursor_source", False)

    # 6. every generated file is structurally closed
    for name, lines in files.items():
        text = "\n".join(lines)
        r.check("file_parens_balanced", text.count("(") == text.count(")"),
                f"{name}: unbalanced parentheses "
                f"({text.count('(')} open / {text.count(')')} close)")
        r.check("file_quotes_balanced", text.count("'") % 2 == 0,
                f"{name}: odd number of single quotes")
        r.check("file_has_package_body", "CREATE OR REPLACE PACKAGE BODY" in text,
                f"{name}: no package body")
        r.check("file_terminated", lines[-1] == "" and lines[-2] == "/",
                f"{name}: does not end with a slash terminator")

    return r


_PROC_HEAD = re.compile(r"^\s{2}(?:PROCEDURE|FUNCTION)\s+(\w+)")
_PROC_END = re.compile(r"^\s{2}END\s+(\w+);")


def _in_procedure(lines: list[str], line_no: int, proc: str) -> bool:
    current = None
    for i, text in enumerate(lines[:line_no], start=1):
        head = _PROC_HEAD.match(text)
        if head:
            current = head.group(1)
            continue
        end = _PROC_END.match(text)
        if end and end.group(1) == current:
            current = None
    return current == proc


def _check_ref(r: Report, ref: dict, where: str, label: str,
               allow_null_column: bool) -> None:
    fq = _base_table(ref["table"])
    table = S.CATALOG.get(fq)
    r.check(f"{label}_table_in_catalog", table is not None,
            f"{where}: unknown table {ref['table']}")
    if table is None:
        return
    if ref["column"] is None:
        r.check(f"{label}_column_nullable", allow_null_column,
                f"{where}: {label} column is null but must not be")
        return
    r.check(f"{label}_column_in_catalog", table.has(ref["column"]),
            f"{where}: {fq} has no column {ref['column']}")


# --- hand-written fixtures ----------------------------------------------------

# Transforms that are deliberately synthetic: the label describes the construct
# rather than quoting a literal fragment of the source.
SYNTHETIC_TRANSFORMS = ("s.*", "PIVOT FOR")


def validate_fixtures(fixture_root: pathlib.Path, truth: dict | None) -> Report:
    """Check the hand-written fixtures, and cross-check them against the
    generator's own labels.

    The fixtures exist precisely because the generated truth cannot audit
    itself: both the SQL and the labels come from the same IR, so a bug in the
    IR is invisible from inside. These labels were written by hand against
    hand-written SQL, so agreeing with them is evidence, not tautology.
    """

    r = Report()
    known_kinds = set(VALUE_KINDS) | {"INDIRECT_FILTER", UNRESOLVED}
    fixture_kinds: set[str] = set()

    dirs = sorted(d for d in fixture_root.iterdir() if d.is_dir())
    r.check("fixtures_present", bool(dirs), f"{fixture_root}: no fixture directories")

    for d in dirs:
        sql_path = d / "input.sql"
        label_path = d / "expected.lineage.json"
        r.check("fixture_files_present", sql_path.exists() and label_path.exists(),
                f"{d.name}: missing input.sql or expected.lineage.json")
        if not (sql_path.exists() and label_path.exists()):
            continue

        sql = _norm(sql_path.read_text(encoding="utf-8"))
        doc = json.loads(label_path.read_text(encoding="utf-8"))
        r.check("fixture_has_note", bool(doc.get("note")),
                f"{d.name}: no note explaining what the fixture tests")

        entries = list(doc.get("edges", [])) + list(doc.get("unresolved", []))
        r.check("fixture_not_empty", bool(entries), f"{d.name}: no labelled edges")

        for e in entries:
            where = f"{d.name}"
            r.check("fixture_kind_known", e["kind"] in known_kinds,
                    f"{where}: unknown kind {e['kind']}")
            fixture_kinds.add(e["kind"])

            transform = _strip_clause_label(_norm(e.get("transform", "")))
            synthetic = any(s in transform for s in SYNTHETIC_TRANSFORMS)
            if transform and not synthetic and e["kind"] != UNRESOLVED:
                r.check("fixture_transform_in_sql", transform in sql,
                        f"{where}: transform not present in input.sql: {transform[:60]!r}")

            if e["target"]["table"]:
                _check_ref(r, e["target"], where, "fixture_target", True)
            for s in e.get("sources", []):
                _check_ref(r, s, where, "fixture_source", False)

    if truth is not None:
        corpus_kinds = {e["kind"] for e in truth["edges"]}
        missing = sorted(corpus_kinds - fixture_kinds)
        r.check("fixture_covers_corpus_kinds", not missing,
                f"edge kinds produced by the generator but never hand-labelled: {missing}")
        extra = sorted(fixture_kinds - corpus_kinds)
        r.check("corpus_covers_fixture_kinds", not extra,
                f"edge kinds hand-labelled but never produced by the generator: {extra}")

    return r


def check_determinism(seed: int, packages: int, lines: int, tiers: list[int],
                      profile: dict) -> bool:
    """Same seed must yield byte-identical packages (plan principle 3)."""

    from .core import assign_ids, render_package
    from .generate import generate

    def run() -> list[str]:
        built, _, _ = generate(seed, packages, lines, tiers, profile)
        out = []
        for pkg in built:
            assign_ids(pkg)
            out.append(render_package(pkg)[0])
        return out

    return run() == run()


def main(argv: list[str] | None = None) -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(prog="synplsql.validate",
                                 description="생성 코퍼스 자체 검증")
    ap.add_argument("--out", default="out")
    ap.add_argument("--profile", default=str(root / "profile.json"))
    ap.add_argument("--skip-determinism", action="store_true")
    ap.add_argument("--fixtures", default=str(root / "fixtures"),
                    help="수작업 픽스처 디렉터리")
    args = ap.parse_args(argv)

    out_dir = pathlib.Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir

    report = validate(out_dir)
    truth = json.loads((out_dir / "lineage_truth.json").read_text(encoding="utf-8"))

    fixture_root = pathlib.Path(args.fixtures)
    if fixture_root.exists():
        fx = validate_fixtures(fixture_root, truth)
        report.checks.update(fx.checks)
        report.errors.extend(fx.errors)

    print(f"코퍼스 자체 검증: {out_dir}")
    print("-" * 70)
    width = max(len(k) for k in report.checks if not k.endswith(":failed"))
    for name in sorted(k for k in report.checks if not k.endswith(":failed")):
        failed = report.checks.get(name + ":failed", 0)
        total = report.checks[name]
        mark = "OK " if failed == 0 else "FAIL"
        print(f"  {name:<{width}}  {total - failed:>7,} / {total:<7,}  {mark}")
    print("-" * 70)

    if not args.skip_determinism:
        profile = json.loads(pathlib.Path(args.profile).read_text(encoding="utf-8"))
        same = check_determinism(20260812, 4, 6000, [0, 1, 2, 3], profile)
        print(f"  재현성 (동일 seed -> 동일 코퍼스)                {'OK ' if same else 'FAIL'}")
        if not same:
            report.errors.append("[determinism] same seed produced different output")

    if report.errors:
        print(f"\n실패 {len(report.errors)}건 (최대 60건 표시):")
        for msg in report.errors:
            print(f"  - {msg}")
        return 1
    print("\n모든 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
