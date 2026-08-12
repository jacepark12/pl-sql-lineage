"""Score a lineage engine's output against the corpus truth set.

    python -m synplsql.score --truth out/lineage_truth.json \\
                             --manifest out/manifest.json \\
                             --engine reports/engine.json --format sqlflow-mvp

Two engine formats are understood:

``generic``
    The same shape as ``lineage_truth.json``: ``{"edges": [{"target": {...},
    "sources": [...], "kind": "..."}]}``.

``sqlflow-mvp``
    The JSON contract of the analyzer in this repository: ``relationships`` with
    ``type`` in ``direct`` / ``indirect`` / ``call`` / ``dynamic_sql`` and ids
    shaped like ``column.<table>.<column>`` or ``table.<table>``.

Because a coarse engine cannot distinguish TRANSFORM from AGGREGATE, kinds are
compared at two levels: the exact label, and the coarse class (does the value
flow, or is it only a filter).
"""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter, defaultdict

from .core import INDIRECT_FILTER, UNRESOLVED, VALUE_KINDS

VALUE = "VALUE"
FILTER = "FILTER"
DYNAMIC = "DYNAMIC"


def coarse(kind: str) -> str:
    if kind in VALUE_KINDS:
        return VALUE
    if kind == INDIRECT_FILTER:
        return FILTER
    return DYNAMIC


# --- normalisation ------------------------------------------------------------


def node_key(table: str | None, column: str | None, ignore_schema: bool) -> str:
    table = (table or "").upper().split("@")[0]
    if ignore_schema and "." in table:
        table = table.split(".")[-1]
    column = (column or "*").upper()
    return f"{table}.{column}"


def truth_pairs_by_file(truth: dict, ignore_schema: bool):
    out: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for e in truth["edges"]:
        if e["kind"] == UNRESOLVED:
            continue
        tgt = node_key(e["target"]["table"], e["target"]["column"], ignore_schema)
        for s in e["sources"]:
            out[e["location"]["file"]].add(
                (node_key(s["table"], s["column"], ignore_schema), tgt))
    return dict(out)


def truth_pairs(truth: dict, ignore_schema: bool):
    """(source, target) -> {kinds, files} for every recorded edge."""

    pairs: dict[tuple[str, str], dict] = {}
    for e in truth["edges"]:
        tgt = node_key(e["target"]["table"], e["target"]["column"], ignore_schema)
        kind = e["kind"]
        if kind == UNRESOLVED:
            continue
        for s in e["sources"]:
            src = node_key(s["table"], s["column"], ignore_schema)
            slot = pairs.setdefault((src, tgt), {"kinds": set(), "files": set()})
            slot["kinds"].add(kind)
            slot["files"].add(e["location"]["file"])
    return pairs


def load_engine(path: pathlib.Path, fmt: str, ignore_schema: bool):
    data = json.loads(path.read_text(encoding="utf-8"))
    if fmt == "generic":
        return _load_generic(data, ignore_schema)
    return _load_sqlflow_mvp(data, ignore_schema), {}


def _load_generic(data: dict, ignore_schema: bool):
    """Returns (pairs, per-file pairs). The per-file view is only populated when
    the engine reports a location, which is what makes a per-tier F1 possible
    rather than a per-tier recall."""

    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_file: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for e in data.get("edges", []):
        tgt = node_key(e["target"]["table"], e["target"].get("column"), ignore_schema)
        file = (e.get("location") or {}).get("file")
        for s in e.get("sources", []):
            src = node_key(s["table"], s.get("column"), ignore_schema)
            pairs[(src, tgt)].add(e.get("kind", "DIRECT"))
            if file:
                by_file[file].add((src, tgt))
    return pairs, dict(by_file)


def _split_id(node_id: str, ignore_schema: bool) -> str | None:
    """``column.orders.order_amount`` -> ``ORDERS.ORDER_AMOUNT``."""

    parts = node_id.split(".")
    if parts[0] == "column" and len(parts) >= 3:
        return node_key(".".join(parts[1:-1]), parts[-1], ignore_schema)
    if parts[0] == "table" and len(parts) >= 2:
        return node_key(".".join(parts[1:]), None, ignore_schema)
    return None


def _load_sqlflow_mvp(data: dict, ignore_schema: bool):
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for rel in data.get("relationships", []):
        if rel.get("type") not in ("direct", "indirect", "dynamic_sql"):
            continue
        src = _split_id(rel.get("source", ""), ignore_schema)
        tgt = _split_id(rel.get("target", ""), ignore_schema)
        if src is None or tgt is None:
            continue
        pairs[(src, tgt)].add(rel["type"])
    return pairs


