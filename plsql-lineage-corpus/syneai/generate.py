"""CLI driver for the synthetic EAI corpus.

    python3 -m syneai.generate --out out/eai --stats
    python3 -m syneai.generate --out out/eai --merge out      # join both corpora

The merge step is the point of the whole exercise: on its own the EAI truth
describes a source system loading an interface table, and the PL/SQL truth
describes that interface table feeding a report. Joined at SYNIF, one chain runs
from the source system all the way to the report, which is the question people
actually ask.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
from collections import Counter

from synplsql import schema as S
from synplsql.core import SEVERED, UNRESOLVED, VALUE_KINDS
from synplsql.generate import longest_chains

from . import adapters as A
from . import docs as D
from . import nodes as N
from .flow import render_flow
from .interfaces import build_interface

CORPUS_VERSION = "1.0"
ROOT = pathlib.Path(__file__).resolve().parents[1]


# --- generation ---------------------------------------------------------------


def allocate_tiers(tiers: list[int], mix: dict, count: int) -> list[int]:
    weights = {t: max(0.0, mix.get(str(t), 0.0)) for t in tiers}
    if sum(weights.values()) <= 0:
        weights = {t: 1.0 for t in tiers}
    total = sum(weights.values())
    quota = {t: int(count * w / total) for t, w in weights.items()}
    assigned = [t for t, n in quota.items() for _ in range(n)]
    order = sorted(tiers, key=lambda t: -weights[t])
    i = 0
    while len(assigned) < count:
        assigned.append(order[i % len(order)])
        i += 1
    return assigned[:count]


def generate(seed: int, count: int, tiers: list[int], profile: dict):
    rng = random.Random(seed)
    assigned = allocate_tiers(tiers, profile["tier_mix"], count)
    specs = S.EAI_INTERFACES
    built = []
    for i in range(count):
        spec = specs[i % len(specs)]
        built.append(build_interface(rng, spec, i + 1, assigned[i], profile))
    return built


# --- artifact writing ---------------------------------------------------------


def write_interface(out_dir: pathlib.Path, iface) -> dict[str, str]:
    """Write one interface package. Returns artifact path -> content."""

    base = out_dir / iface.name
    files: dict[str, str] = {
        "node.idf": N.render_node_idf(iface.name, iface.ns, iface.title, iface.tier),
    }
    for doc in (iface.src_doc, iface.tgt_doc, iface.stg_doc):
        files[f"docs/{doc.name}/node.ndf"] = D.render_node_ndf(doc)
    for adapter in iface.adapters.values():
        files[f"adpt/{adapter.name}/node.ndf"] = A.render_node_ndf(
            adapter, f"{iface.ns}.adpt")
    for svc in iface.services:
        files[f"srvc/{svc.name}/flow.xml"] = render_flow(svc)
        files[f"srvc/{svc.name}/node.ndf"] = N.render_service_ndf(
            svc, f"{iface.ns}.srvc")

    for rel, content in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return files


def edge_json(iface, edge) -> dict:
    anchor = edge.anchor or ""
    service, _, rest = anchor.partition("/")
    step_path, _, adapter_name = rest.partition("#")
    artifact = f"srvc/{service}/flow.xml" if service else ""
    adapter = f"adpt/{adapter_name}" if adapter_name else None
    out = {
        "target": {"table": edge.target_table, "column": edge.target_column},
        "sources": [{"table": t, "column": c} for t, c in edge.sources],
        "kind": edge.kind,
        "transform": " ".join(edge.transform.split()),
        "hops": edge.hops,
        "location": {
            "layer": "eai",
            "interface": iface.name,
            "artifact": artifact,
            "step_path": step_path,
        },
    }
    if adapter:
        out["location"]["adapter"] = adapter
    if edge.via:
        out["via"] = edge.via
    if edge.note:
        out["note"] = edge.note
    return out


def write_corpus(out_dir: pathlib.Path, built: list, seed: int,
                 tiers: list[int]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_edges: list[dict] = []
    manifest_ifaces: list[dict] = []
    kind_counts: Counter[str] = Counter()

    for iface in built:
        files = write_interface(out_dir, iface)
        for edge in iface.edges:
            all_edges.append(edge_json(iface, edge))
            kind_counts[edge.kind] += 1
        manifest_ifaces.append({
            "interface": iface.name,
            "tier": iface.tier,
            "title": iface.title,
            "source": iface.spec.source,
            "target": iface.spec.target,
            "write_op": iface.spec.write_op,
            "artifacts": sorted(files),
            "adapters": sorted(iface.adapters),
            "severed_fields": iface.severed_fields,
            "mapcopy_depth": {str(d): n for d, n in sorted(iface.depth_counts.items())},
            "blob_bytes": sum(len(a.blob()) for a in iface.adapters.values()),
        })

    truth = {
        "corpus_version": CORPUS_VERSION,
        "layer": "eai",
        "seed": seed,
        "tiers": tiers,
        "format_note": "어댑터 메타데이터 인코딩은 docs/WM-VALUES-FORMAT.md 참고. "
                       "실제 webMethods 바이트 호환성은 미검증.",
        "edges": all_edges,
    }
    (out_dir / "lineage_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "corpus_version": CORPUS_VERSION,
        "layer": "eai",
        "seed": seed,
        "tiers": tiers,
        "totals": {
            "interfaces": len(built),
            "artifacts": sum(len(i["artifacts"]) for i in manifest_ifaces),
            "adapters": sum(len(i["adapters"]) for i in manifest_ifaces),
            "edges": len(all_edges),
            "severed_edges": kind_counts.get(SEVERED, 0),
        },
        "edge_kinds": dict(sorted(kind_counts.items())),
        "tier_distribution": dict(sorted(Counter(i["tier"] for i in manifest_ifaces).items())),
        "interfaces": manifest_ifaces,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


# --- profile conformance ------------------------------------------------------


def measure(out_dir: pathlib.Path, profile: dict) -> dict:
    flows = sorted(out_dir.glob("*/srvc/*/flow.xml"))
    counts: Counter[str] = Counter()
    depths: Counter[int] = Counter()
    compiled = {k: re.compile(v) for k, v in profile["patterns"].items()}
    from_re = re.compile(r'<MAPCOPY\s+FROM="([^"]+)"')

    for f in flows:
        text = f.read_text(encoding="utf-8")
        for name, rx in compiled.items():
            counts[name] += len(rx.findall(text))
        for path in from_re.findall(text):
            depths[len([s for s in path.split("/") if s])] += 1

    total_copy = max(1, counts["MAPCOPY"])
    n_services = max(1, len(flows))
    tol = profile["tolerance"]
    rows = []
    # Field-proportional constructs: held to a ratio against MAPCOPY.
    for name, want_ratio in profile["step_ratio_to_mapcopy"].items():
        want = want_ratio * total_copy
        got = counts[name]
        ok = abs(got - want) <= max(tol["min_abs"], want * tol["default_rel"])
        rows.append({"metric": name, "basis": "/MAPCOPY", "target_ratio": want_ratio,
                     "actual_ratio": round(got / total_copy, 3),
                     "target": round(want, 1), "actual": got,
                     "within_tolerance": ok})
    # Structural constructs: they exist per step block, so they scale with the
    # number of FLOW services, not with how many fields an interface maps.
    for name, want_rate in profile["step_per_service"].items():
        want = want_rate * n_services
        got = counts[name]
        ok = abs(got - want) <= max(tol["min_abs"], want * tol["default_rel"])
        rows.append({"metric": name, "basis": "/service", "target_ratio": want_rate,
                     "actual_ratio": round(got / n_services, 3),
                     "target": round(want, 1), "actual": got,
                     "within_tolerance": ok})

    depth_total = max(1, sum(depths.values()))
    depth_rows = []
    for key, want_share in profile["mapcopy_depth"].items():
        d = int(key)
        want = want_share * depth_total
        got = depths[d]
        ok = abs(got - want) <= max(tol["min_abs"], want * tol["default_rel"])
        depth_rows.append({"metric": f"depth {d}", "basis": "/MAPCOPY",
                           "target_ratio": want_share,
                           "actual_ratio": round(got / depth_total, 3),
                           "target": round(want, 1), "actual": got,
                           "within_tolerance": ok})

    return {"flow_files": len(flows), "mapcopy": counts["MAPCOPY"],
            "steps": rows, "depths": depth_rows}


def print_stats(stats: dict) -> bool:
    ok_all = True
    print(f"\nFLOW 구문 프로파일 대조  (flow.xml {stats['flow_files']}개 / "
          f"MAPCOPY {stats['mapcopy']:,}개)")
    print("-" * 76)
    print(f"{'metric':<12}{'기준':>10}{'target':>10}{'actual':>10}"
          f"{'target 수':>11}{'actual 수':>10}  판정")
    print("-" * 76)
    for row in stats["steps"] + [None] + stats["depths"]:
        if row is None:
            print("-" * 76)
            continue
        ok_all = ok_all and row["within_tolerance"]
        print(f"{row['metric']:<12}{row.get('basis', ''):>10}"
              f"{row['target_ratio']:>10.3f}{row['actual_ratio']:>10.3f}"
              f"{row['target']:>11.0f}{row['actual']:>10}"
              f"  {'OK ' if row['within_tolerance'] else 'OUT'}")
    print("-" * 76)
    return ok_all


# --- merge with the PL/SQL corpus ---------------------------------------------


def merge(eai_dir: pathlib.Path, plsql_dir: pathlib.Path) -> dict | None:
    """Join both truth files and report the end-to-end chains."""

    sql_truth = plsql_dir / "lineage_truth.json"
    if not sql_truth.exists():
        return None
    sql = json.loads(sql_truth.read_text(encoding="utf-8"))
    eai = json.loads((eai_dir / "lineage_truth.json").read_text(encoding="utf-8"))

    edges = list(eai["edges"]) + list(sql["edges"])
    chains = longest_chains(edges, limit=8)
    cross = [c for c in chains
             if any(node.startswith("SYNSRC.") for node in c["path"])
             and any(node.startswith("SYNWMS.RPT_") or node.startswith("SYNARC.")
                     for node in c["path"])]

    merged = {
        "corpus_version": CORPUS_VERSION,
        "layer": "merged",
        "seeds": {"eai": eai["seed"], "plsql": sql["seed"]},
        "edge_counts": {"eai": len(eai["edges"]), "plsql": len(sql["edges"]),
                        "total": len(edges)},
        "longest_chain": chains,
        "cross_layer_chains": cross[:5],
        "edges": edges,
    }
    (plsql_dir / "lineage_truth_merged.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


# --- entry point --------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="syneai.generate",
                                 description="합성 EAI(webMethods) 코퍼스 생성기")
    ap.add_argument("--seed", type=int, default=20260812)
    ap.add_argument("--interfaces", type=int, default=None)
    ap.add_argument("--tier", default="0,1,2,3")
    ap.add_argument("--out", default="out/eai")
    ap.add_argument("--profile", default=str(ROOT / "profile-eai.json"))
    ap.add_argument("--merge", metavar="PLSQL_OUT",
                    help="PL/SQL 코퍼스 출력 디렉터리와 정답셋 병합")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--stats-only", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    profile = json.loads(pathlib.Path(args.profile).read_text(encoding="utf-8"))
    out_dir = pathlib.Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    if args.stats_only:
        return 0 if print_stats(measure(out_dir, profile)) or not args.strict else 1

    count = args.interfaces or profile["scale"]["interfaces"]
    tiers = sorted({int(t) for t in args.tier.split(",") if t.strip()})
    built = generate(args.seed, count, tiers, profile)
    manifest = write_corpus(out_dir, built, args.seed, tiers)

    t = manifest["totals"]
    print(f"EAI 코퍼스 생성 완료: {out_dir}")
    print(f"  인터페이스  {t['interfaces']:>6,}   아티팩트 {t['artifacts']:,}"
          f"   어댑터 {t['adapters']:,}")
    print(f"  리니지 엣지 {t['edges']:>6,}   그중 SEVERED {t['severed_edges']:,}")
    print(f"  엣지 종류 {manifest['edge_kinds']}")

    ok = True
    if args.stats:
        ok = print_stats(measure(out_dir, profile))

    if args.merge:
        plsql_dir = pathlib.Path(args.merge)
        if not plsql_dir.is_absolute():
            plsql_dir = ROOT / plsql_dir
        merged = merge(out_dir, plsql_dir)
        if merged is None:
            print(f"\n병합 건너뜀: {plsql_dir}/lineage_truth.json 없음")
        else:
            c = merged["edge_counts"]
            print(f"\n통합 정답셋: {plsql_dir / 'lineage_truth_merged.json'}")
            print(f"  엣지  EAI {c['eai']:,} + PL/SQL {c['plsql']:,} = {c['total']:,}")
            if merged["cross_layer_chains"]:
                top = merged["cross_layer_chains"][0]
                print(f"  전 구간 체인 {top['hops']}홉:")
                print("    " + "\n     <- ".join(top["path"]))
            else:
                print("  경고: 원천 시스템에서 리포트까지 이어지는 체인을 찾지 못했습니다.")
                ok = False
    return 0 if ok or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
