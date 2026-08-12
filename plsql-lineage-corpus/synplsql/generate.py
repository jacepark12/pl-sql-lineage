"""CLI driver: assemble packages, render SQL, serialise the lineage truth set.

    python -m synplsql.generate --seed 20260812 --packages 200 --out out
    python -m synplsql.generate --tier 0,1 --packages 20 --lines 30000 --out out/dev
    python -m synplsql.generate --stats-only --out out
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys
from collections import Counter, defaultdict

from . import schema as S
from .core import (
    COMMON_PACKAGE,
    UNRESOLVED,
    VALUE_KINDS,
    Package,
    assign_ids,
    extract_package_edges,
    render_package,
)
from .scenarios import Budget, Gen, build_package, sample_package_lines

CORPUS_VERSION = "1.0"
ROOT = pathlib.Path(__file__).resolve().parents[1]


# --- generation ---------------------------------------------------------------


def generate(seed: int, packages: int, lines: int, tiers: list[int],
             profile: dict) -> tuple[list[Package], Budget, Gen]:
    rng = random.Random(seed)
    profile = json.loads(json.dumps(profile))
    profile["scale"]["packages"] = packages
    profile["scale"]["lines"] = lines
    if lines < profile["scale"]["max_package_lines"] * 2:
        profile["scale"]["max_package_lines"] = max(400, lines // 4)

    budget = Budget(profile, lines)
    g = Gen(rng=rng, budget=budget, profile=profile)

    sizes = sample_package_lines(rng, profile, packages)
    assigned = allocate_tiers(tiers, profile["tier_mix"], sizes)

    built: list[Package] = []
    for i, size in enumerate(sizes):
        tier = assigned[i]
        pkg = build_package(g, i + 1, tier, size)
        assign_ids(pkg)
        built.append(pkg)
    return built, budget, g


def allocate_tiers(tiers: list[int], mix: dict, sizes: list[int]) -> list[int]:
    """Assign a tier to each package so the mix holds *by line count*.

    Two failure modes this avoids. Drawing each package's tier independently
    leaves rare tiers to chance - a 30-package run can easily contain no Tier 3
    package at all, and then every Tier 3 construct silently vanishes from the
    corpus. And allocating by package count lets a tier land on nothing but tiny
    packages, so its share of the corpus is far below the declared mix. Filling
    largest-package-first into whichever tier is furthest behind its line quota
    fixes both.
    """

    weights = {t: max(0.0, mix.get(str(t), 0.0)) for t in tiers}
    if sum(weights.values()) <= 0:
        weights = {t: 1.0 for t in tiers}
    total_w = sum(weights.values())
    total_lines = sum(sizes) or 1
    target = {t: total_lines * w / total_w for t, w in weights.items()}
    got = {t: 0 for t in tiers}
    eligible = [t for t in tiers if weights[t] > 0] or list(tiers)

    assigned = [eligible[0]] * len(sizes)
    for i in sorted(range(len(sizes)), key=lambda i: -sizes[i]):
        t = max(eligible, key=lambda t: target[t] - got[t])
        assigned[i] = t
        got[t] += sizes[i]
    return assigned


# --- serialisation ------------------------------------------------------------


def anchor_line(anchors: dict[str, int], key: str | None) -> int:
    """Resolve an edge anchor, falling back to the statement's first line."""

    if not key:
        return 0
    line = anchors.get(key)
    if line:
        return line
    return anchors.get(key.split(":", 1)[0] + ":stmt", 0)


def edge_json(pkg: Package, sub_name: str, edge, file_rel: str, line: int) -> dict:
    def split(fq: str, column: str | None) -> dict:
        return {"table": fq, "column": column}

    out = {
        "target": split(edge.target_table, edge.target_column),
        "sources": [{"table": t, "column": c} for t, c in edge.sources],
        "kind": edge.kind,
        "transform": " ".join(edge.transform.split()),
        "hops": edge.hops,
        "location": {
            "file": file_rel,
            "package": pkg.name,
            "procedure": sub_name,
            "line": line,
        },
    }
    if edge.via:
        out["via"] = edge.via
    if edge.note:
        out["note"] = edge.note
    return out


