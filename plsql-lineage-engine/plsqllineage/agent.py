"""Project engine ``edges`` JSON onto a budgeted text subgraph for agents.

The viewer contract lives in ``export.py``. This module does not re-analyze SQL
and does not dump ``graph.json`` into a prompt: it resolves an FQN, walks a
directed column graph, and renders COL / EDGE / DIAG lines under a token budget.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable

from plsqllineage.export import table_spelling

VALUE_KINDS = frozenset({
    "DIRECT", "TRANSFORM", "AGGREGATE", "ANALYTIC",
    "VIA_VARIABLE", "VIA_CTE", "VIA_PIPELINE",
})
FILTER_KINDS = frozenset({"FILTER", "INDIRECT_FILTER", "INDIRECT"})
UNRESOLVED_KINDS = frozenset({
    "UNRESOLVED", "DYNAMIC", "DYNAMIC_SQL", "EXECUTE_IMMEDIATE",
})
SEED_ALWAYS_KINDS = UNRESOLVED_KINDS | frozenset({"SEVERED"})

KIND_ALIAS = {
    "INDIRECT_FILTER": "FILTER",
    "INDIRECT": "FILTER",
    "DYNAMIC": "UNRESOLVED",
    "DYNAMIC_SQL": "UNRESOLVED",
    "EXECUTE_IMMEDIATE": "UNRESOLVED",
}

CHARS_PER_TOKEN = 3
DEFAULT_DEPTH = 2
DEFAULT_BUDGET = 2000
MAX_EXPLAIN_EDGES = 20
MAX_CANDIDATES = 8


@dataclass(frozen=True)
class Assertion:
    kind: str
    sources: tuple[str, ...]
    target: str
    expression: str
    method: str
    location: dict
    hops: int | None = None

    @property
    def span(self) -> str:
        return span_text(self.location)

    @property
    def identity(self) -> tuple:
        loc = self.location
        return (
            self.kind,
            self.sources,
            self.target,
            self.expression,
            loc.get("file"),
            loc.get("line"),
        )


@dataclass
class LineageGraph:
    display: dict[str, str]  # upper key -> display FQN
    by_target: dict[str, list[Assertion]] = field(
        default_factory=lambda: defaultdict(list))
    by_source: dict[str, list[Assertion]] = field(
        default_factory=lambda: defaultdict(list))
    diagnostics: list[dict] = field(default_factory=list)

    @property
    def nodes(self) -> Iterable[str]:
        return self.display.keys()


def span_text(location: object) -> str:
    if not location:
        return ""
    if isinstance(location, str):
        return location
    if not isinstance(location, dict):
        return str(location)
    file = str(location.get("file") or "")
    line = location.get("line")
    span = file
    if line is not None and line != "":
        span = f"{file}:{line}" if file else str(line)
    pkg = str(location.get("package") or "").strip()
    routine = str(
        location.get("function") or location.get("procedure") or "").strip()
    qualifier = ".".join(p for p in (pkg, routine) if p)
    if qualifier:
        span = f"{span} {qualifier}".strip()
    return span


def column_fqn(ref: dict) -> str | None:
    table = table_spelling(ref)
    if not table:
        return None
    column = ref.get("column")
    if column is None or str(column).strip() == "":
        return f"{table}.*"
    return f"{table}.{str(column).strip()}"


def _norm_kind(raw: str | None) -> str:
    folded = (raw or "DIRECT").strip().upper()
    return KIND_ALIAS.get(folded, folded)


def parse_kinds(spec: str | None) -> set[str]:
    """Parse ``--kind`` into a set of canonical kind labels.

    ``value`` (default) is the value-carrying kinds. ``all`` is every kind the
    engine emits. Comma-separated labels union. FILTER/UNRESOLVED aliases fold
    to the canonical names used on assertions.
    """
    text = (spec or "value").strip()
    if not text:
        text = "value"
    out: set[str] = set()
    for part in text.split(","):
        token = part.strip().upper()
        if not token:
            continue
        if token in {"VALUE", "VALUES"}:
            out |= set(VALUE_KINDS)
            continue
        if token == "ALL":
            return set(VALUE_KINDS) | set(FILTER_KINDS) | set(UNRESOLVED_KINDS) | {
                "CONSTANT", "SEVERED", "CALL",
            }
        if token in FILTER_KINDS or token == "FILTER":
            out.add("FILTER")
            continue
        if token in UNRESOLVED_KINDS:
            out.add("UNRESOLVED")
            continue
        out.add(KIND_ALIAS.get(token, token))
    return out or set(VALUE_KINDS)


def load_graph(data: dict) -> LineageGraph:
    graph = LineageGraph(display={})
    for edge in data.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        target = edge.get("target")
        if not isinstance(target, dict):
            continue
        target_fqn = column_fqn(target)
        if not target_fqn:
            continue
        sources: list[str] = []
        for source in edge.get("sources") or []:
            if not isinstance(source, dict):
                continue
            sfqn = column_fqn(source)
            if sfqn:
                sources.append(sfqn)
        loc = edge.get("location") or {}
        if not isinstance(loc, dict):
            loc = {}
        assertion = Assertion(
            kind=_norm_kind(edge.get("kind")),
            sources=tuple(sources),
            target=target_fqn,
            expression=str(edge.get("transform") or edge.get("expression") or ""),
            method=str(edge.get("method") or "static-parse"),
            location=loc,
            hops=edge.get("hops"),
        )
        _remember(graph, target_fqn)
        for src in sources:
            _remember(graph, src)
            graph.by_source[_key(src)].append(assertion)
        graph.by_target[_key(target_fqn)].append(assertion)
    for item in data.get("diagnostics") or []:
        if isinstance(item, dict):
            graph.diagnostics.append(item)
    return graph


def _key(fqn: str) -> str:
    return fqn.upper()


def _remember(graph: LineageGraph, fqn: str) -> None:
    graph.display.setdefault(_key(fqn), fqn)


def _display(graph: LineageGraph, fqn: str) -> str:
    return graph.display.get(_key(fqn), fqn)


def resolve_seeds(graph: LineageGraph, query: str) -> tuple[list[str], str]:
    """Return (matches, status) where status is ok / ambiguous / missing."""
    needle = (query or "").strip()
    if not needle:
        return [], "missing"
    q = needle.upper().lstrip(".")
    nodes = list(graph.display.values())
    exact = [n for n in nodes if _key(n) == q]
    if exact:
        return exact, "ok"
    suffix = [n for n in nodes if _key(n) == q or _key(n).endswith("." + q)]
    if len(suffix) == 1:
        return suffix, "ok"
    if len(suffix) > 1:
        return sorted(suffix, key=str.upper), "ambiguous"
    return [], "missing"


def suggest_candidates(graph: LineageGraph, query: str) -> list[str]:
    q = (query or "").strip().upper().lstrip(".")
    if not q:
        return []
    scored: list[tuple[int, str]] = []
    for fqn in graph.display.values():
        key = _key(fqn)
        last = key.rsplit(".", 1)[-1]
        if last == q or key.endswith("." + q):
            scored.append((0, fqn))
        elif last.startswith(q) or q in key:
            scored.append((1, fqn))
    scored.sort(key=lambda item: (item[0], item[1].upper()))
    out: list[str] = []
    seen: set[str] = set()
    for _, fqn in scored:
        k = _key(fqn)
        if k in seen:
            continue
        seen.add(k)
        out.append(fqn)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def _table_star(fqn: str) -> str | None:
    parts = fqn.rsplit(".", 1)
    if len(parts) != 2:
        return None
    table, col = parts
    if col == "*":
        return None
    return f"{table}.*"


def _kind_allowed(kind: str, kinds: set[str], *, seed_incident: bool) -> bool:
    if kind in kinds:
        return True
    if seed_incident and kind in SEED_ALWAYS_KINDS:
        return True
    return False


def traverse(
    graph: LineageGraph,
    seeds: list[str],
    *,
    depth: int,
    kinds: set[str],
    downstream: bool = False,
) -> tuple[list[str], list[Assertion]]:
    """Walk ``depth`` hops from seeds. Default direction is upstream (sources)."""
    depth = max(0, depth)
    seed_keys = {_key(s) for s in seeds}
    extra_seeds: list[str] = []
    if "FILTER" in kinds:
        for seed in seeds:
            star = _table_star(_display(graph, seed))
            if star and _key(star) in graph.display:
                extra_seeds.append(_display(graph, star))
    start = list(dict.fromkeys(seeds + extra_seeds))
    ordered: list[str] = []
    seen_nodes: set[str] = set()
    for s in start:
        k = _key(s)
        if k not in seen_nodes:
            seen_nodes.add(k)
            ordered.append(_display(graph, s))

    assertions: list[Assertion] = []
    seen_a: set[tuple] = set()
    frontier = list(start)
    for hop in range(depth):
        nxt: list[str] = []
        for node in frontier:
            bucket = graph.by_source if downstream else graph.by_target
            for assertion in bucket.get(_key(node), []):
                seed_incident = _key(node) in seed_keys and hop == 0
                if not _kind_allowed(assertion.kind, kinds, seed_incident=seed_incident):
                    continue
                ident = assertion.identity
                if ident not in seen_a:
                    seen_a.add(ident)
                    assertions.append(assertion)
                neighbors = (
                    [assertion.target] if downstream else list(assertion.sources)
                )
                for neigh in neighbors:
                    nk = _key(neigh)
                    if nk in seen_nodes:
                        continue
                    seen_nodes.add(nk)
                    ordered.append(_display(graph, neigh))
                    nxt.append(neigh)
        frontier = nxt
    return ordered, assertions


def _cut_to_budget(lines: list[str], token_budget: int, *,
                   seed_line_count: int, total_cols: int,
                   narrow_hint: str) -> str:
    body = "\n".join(lines)
    char_budget = max(1, token_budget) * CHARS_PER_TOKEN
    if len(body) <= char_budget:
        return body
    cut_at = body[:char_budget].rfind("\n")
    cut_at = cut_at if cut_at > 0 else char_budget
    seed_end = 0
    if seed_line_count:
        seed_end = sum(len(lines[i]) + 1 for i in range(min(seed_line_count, len(lines)))) - 1
        cut_at = max(cut_at, min(seed_end, len(body)))
    kept = body[:cut_at]
    total_col_lines = sum(1 for line in lines if line.startswith("COL "))
    shown_col_lines = sum(1 for line in kept.splitlines() if line.startswith("COL "))
    cut_count = max(0, total_col_lines - shown_col_lines)
    if cut_count == 0:
        est = len(body) // CHARS_PER_TOKEN
        return (
            f"[i] Complete answer over budget: all {total_cols} columns shown "
            f"(~{est} tokens vs the requested ~{token_budget}-token budget). "
            f"{narrow_hint}\n\n"
            + body
        )
    return (
        f"[!] TRUNCATED: showing {shown_col_lines} of {total_col_lines} columns "
        f"(~{token_budget}-token budget). The answer may be among the "
        f"{cut_count} cut columns — {narrow_hint}\n\n"
        + kept
        + f"\n... (truncated — {cut_count} more columns cut by "
          f"~{token_budget}-token budget. {narrow_hint})"
    )


def _edge_lines(graph: LineageGraph, assertion: Assertion) -> list[str]:
    src = ", ".join(_display(graph, s) for s in assertion.sources) or "(unresolved)"
    tgt = _display(graph, assertion.target)
    line = f"EDGE {assertion.kind} {src} --> {tgt}"
    extra = []
    if assertion.expression:
        extra.append(f"expr={assertion.expression}")
    span = assertion.span
    if span:
        extra.append(f"at={span}")
    extra.append(f"method={assertion.method}")
    return [line, "     " + "  ".join(extra)]


def _diag_line(item: dict) -> str:
    code = item.get("code") or "DIAG"
    loc = item.get("location") or item.get("span") or {}
    span = item.get("spanText") or span_text(loc)
    message = item.get("message") or ""
    quoted = f'  "{message}"' if message else ""
    at = f" at={span}" if span else ""
    return f"DIAG {code}{at}{quoted}"


def _diag_from_unresolved(_graph: LineageGraph, assertions: list[Assertion]) -> list[str]:
    lines = []
    for assertion in assertions:
        if assertion.kind not in UNRESOLVED_KINDS and assertion.kind != "UNRESOLVED":
            continue
        message = assertion.expression or "unresolved dependency"
        span = assertion.span
        at = f" at={span}" if span else ""
        lines.append(f'DIAG UNRESOLVED{at}  "{message}"')
    return lines


def _matching_diagnostics(graph: LineageGraph, assertions: list[Assertion]) -> list[dict]:
    keys: set[tuple[str, str, str]] = set()
    for assertion in assertions:
        loc = assertion.location
        file = str(loc.get("file") or "")
        pkg = str(loc.get("package") or "")
        routine = str(loc.get("procedure") or loc.get("function") or "")
        keys.add((file, pkg, routine))
    out = []
    for item in graph.diagnostics:
        loc = item.get("location") or {}
        if not isinstance(loc, dict):
            loc = {}
        file = str(loc.get("file") or "")
        pkg = str(loc.get("package") or "")
        routine = str(loc.get("procedure") or loc.get("function") or "")
        if (file, pkg, routine) in keys:
            out.append(item)
    # Dedup by (code, file, line, message)
    seen: set[tuple] = set()
    uniq = []
    for item in out:
        loc = item.get("location") or {}
        ident = (
            item.get("code"),
            (loc or {}).get("file") if isinstance(loc, dict) else None,
            (loc or {}).get("line") if isinstance(loc, dict) else None,
            item.get("message"),
        )
        if ident in seen:
            continue
        seen.add(ident)
        uniq.append(item)
    return uniq


def _header(*, seed: str, downstream: bool, depth: int, kinds: set[str],
            n_assertions: int, budget: int) -> str:
    direction = "Downstream" if downstream else "Upstream"
    if kinds == set(VALUE_KINDS):
        kind_label = "value"
    elif kinds >= (set(VALUE_KINDS) | {"FILTER"} | {"UNRESOLVED"}):
        kind_label = "all"
    else:
        kind_label = ",".join(sorted(kinds))
    return (
        f"Column: {seed}\n"
        f"  {direction} depth={depth} kind={kind_label}  |  "
        f"{n_assertions} assertions  |  budget ~{budget}"
    )


def render_query(
    graph: LineageGraph,
    query: str,
    *,
    depth: int = DEFAULT_DEPTH,
    token_budget: int = DEFAULT_BUDGET,
    kinds: set[str] | None = None,
    downstream: bool = False,
) -> str:
    kinds = kinds if kinds is not None else set(VALUE_KINDS)
    matches, status = resolve_seeds(graph, query)
    if status == "ambiguous":
        listing = "\n".join(f"  {m}" for m in matches)
        return (
            f"Ambiguous: '{query}' matches {len(matches)} columns.\n"
            f"{listing}\n"
            "Retry with a more specific FQN."
        )
    if status != "ok":
        cands = suggest_candidates(graph, query)
        if cands:
            listing = "\n".join(f"  {c}" for c in cands)
            return (
                f"No column matching '{query}'. Nearby FQNs:\n"
                f"{listing}\n"
                "Retry with one of these."
            )
        return (
            f"No column matching '{query}'. "
            "The graph has no relevant FQN for this question."
        )
    seed = matches[0]
    nodes, assertions = traverse(
        graph, matches, depth=depth, kinds=kinds, downstream=downstream)
    header = _header(
        seed=_display(graph, seed), downstream=downstream, depth=depth,
        kinds=kinds, n_assertions=len(assertions), budget=token_budget)
    col_lines = [f"COL {_display(graph, n)}" for n in nodes]
    edge_lines: list[str] = []
    for assertion in assertions:
        edge_lines.extend(_edge_lines(graph, assertion))
    diag_lines = _diag_from_unresolved(graph, assertions)
    for item in _matching_diagnostics(graph, assertions):
        diag_lines.append(_diag_line(item))
    lines = [header, ""] + col_lines + edge_lines + diag_lines
    # seed COL lines are the first len(matches) after the blank
    seed_line_count = 2 + len(matches)  # header, blank, COL seeds
    body_lines = col_lines + edge_lines + diag_lines
    rendered = _cut_to_budget(
        [header, ""] + body_lines,
        token_budget,
        seed_line_count=seed_line_count,
        total_cols=len(nodes),
        narrow_hint="narrow with --kind FILTER or a more specific FQN, or raise --budget",
    )
    return rendered


def render_explain(
    graph: LineageGraph,
    query: str,
    *,
    token_budget: int = DEFAULT_BUDGET,
    kinds: set[str] | None = None,
    downstream: bool = False,
) -> str:
    kinds = kinds if kinds is not None else set(VALUE_KINDS)
    matches, status = resolve_seeds(graph, query)
    if status != "ok":
        return render_query(graph, query, depth=1, token_budget=token_budget,
                            kinds=kinds, downstream=downstream)
    seed = matches[0]
    nodes, assertions = traverse(
        graph, matches, depth=1, kinds=kinds, downstream=downstream)
    header = (
        f"Column: {_display(graph, seed)}\n"
        f"  {'Downstream' if downstream else 'Upstream'} 1 hop  |  "
        f"{len(assertions)} assertions"
    )
    shown = assertions[:MAX_EXPLAIN_EDGES]
    remainder = assertions[MAX_EXPLAIN_EDGES:]
    lines = [header, "", f"COL {_display(graph, seed)}"]
    for assertion in shown:
        lines.extend(_edge_lines(graph, assertion))
    if remainder:
        by_file: dict[str, int] = {}
        for assertion in remainder:
            file = str(assertion.location.get("file") or "(unknown file)")
            by_file[file] = by_file.get(file, 0) + 1
        lines.append(f"  ... and {len(remainder)} more")
        lines.append("  Grouped by file:")
        for file, count in sorted(by_file.items(), key=lambda kv: (-kv[1], kv[0])):
            noun = "assertion" if count == 1 else "assertions"
            lines.append(f"    {file}: {count} {noun}")
    for item in _diag_from_unresolved(graph, assertions):
        lines.append(item)
    for item in _matching_diagnostics(graph, assertions):
        lines.append(_diag_line(item))
    return _cut_to_budget(
        lines, token_budget, seed_line_count=3, total_cols=len(nodes),
        narrow_hint="use query for more hops, or --kind to widen",
    )


def render_path(
    graph: LineageGraph,
    source: str,
    target: str,
    *,
    kinds: set[str] | None = None,
    token_budget: int = DEFAULT_BUDGET,
) -> str:
    kinds = kinds if kinds is not None else set(VALUE_KINDS)
    src_matches, src_status = resolve_seeds(graph, source)
    tgt_matches, tgt_status = resolve_seeds(graph, target)
    if src_status != "ok":
        return render_query(graph, source, depth=0, token_budget=token_budget, kinds=kinds)
    if tgt_status != "ok":
        return render_query(graph, target, depth=0, token_budget=token_budget, kinds=kinds)
    src = src_matches[0]
    tgt = tgt_matches[0]
    if _key(src) == _key(tgt):
        return (
            f"'{source}' and '{target}' both resolved to '{_display(graph, src)}'. "
            "Use two different FQNs."
        )
    # Directed path along source --> target (value flows toward the sink).
    prev: dict[str, tuple[str, Assertion] | None] = {_key(src): None}
    queue = deque([src])
    found = False
    while queue:
        node = queue.popleft()
        if _key(node) == _key(tgt):
            found = True
            break
        for assertion in graph.by_source.get(_key(node), []):
            if assertion.kind not in kinds:
                continue
            nxt = assertion.target
            if _key(nxt) in prev:
                continue
            prev[_key(nxt)] = (node, assertion)
            queue.append(nxt)
    if not found or _key(tgt) not in prev:
        return (
            f"No path from {_display(graph, src)} to {_display(graph, tgt)} "
            f"under kind={','.join(sorted(kinds))}."
        )
    hops: list[Assertion] = []
    cursor = tgt
    while _key(cursor) != _key(src):
        step = prev[_key(cursor)]
        if step is None:
            break
        parent, assertion = step
        hops.append(assertion)
        cursor = parent
    hops.reverse()
    lines = [
        f"Path ({len(hops)} hop{'s' if len(hops) != 1 else ''}):",
        f"  {_display(graph, src)} -> {_display(graph, tgt)}",
        "",
    ]
    for assertion in hops:
        lines.extend(_edge_lines(graph, assertion))
    return _cut_to_budget(
        lines, token_budget, seed_line_count=2, total_cols=len(hops) + 1,
        narrow_hint="try --kind all if a FILTER hop is required",
    )


def render_diagnose(
    graph: LineageGraph,
    *,
    token_budget: int = DEFAULT_BUDGET,
) -> str:
    items = list(graph.diagnostics)
    # Also surface UNRESOLVED assertions that have no diagnostic sibling.
    synthetic = []
    for assertions in graph.by_target.values():
        for assertion in assertions:
            if assertion.kind in UNRESOLVED_KINDS or assertion.kind == "UNRESOLVED":
                synthetic.append({
                    "severity": "warning",
                    "code": "UNRESOLVED",
                    "message": assertion.expression or "unresolved dependency",
                    "location": assertion.location,
                })
    items = synthetic + items

    def _rank(item: dict) -> tuple:
        code = str(item.get("code") or "")
        priority = 0
        if code in {"DYNAMIC_SQL", "UNRESOLVED", "EXECUTE_IMMEDIATE"}:
            priority = 0
        elif code == "PARSE_FAILED":
            priority = 1
        else:
            priority = 2
        loc = item.get("location") or {}
        file = loc.get("file") if isinstance(loc, dict) else ""
        line = loc.get("line") if isinstance(loc, dict) else 0
        return (priority, str(file), line or 0, code)

    items.sort(key=_rank)
    lines = [f"Diagnostics: {len(items)}", ""]
    for item in items:
        lines.append(_diag_line(item))
    if len(lines) == 2:
        return "No diagnostics."
    return _cut_to_budget(
        lines, token_budget, seed_line_count=2, total_cols=len(items),
        narrow_hint="raise --budget to see more diagnostics",
    )
