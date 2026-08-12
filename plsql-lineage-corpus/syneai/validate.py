"""Self-check for a generated EAI corpus.

Same posture as ``synplsql.validate``: re-derive from the written artifacts what
can be re-derived, and confront the truth with that rather than trusting the IR
twice. Here it matters more, because the lineage-bearing metadata is inside a
binary blob - if the encoder and the truth disagree, nothing else would notice.

    python3 -m syneai.validate --out out/eai
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter

from synplsql import schema as S
from synplsql.core import CONSTANT, SEVERED, UNRESOLVED, VALUE_KINDS

from . import wmvalues

#: Identifiers observed in the sampled packages. None of them may appear in a
#: generated artifact - see the export-restriction risk in docs/PLAN-EAI.md.
FORBIDDEN = ("FCMD", "CJKX", "IFADM03", "WMSADM", "STORER2", "ALTKN",
             "CD000012", "PG_CRYPT", "ComDBconnect", "WMS03", "PG_BS_")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks: Counter[str] = Counter()

    def check(self, name: str, ok: bool, detail: str) -> None:
        self.checks[name] += 1
        if not ok:
            self.checks[name + ":failed"] += 1
            if len(self.errors) < 40:
                self.errors.append(f"[{name}] {detail}")


def _base_table(fq: str) -> str:
    return fq.split("@")[0]


def _check_ref(r: Report, ref: dict, where: str, label: str,
               allow_null_column: bool) -> None:
    table = S.CATALOG.get(_base_table(ref["table"]))
    r.check(f"{label}_table_in_catalog", table is not None,
            f"{where}: unknown table {ref['table']}")
    if table is None:
        return
    if ref["column"] is None:
        r.check(f"{label}_column_nullable", allow_null_column,
                f"{where}: {label} column is null but must not be")
        return
    r.check(f"{label}_column_in_catalog", table.has(ref["column"]),
            f"{where}: {table.fq} has no column {ref['column']}")


def validate(out_dir: pathlib.Path) -> Report:
    r = Report()
    truth = json.loads((out_dir / "lineage_truth.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    by_name = {i["interface"]: i for i in manifest["interfaces"]}

    # --- artifacts and the blobs inside them ---------------------------------
    blobs: dict[tuple[str, str], dict] = {}
    for entry in manifest["interfaces"]:
        base = out_dir / entry["interface"]
        for rel in entry["artifacts"]:
            path = base / rel
            r.check("artifact_exists", path.exists(), f"{entry['interface']}/{rel}")
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            hit = next((f for f in FORBIDDEN if f in text), None)
            r.check("no_sampled_identifier", hit is None,
                    f"{entry['interface']}/{rel}: contains {hit!r}")

            if rel.startswith("adpt/"):
                found = wmvalues.extract_blobs(text)
                r.check("adapter_has_blob", bool(found),
                        f"{entry['interface']}/{rel}: no IRTNODE_PROPERTY")
                if not found:
                    continue
                try:
                    record, impl = wmvalues.decode_b64(found[0])
                    ok, detail = True, ""
                except wmvalues.WmValuesError as exc:
                    record, impl, ok, detail = {}, "", False, str(exc)
                r.check("blob_decodes", ok, f"{entry['interface']}/{rel}: {detail}")
                if not ok:
                    continue
                r.check("blob_roundtrips",
                        wmvalues.encode_b64(record, impl) == "".join(found[0].split()),
                        f"{entry['interface']}/{rel}: re-encode differs")
                name = rel.split("/")[1]
                blobs[(entry["interface"], name)] = record

                fq = f"{record.get('tables.realSchemaName')}.{record.get('tables.tableName')}"
                r.check("blob_table_in_catalog", fq in S.CATALOG,
                        f"{entry['interface']}/{rel}: blob names unknown table {fq}")
                if fq in S.CATALOG:
                    declared = {c.split("\n")[0]
                                for c in record.get("tables.columnInfo") or []}
                    actual = set(S.CATALOG[fq].column_names)
                    r.check("blob_columninfo_matches_catalog", declared == actual,
                            f"{entry['interface']}/{rel}: columnInfo differs from DDL "
                            f"({sorted(declared ^ actual)[:4]})")

    # --- edges ----------------------------------------------------------------
    known_kinds = set(VALUE_KINDS) | {"INDIRECT_FILTER", UNRESOLVED, CONSTANT, SEVERED}
    for e in truth["edges"]:
        loc = e["location"]
        iface = loc["interface"]
        where = f"{iface}/{loc.get('artifact', '')}#{loc.get('step_path', '')}"
        r.check("edge_kind_known", e["kind"] in known_kinds,
                f"{where}: unknown kind {e['kind']}")
        r.check("edge_interface_known", iface in by_name, f"{where}: unknown interface")
        if iface not in by_name:
            continue

        artifact = out_dir / iface / loc["artifact"]
        r.check("edge_artifact_exists", artifact.exists(), where)
        if artifact.exists() and loc.get("step_path"):
            text = artifact.read_text(encoding="utf-8")
            leaf = loc["step_path"].rsplit("/", 1)[-1].split("[")[0]
            r.check("edge_step_kind_present", f"<{leaf}" in text,
                    f"{where}: no <{leaf}> element in the artifact")

        _check_ref(r, e["target"], where, "target", allow_null_column=True)
        for s in e["sources"]:
            _check_ref(r, s, where, "source", allow_null_column=False)

        if e["kind"] in VALUE_KINDS:
            r.check("value_edge_has_sources", bool(e["sources"]),
                    f"{where}: {e['kind']} with no sources")
            r.check("value_edge_has_target_column", e["target"]["column"] is not None,
                    f"{where}: {e['kind']} without a target column")
            # The whole point of the EAI layer: the source column name differs
            # from the target column name, so a name-matching engine fails.
            r.check("edge_hops_cross_layer", e["hops"] >= 2,
                    f"{where}: hops={e['hops']} - an EAI edge crosses at least "
                    f"the adapter and the pipeline")
        if e["kind"] in (SEVERED, CONSTANT):
            r.check("no_source_kind_has_no_sources", not e["sources"],
                    f"{where}: {e['kind']} carries sources")

        # A write edge must agree with the adapter blob it came from.
        adapter = loc.get("adapter")
        if adapter and e["target"]["column"]:
            record = blobs.get((iface, adapter.split("/")[-1]))
            if record and "update.column" in record:
                r.check("edge_column_in_blob",
                        e["target"]["column"] in (record["update.column"] or []),
                        f"{where}: {e['target']['column']} not in update.column")

    # --- severed fields are actually deleted somewhere ------------------------
    severed_targets = {(e["location"]["interface"], e["target"]["column"])
                       for e in truth["edges"] if e["kind"] == SEVERED}
    for entry in manifest["interfaces"]:
        for fieldname in entry["severed_fields"]:
            r.check("severed_field_has_edge",
                    (entry["interface"], fieldname) in severed_targets,
                    f"{entry['interface']}: {fieldname} deleted but no SEVERED edge")
            flow = out_dir / entry["interface"] / f"srvc/{entry['interface']}_target/flow.xml"
            if flow.exists():
                r.check("severed_field_has_mapdelete",
                        re.search(rf'<MAPDELETE FIELD="[^"]*/{fieldname};',
                                  flow.read_text(encoding="utf-8")) is not None,
                        f"{entry['interface']}: no MAPDELETE for {fieldname}")

    # --- every flow.xml is well-formed XML ------------------------------------
    from xml.etree import ElementTree
    for flow in sorted(out_dir.glob("*/srvc/*/flow.xml")):
        try:
            ElementTree.parse(flow)
            ok, detail = True, ""
        except ElementTree.ParseError as exc:
            ok, detail = False, str(exc)
        r.check("flow_xml_wellformed", ok, f"{flow.name}: {detail}")
    for node in sorted(out_dir.glob("*/**/node.*")):
        try:
            ElementTree.parse(node)
            ok, detail = True, ""
        except ElementTree.ParseError as exc:
            ok, detail = False, str(exc)
        r.check("node_xml_wellformed", ok, f"{node}: {detail}")

    return r


# --- hand-written fixtures ----------------------------------------------------


def validate_fixtures(root: pathlib.Path, truth: dict | None) -> Report:
    """Check the hand-written EAI fixtures and cross-check them with the corpus.

    The flow.xml and the labels here were written by hand; only the blob is
    machine-produced, because the encoder is the only thing that can produce it.
    That still leaves the labels independent of the pipeline simulator, which is
    the part most likely to be wrong.
    """

    r = Report()
    known = set(VALUE_KINDS) | {"INDIRECT_FILTER", UNRESOLVED, CONSTANT, SEVERED}
    fixture_kinds: set[str] = set()

    dirs = sorted(d for d in root.iterdir() if d.is_dir())
    r.check("fixtures_present", bool(dirs), f"{root}: empty")

    for d in dirs:
        needed = ["flow.xml", "node.ndf", "adapter.values.json",
                  "expected.lineage.json"]
        missing = [n for n in needed if not (d / n).exists()]
        r.check("fixture_files_present", not missing, f"{d.name}: missing {missing}")
        if missing:
            continue

        doc = json.loads((d / "expected.lineage.json").read_text(encoding="utf-8"))
        values = json.loads((d / "adapter.values.json").read_text(encoding="utf-8"))
        ndf = (d / "node.ndf").read_text(encoding="utf-8")
        flow = (d / "flow.xml").read_text(encoding="utf-8")

        r.check("fixture_has_note", bool(doc.get("note")), f"{d.name}: no note")
        r.check("fixture_not_empty", bool(doc.get("edges")), f"{d.name}: no edges")

        # the sidecar and the blob must agree, or the fixture documents a lie
        found = wmvalues.extract_blobs(ndf)
        r.check("fixture_blob_present", bool(found), f"{d.name}: no blob in node.ndf")
        if found:
            decoded, _ = wmvalues.decode_b64(found[0])
            r.check("fixture_blob_matches_sidecar", decoded == values,
                    f"{d.name}: node.ndf blob differs from adapter.values.json")

        # nothing that identifies the sampled system may appear
        for label, text in (("flow.xml", flow), ("node.ndf", ndf)):
            hit = next((f for f in FORBIDDEN if f in text), None)
            r.check("fixture_no_sampled_identifier", hit is None,
                    f"{d.name}/{label}: contains {hit!r}")

        for e in doc["edges"]:
            fixture_kinds.add(e["kind"])
            r.check("fixture_kind_known", e["kind"] in known,
                    f"{d.name}: unknown kind {e['kind']}")
            if e["target"]["table"]:
                _check_ref(r, e["target"], d.name, "fixture_target", True)
            for s in e.get("sources", []):
                _check_ref(r, s, d.name, "fixture_source", False)
            if e["kind"] in (SEVERED, CONSTANT):
                r.check("fixture_no_source_kind_empty", not e.get("sources"),
                        f"{d.name}: {e['kind']} carries sources")

    if truth is not None:
        corpus_kinds = {e["kind"] for e in truth["edges"]}
        missing = sorted(corpus_kinds - fixture_kinds)
        r.check("fixture_covers_corpus_kinds", not missing,
                f"kinds produced by the generator but never hand-labelled: {missing}")
    return r


def check_determinism(seed: int, count: int, tiers: list[int], profile: dict) -> bool:
    from .flow import render_flow
    from .generate import generate

    def run() -> list[str]:
        return [render_flow(svc) + "".join(a.blob() for a in i.adapters.values())
                for i in generate(seed, count, tiers, profile) for svc in i.services]

    return run() == run()


def main(argv: list[str] | None = None) -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(prog="syneai.validate",
                                 description="EAI 코퍼스 자체 검증")
    ap.add_argument("--out", default="out/eai")
    ap.add_argument("--profile", default=str(root / "profile-eai.json"))
    ap.add_argument("--skip-determinism", action="store_true")
    ap.add_argument("--fixtures", default=str(root / "fixtures-eai"))
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

    print(f"EAI 코퍼스 자체 검증: {out_dir}")
    print("-" * 70)
    names = sorted(k for k in report.checks if not k.endswith(":failed"))
    width = max(len(k) for k in names)
    for name in names:
        failed = report.checks.get(name + ":failed", 0)
        total = report.checks[name]
        print(f"  {name:<{width}}  {total - failed:>6,} / {total:<6,}  "
              f"{'OK ' if failed == 0 else 'FAIL'}")
    print("-" * 70)

    if not args.skip_determinism:
        profile = json.loads(pathlib.Path(args.profile).read_text(encoding="utf-8"))
        same = check_determinism(20260812, 4, [0, 1, 2, 3], profile)
        print(f"  재현성 (동일 seed -> 동일 코퍼스)              {'OK ' if same else 'FAIL'}")
        if not same:
            report.errors.append("[determinism] same seed produced different output")

    if report.errors:
        print(f"\n실패 {len(report.errors)}건:")
        for msg in report.errors:
            print(f"  - {msg}")
        return 1
    print("\n모든 검증 통과")
    print("  주의: 블롭의 실제 webMethods 호환성은 이 검증의 범위가 아닙니다. "
          "docs/WM-VALUES-FORMAT.md 참고.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