def write_corpus(out_dir: pathlib.Path, packages: list[Package], budget: Budget,
                 seed: int, tiers: list[int], profile: dict) -> dict:
    pkg_dir = out_dir / "packages"
    ddl_dir = out_dir / "ddl"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    ddl_dir.mkdir(parents=True, exist_ok=True)

    (ddl_dir / "catalog.sql").write_text(S.render_ddl(), encoding="utf-8")
    common_rel = "packages/SYNWMS.PKG_COMMON.sql"
    (out_dir / common_rel).write_text(COMMON_PACKAGE, encoding="utf-8")
    common_lines = len(COMMON_PACKAGE.split("\n"))

    all_edges: list[dict] = []
    all_cursors: list[dict] = []
    manifest_pkgs: list[dict] = [{
        "file": common_rel,
        "package": "SYNWMS.PKG_COMMON",
        "tier": 0,
        "lines": common_lines,
        "subprograms": 2,
        "procedures": 1,
        "functions": 1,
        "scenarios": ["common_utility"],
    }]
    total_lines = common_lines
    kind_counts: Counter[str] = Counter()

    for pkg in packages:
        text, anchors = render_package(pkg)
        rel = f"packages/{pkg.fq}.sql"
        # render_package already terminates with a newline; adding another
        # would put the manifest line count one ahead of the file.
        (out_dir / rel).write_text(text, encoding="utf-8")
        n_lines = len(text.split("\n"))
        total_lines += n_lines

        edges, cursors = extract_package_edges(pkg, S.CATALOG)
        for sub_name, e in edges:
            line = anchor_line(anchors, e.anchor)
            all_edges.append(edge_json(pkg, sub_name, e, rel, line))
            kind_counts[e.kind] += 1
        for sub_name, rc in cursors:
            all_cursors.append({
                "out_param": rc.out_param,
                "columns": [
                    {"name": name,
                     "sources": [{"table": t, "column": c} for t, c in srcs],
                     "kind": kind}
                    for name, srcs, kind in rc.columns
                ],
                "location": {
                    "file": rel, "package": pkg.name, "procedure": sub_name,
                    "line": anchor_line(anchors, rc.anchor),
                },
            })

        manifest_pkgs.append({
            "file": rel,
            "package": pkg.fq,
            "tier": pkg.tier,
            "lines": n_lines,
            "subprograms": len(pkg.subprograms),
            "procedures": sum(1 for s in pkg.subprograms if s.kind == "PROCEDURE"),
            "functions": sum(1 for s in pkg.subprograms if s.kind == "FUNCTION"),
            "scenarios": sorted(set(pkg.scenarios)),
        })

    truth = {
        "corpus_version": CORPUS_VERSION,
        "seed": seed,
        "tiers": tiers,
        "edge_kinds": list(VALUE_KINDS) + ["INDIRECT_FILTER", UNRESOLVED],
        "edges": all_edges,
        "ref_cursors": all_cursors,
    }
    (out_dir / "lineage_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")

    chains = longest_chains(all_edges)
    manifest = {
        "corpus_version": CORPUS_VERSION,
        "seed": seed,
        "tiers": tiers,
        "totals": {
            "packages": len(manifest_pkgs),
            "lines": total_lines,
            "avg_package_lines": round(total_lines / max(1, len(packages)), 1),
            "max_package_lines": max((p["lines"] for p in manifest_pkgs), default=0),
            "procedures": sum(p["procedures"] for p in manifest_pkgs),
            "functions": sum(p["functions"] for p in manifest_pkgs),
            "edges": len(all_edges),
            "ref_cursor_projections": len(all_cursors),
        },
        "edge_kinds": dict(sorted(kind_counts.items())),
        "tier_distribution": dict(sorted(Counter(p["tier"] for p in manifest_pkgs).items())),
        "longest_chain": chains,
        "packages": manifest_pkgs,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def longest_chains(edges: list[dict], limit: int = 5) -> list[dict]:
    """Longest value-carrying column chains, found by DFS over the truth edges."""

    graph: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for e in edges:
        if e["kind"] not in VALUE_KINDS:
            continue
        tgt = e["target"]
        if tgt["column"] is None:
            continue
        tkey = (tgt["table"], tgt["column"])
        for s in e["sources"]:
            skey = (s["table"], s["column"])
            if skey != tkey:
                graph[tkey].add(skey)

    # The column graph contains cycles (STK_ONHAND feeds STK_TRX feeds
    # STK_ONHAND again), so the longest simple path has to be searched with an
    # explicit visited set per path rather than memoised per node.
    max_depth = 16
    step_budget = 400_000
    steps = 0

    def walk(node: tuple[str, str], seen: frozenset) -> list[tuple[str, str]]:
        nonlocal steps
        longest = [node]
        if len(seen) >= max_depth or steps >= step_budget:
            return longest
        for nxt in sorted(graph.get(node, ())):
            if nxt in seen:
                continue
            steps += 1
            if steps >= step_budget:
                break
            path = [node] + walk(nxt, seen | {nxt})
            if len(path) > len(longest):
                longest = path
        return longest

    sys.setrecursionlimit(10000)
    results = [walk(node, frozenset({node})) for node in sorted(graph)]
    results.sort(key=lambda p: (len(p), p), reverse=True)

    out = []
    seen_sig = set()
    for path in results:
        sig = (path[0], path[-1], len(path))
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        out.append({
            "hops": len(path) - 1,
            "path": [f"{t}.{c}" for t, c in path],
        })
        if len(out) >= limit:
            break
    return out


# --- profile conformance ------------------------------------------------------


# Constructs measured against the raw file; everything else is measured against
# code with line comments stripped. Without this a comment that merely mentions
# a construct ("-- 대량 조회 (BULK COLLECT)") is counted as an occurrence of it,
# which silently doubles several rates.
RAW_TEXT_CONSTRUCTS = frozenset({"HANGUL_LINE"})

_LINE_COMMENT = re.compile(r"--[^\n]*")


def strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", text)


def measure(out_dir: pathlib.Path, profile: dict) -> dict:
    files = sorted((out_dir / "packages").glob("*.sql"))
    total_lines = 0
    counts: Counter[str] = Counter()
    compiled = {name: re.compile(cfg["pattern"])
                for name, cfg in profile["constructs"].items()}
    for f in files:
        text = f.read_text(encoding="utf-8")
        code = strip_comments(text)
        total_lines += text.count("\n") + 1
        for name, rx in compiled.items():
            counts[name] += len(rx.findall(text if name in RAW_TEXT_CONSTRUCTS else code))

    manifest_path = out_dir / "manifest.json"
    scale_rows = []
    if manifest_path.exists():
        totals = json.loads(manifest_path.read_text(encoding="utf-8"))["totals"]
        want = profile["scale"]
        n_pkg = max(1, totals["packages"])
        for label, got, target in (
            ("packages", totals["packages"], want["packages"]),
            ("lines", totals["lines"], want["lines"]),
            ("avg_package_lines", totals["avg_package_lines"], want["avg_package_lines"]),
            ("max_package_lines", totals["max_package_lines"], want["max_package_lines"]),
            ("procedures_per_package", round(totals["procedures"] / n_pkg, 2),
             want["procedures_per_package"]),
            ("functions_per_package", round(totals["functions"] / n_pkg, 2),
             want["functions_per_package"]),
        ):
            ok = abs(got - target) <= max(1.0, target * profile["tolerance"]["default_rel"])
            scale_rows.append({"metric": label, "target": target, "actual": got,
                               "within_tolerance": ok})

    tol = profile["tolerance"]
    rows = []
    for name, cfg in profile["constructs"].items():
        want = cfg["per_1k_lines"] * total_lines / 1000.0
        got = counts[name]
        delta = got - want
        ok = abs(delta) <= max(tol["min_abs"], want * tol["default_rel"])
        rows.append({
            "construct": name,
            "target_rate_per_1k": cfg["per_1k_lines"],
            "actual_rate_per_1k": round(got / max(1.0, total_lines / 1000.0), 3),
            "target_count": round(want, 1),
            "actual_count": got,
            "within_tolerance": ok,
        })
    return {"files": len(files), "lines": total_lines, "constructs": rows,
            "scale": scale_rows}


def print_stats(stats: dict) -> bool:
    ok_all = True
    if stats.get("scale"):
        print("\n규모 프로파일 대조")
        print("-" * 78)
        print(f"{'metric':<26}{'target':>14}{'actual':>14}   판정")
        print("-" * 78)
        for r in stats["scale"]:
            ok_all = ok_all and r["within_tolerance"]
            print(f"{r['metric']:<26}{r['target']:>14,.2f}{r['actual']:>14,.2f}"
                  f"   {'OK ' if r['within_tolerance'] else 'OUT'}")
        print("-" * 78)

    print(f"\n구문 프로파일 대조  (파일 {stats['files']}개 / {stats['lines']:,} 라인)")
    print("-" * 78)
    print(f"{'construct':<18}{'target/1K':>11}{'actual/1K':>11}{'target':>10}{'actual':>9}   판정")
    print("-" * 78)
    for r in stats["constructs"]:
        mark = "OK " if r["within_tolerance"] else "OUT"
        ok_all = ok_all and r["within_tolerance"]
        print(f"{r['construct']:<18}{r['target_rate_per_1k']:>11.2f}"
              f"{r['actual_rate_per_1k']:>11.2f}{r['target_count']:>10.0f}"
              f"{r['actual_count']:>9}   {mark}")
    print("-" * 78)
    return ok_all


# --- entry point --------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="synplsql.generate",
                                 description="합성 PL/SQL 코퍼스 생성기")
    ap.add_argument("--seed", type=int, default=20260812)
    ap.add_argument("--packages", type=int, default=None)
    ap.add_argument("--lines", type=int, default=None)
    ap.add_argument("--tier", default="0,1,2,3",
                    help="생성할 난이도 티어 목록 (예: 0,1)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--profile", default=str(ROOT / "profile.json"))
    ap.add_argument("--stats", action="store_true", help="생성 후 프로파일 대조 출력")
    ap.add_argument("--stats-only", action="store_true",
                    help="생성하지 않고 기존 출력만 대조")
    ap.add_argument("--strict", action="store_true",
                    help="프로파일 허용오차를 벗어나면 종료코드 1")
    args = ap.parse_args(argv)

    profile = json.loads(pathlib.Path(args.profile).read_text(encoding="utf-8"))
    out_dir = pathlib.Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    if args.stats_only:
        stats = measure(out_dir, profile)
        ok = print_stats(stats)
        return 0 if ok or not args.strict else 1

    packages = args.packages or profile["scale"]["packages"]
    lines = args.lines or profile["scale"]["lines"]
    tiers = sorted({int(t) for t in args.tier.split(",") if t.strip() != ""})

    built, budget, _ = generate(args.seed, packages, lines, tiers, profile)
    manifest = write_corpus(out_dir, built, budget, args.seed, tiers, profile)

    t = manifest["totals"]
    print(f"코퍼스 생성 완료: {out_dir}")
    print(f"  패키지    {t['packages']:>8,}  (평균 {t['avg_package_lines']:,.0f} 라인 / "
          f"최대 {t['max_package_lines']:,} 라인)")
    print(f"  총 라인   {t['lines']:>8,}")
    print(f"  프로시저  {t['procedures']:>8,}   함수 {t['functions']:,}")
    print(f"  리니지 엣지 {t['edges']:>6,}   REF CURSOR 투영 {t['ref_cursor_projections']:,}")
    print(f"  엣지 종류 {manifest['edge_kinds']}")
    if manifest["longest_chain"]:
        top = manifest["longest_chain"][0]
        print(f"  최장 체인 {top['hops']}홉: {' <- '.join(top['path'])}")

    ok = True
    if args.stats:
        ok = print_stats(measure(out_dir, profile))
    return 0 if ok or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