ENGINE_COARSE = {"direct": VALUE, "indirect": FILTER, "dynamic_sql": DYNAMIC}


def engine_coarse(kinds: set[str]) -> set[str]:
    out = set()
    for k in kinds:
        out.add(ENGINE_COARSE.get(k, coarse(k.upper())))
    return out


# --- metrics ------------------------------------------------------------------


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def multi_hop_score(truth: dict, engine_pairs, ignore_schema: bool,
                    min_hops: int = 2) -> tuple[int, int]:
    """How many multi-hop truth chains the engine can still reconstruct.

    A chain counts as completed if every consecutive link on it is present in
    the engine's edge set - that is what makes an end-to-end impact query work.
    """

    graph: dict[str, set[str]] = defaultdict(set)
    for e in truth["edges"]:
        if e["kind"] not in VALUE_KINDS or e["target"]["column"] is None:
            continue
        tgt = node_key(e["target"]["table"], e["target"]["column"], ignore_schema)
        for s in e["sources"]:
            src = node_key(s["table"], s["column"], ignore_schema)
            if src != tgt:
                graph[tgt].add(src)

    total = complete = 0
    for tgt, sources in graph.items():
        for mid in sources:
            for deep in graph.get(mid, ()):
                if deep == tgt:
                    continue
                total += 1
                if (mid, tgt) in engine_pairs and (deep, mid) in engine_pairs:
                    complete += 1
    return complete, total


def tier_breakdown(truth: dict, manifest: dict, engine_by_file: dict,
                   ignore_schema: bool) -> dict:
    """Per-tier precision/recall/F1, scoped to each package file."""

    tier_by_file = {p["file"]: p["tier"] for p in manifest["packages"]}
    want = truth_pairs_by_file(truth, ignore_schema)
    counts: dict[int, Counter] = defaultdict(Counter)
    for file, expected in want.items():
        tier = tier_by_file.get(file, -1)
        got = engine_by_file.get(file, set())
        counts[tier]["tp"] += len(expected & got)
        counts[tier]["fn"] += len(expected - got)
        counts[tier]["fp"] += len(got - expected)
    for file, got in engine_by_file.items():
        if file not in want:
            counts[tier_by_file.get(file, -1)]["fp"] += len(got)

    out = {}
    for tier, c in sorted(counts.items()):
        p, r, f1 = prf(c["tp"], c["fp"], c["fn"])
        out[str(tier)] = {"precision": round(p, 4), "recall": round(r, 4),
                          "f1": round(f1, 4), "expected": c["tp"] + c["fn"]}
    return out


def score(truth: dict, manifest: dict, engine_pairs, ignore_schema: bool) -> dict:
    expected = truth_pairs(truth, ignore_schema)
    tier_by_file = {p["file"]: p["tier"] for p in manifest["packages"]}

    tp = [k for k in expected if k in engine_pairs]
    fn = [k for k in expected if k not in engine_pairs]
    fp = [k for k in engine_pairs if k not in expected]

    engine_vocab = {k for kinds in engine_pairs.values() for k in kinds}
    truth_vocab = {k for slot in expected.values() for k in slot["kinds"]}
    # An engine that only emits coarse labels ("direct" / "indirect") shares no
    # vocabulary with the truth's fine-grained kinds. Reporting 0% there would
    # read as a failure when it is really a difference in granularity.
    exact_applicable = bool(engine_vocab & truth_vocab)

    kind_exact = kind_coarse = 0
    for key in tp:
        got = engine_pairs[key]
        want = expected[key]["kinds"]
        if got & want:
            kind_exact += 1
        if engine_coarse(got) & {coarse(k) for k in want}:
            kind_coarse += 1

    tier_stats: dict[int, Counter] = defaultdict(Counter)
    for key, slot in expected.items():
        hit = key in engine_pairs
        for f in slot["files"]:
            tier = tier_by_file.get(f, -1)
            tier_stats[tier]["expected"] += 1
            tier_stats[tier]["found"] += 1 if hit else 0

    p, r, f1 = prf(len(tp), len(fp), len(fn))
    hops_done, hops_total = multi_hop_score(truth, engine_pairs, ignore_schema)
    unresolved = [e for e in truth["edges"] if e["kind"] == UNRESOLVED]

    return {
        "edges": {
            "expected": len(expected), "engine": len(engine_pairs),
            "true_positive": len(tp), "false_positive": len(fp),
            "false_negative": len(fn),
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
        },
        "kind_accuracy": {
            "exact": (round(kind_exact / len(tp), 4) if tp else 0.0)
                     if exact_applicable else None,
            "coarse": round(kind_coarse / len(tp), 4) if tp else 0.0,
            "exact_applicable": exact_applicable,
        },
        "tier_recall": {
            str(tier): round(c["found"] / c["expected"], 4)
            for tier, c in sorted(tier_stats.items()) if c["expected"]
        },
        "multi_hop": {
            "chains": hops_total,
            "completed": hops_done,
            "rate": round(hops_done / hops_total, 4) if hops_total else 0.0,
        },
        "unresolved": {
            "count": len(unresolved),
            "note": "동적 SQL 구간. 정적 해석 불가 영역이므로 P/R 계산에서 제외됨.",
        },
    }


def parse_rate(manifest: dict, engine_raw: dict) -> dict | None:
    """Parse success rate, if the engine reports per-file diagnostics."""

    diags = engine_raw.get("diagnostics")
    if diags is None:
        return None
    failed = {d.get("file") for d in diags
              if str(d.get("severity", "")).lower() in ("error", "fatal")}
    failed.discard(None)
    total = len(manifest["packages"])
    return {"files": total, "failed": len(failed),
            "rate": round((total - len(failed)) / total, 4) if total else 0.0}


def main(argv: list[str] | None = None) -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(prog="synplsql.score",
                                 description="리니지 엔진 출력 채점")
    ap.add_argument("--truth", default=str(root / "out" / "lineage_truth.json"))
    ap.add_argument("--manifest", default=str(root / "out" / "manifest.json"))
    ap.add_argument("--engine", required=True, help="엔진 출력 JSON")
    ap.add_argument("--format", choices=("generic", "sqlflow-mvp"), default="generic")
    ap.add_argument("--ignore-schema", action="store_true",
                    help="스키마 접두사를 무시하고 테이블명만 비교")
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = ap.parse_args(argv)

    truth = json.loads(pathlib.Path(args.truth).read_text(encoding="utf-8"))
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    engine_path = pathlib.Path(args.engine)
    engine_pairs, engine_by_file = load_engine(engine_path, args.format,
                                               args.ignore_schema)
    engine_raw = json.loads(engine_path.read_text(encoding="utf-8"))

    result = score(truth, manifest, engine_pairs, args.ignore_schema)
    if engine_by_file:
        result["tier_breakdown"] = tier_breakdown(truth, manifest, engine_by_file,
                                                  args.ignore_schema)
    rate = parse_rate(manifest, engine_raw)
    if rate:
        result["parse_rate"] = rate

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    e = result["edges"]
    print(f"\n채점 결과  (고유 source->target 쌍: truth {e['expected']:,} / "
          f"engine {e['engine']:,})")
    print("-" * 60)
    if rate:
        print(f"  파싱 성공률       {rate['rate']:>8.1%}  "
              f"({rate['files'] - rate['failed']}/{rate['files']} 파일)")
    print(f"  엣지 Precision    {e['precision']:>8.1%}")
    print(f"  엣지 Recall       {e['recall']:>8.1%}")
    print(f"  엣지 F1           {e['f1']:>8.1%}")
    exact = result["kind_accuracy"]["exact"]
    if exact is None:
        print("  Kind 정확도(정밀)      해당 없음 (엔진이 개략 분류만 출력)")
    else:
        print(f"  Kind 정확도(정밀) {exact:>8.1%}")
    print(f"  Kind 정확도(개략) {result['kind_accuracy']['coarse']:>8.1%}")
    mh = result["multi_hop"]
    print(f"  다홉 완주율       {mh['rate']:>8.1%}  ({mh['completed']:,}/{mh['chains']:,})")
    print("-" * 60)
    if "tier_breakdown" in result:
        print(f"  Tier별  {'expected':>9}{'P':>9}{'R':>9}{'F1':>9}")
        for tier, v in result["tier_breakdown"].items():
            print(f"    Tier {tier} {v['expected']:>9,}{v['precision']:>9.1%}"
                  f"{v['recall']:>9.1%}{v['f1']:>9.1%}")
    else:
        print("  Tier별 Recall  (엔진 출력에 location 정보가 없어 재현율만 산출)")
        for tier, value in result["tier_recall"].items():
            print(f"    Tier {tier}          {value:>8.1%}")
    print("-" * 60)
    print(f"  UNRESOLVED {result['unresolved']['count']}건 - "
          f"{result['unresolved']['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
