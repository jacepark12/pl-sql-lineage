"""Budgeted table-relation text for agents.

Reads ``relations`` from engine JSON. A seed is a table (``OUT_ALLOC`` or
``SYNWMS.OUT_ALLOC``), not a column. The procedure is printed on the relation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_DEPTH = 2
DEFAULT_BUDGET = 2000


@dataclass(frozen=True)
class Relation:
    source: str
    target: str
    operation: str
    method: str
    location: dict


@dataclass
class TableGraph:
    display: dict[str, str] = field(default_factory=dict)
    by_target: dict[str, list[Relation]] = field(default_factory=dict)
    by_source: dict[str, list[Relation]] = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)

    def tables(self) -> list[str]:
        return sorted(self.display)


def _key(name: str) -> str:
    return name.strip().upper()


def _remember(graph: TableGraph, name: str) -> None:
    key = _key(name)
    graph.display.setdefault(key, name.strip())


def load_relations(data: dict) -> TableGraph:
    graph = TableGraph()
    for item in data.get("relations") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target:
            continue
        location = item.get("location") if isinstance(item.get("location"), dict) else {}
        relation = Relation(
            source=source,
            target=target,
            operation=str(item.get("operation") or "WRITE"),
            method=str(item.get("method") or "static"),
            location=location,
        )
        _remember(graph, source)
        _remember(graph, target)
        graph.by_target.setdefault(_key(target), []).append(relation)
        graph.by_source.setdefault(_key(source), []).append(relation)
    for item in data.get("diagnostics") or []:
        if isinstance(item, dict):
            graph.diagnostics.append(item)
    return graph


def resolve_table(graph: TableGraph, query: str) -> tuple[list[str], str]:
    """Return ``(matches, status)`` where status is ok, ambiguous, or missing."""
    needle = _key(query)
    if not needle:
        return [], "missing"
    exact = [key for key in graph.display if key == needle]
    if len(exact) == 1:
        return exact, "ok"
    if len(exact) > 1:
        return [_display(graph, key) for key in exact], "ambiguous"
    suffix = [key for key in graph.display if key.endswith("." + needle) or key == needle]
    if len(suffix) == 1:
        return suffix, "ok"
    if len(suffix) > 1:
        return [_display(graph, key) for key in sorted(suffix)], "ambiguous"
    return [], "missing"


def suggest_tables(graph: TableGraph, query: str, limit: int = 8) -> list[str]:
    needle = _key(query)
    if not needle:
        return []
    hits = [key for key in graph.display if needle in key]
    hits.sort()
    return [_display(graph, key) for key in hits[:limit]]


def _display(graph: TableGraph, key: str) -> str:
    return graph.display.get(key, key)


def _walk(graph: TableGraph, seeds: list[str], *, depth: int,
          downstream: bool) -> tuple[list[str], list[Relation]]:
    seen_nodes = []
    seen_keys: set[str] = set()
    relations: list[Relation] = []
    seen_rel: set[tuple] = set()
    frontier = list(seeds)
    for _ in range(max(depth, 0)):
        nxt: list[str] = []
        for key in frontier:
            bucket = graph.by_source.get(key, []) if downstream else graph.by_target.get(key, [])
            for relation in bucket:
                other = _key(relation.target if downstream else relation.source)
                ident = (
                    _key(relation.source), _key(relation.target),
                    relation.operation, relation.method,
                    relation.location.get("file"), relation.location.get("line"),
                    relation.location.get("procedure"), relation.location.get("function"),
                )
                if ident not in seen_rel:
                    seen_rel.add(ident)
                    relations.append(relation)
                if other not in seen_keys:
                    seen_keys.add(other)
                    seen_nodes.append(other)
                    nxt.append(other)
        frontier = nxt
    nodes = []
    have: set[str] = set()
    for key in seeds + seen_nodes:
        if key in have:
            continue
        have.add(key)
        nodes.append(key)
    return nodes, relations


def _location_text(location: dict) -> str:
    file = str(location.get("file") or "")
    line = location.get("line")
    span = file
    if line is not None and line != "":
        span = f"{file}:{line}" if file else str(line)
    routine = ".".join(
        part for part in (
            str(location.get("package") or "").strip(),
            str(location.get("function") or location.get("procedure") or "").strip(),
        ) if part
    )
    return " ".join(part for part in (span, routine) if part)


def _rel_lines(relation: Relation) -> list[str]:
    via = _location_text(relation.location)
    head = (
        f"REL {relation.operation} {relation.source} --> {relation.target}"
    )
    detail = f"     method={relation.method}"
    if via:
        detail += f"  at={via}"
    return [head, detail]


def _diag_lines(graph: TableGraph, relations: list[Relation]) -> list[str]:
    files = {
        str(relation.location.get("file") or "")
        for relation in relations if relation.location.get("file")
    }
    lines: list[str] = []
    seen: set[tuple] = set()
    for item in graph.diagnostics:
        location = item.get("location") if isinstance(item.get("location"), dict) else {}
        file = str(location.get("file") or "")
        code = str(item.get("code") or "")
        if files and file and file not in files and code not in {
            "DYNAMIC_SQL", "DYNAMIC_SQL_PARTIAL", "PARSE_FAILED",
        }:
            continue
        if files and file and file not in files:
            continue
        if not files and code not in {"DYNAMIC_SQL", "DYNAMIC_SQL_PARTIAL", "PARSE_FAILED"}:
            continue
        ident = (code, file, location.get("line"), item.get("message"))
        if ident in seen:
            continue
        seen.add(ident)
        at = _location_text(location)
        message = str(item.get("message") or "")
        lines.append(f"DIAG {code}" + (f" at={at}" if at else "") + f"  \"{message}\"")
    return lines


def _cut(lines: list[str], budget: int, seed_line_count: int) -> str:
    limit = max(budget, 1) * 3
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    kept = lines[:seed_line_count]
    used = len("\n".join(kept))
    for line in lines[seed_line_count:]:
        extra = len(line) + 1
        if used + extra > limit:
            break
        kept.append(line)
        used += extra
    omitted = len(lines) - len(kept)
    kept.append(
        f"[!] TRUNCATED {omitted} lines omitted. "
        "Raise --budget or narrow the table name."
    )
    return "\n".join(kept)


def render_table_query(
    graph: TableGraph,
    query: str,
    *,
    depth: int = DEFAULT_DEPTH,
    token_budget: int = DEFAULT_BUDGET,
    downstream: bool = False,
) -> str:
    matches, status = resolve_table(graph, query)
    if status == "ambiguous":
        listing = "\n".join(f"  {name}" for name in matches)
        return (
            f"Ambiguous: '{query}' matches {len(matches)} tables.\n"
            f"{listing}\n"
            "Retry with a more specific table name."
        )
    if status != "ok":
        candidates = suggest_tables(graph, query)
        if candidates:
            listing = "\n".join(f"  {name}" for name in candidates)
            return (
                f"No table matching '{query}'. Nearby tables:\n"
                f"{listing}\n"
                "Retry with one of these."
            )
        return (
            f"No table matching '{query}'. "
            "The graph has no table relation for this question."
        )
    seed = matches[0]
    nodes, relations = _walk(graph, matches, depth=depth, downstream=downstream)
    direction = "Downstream" if downstream else "Upstream"
    header = (
        f"Table: {_display(graph, seed)}\n"
        f"  {direction} depth={depth}  |  {len(relations)} relations  |  "
        f"budget ~{token_budget}"
    )
    table_lines = [f"TABLE {_display(graph, key)}" for key in nodes]
    rel_lines: list[str] = []
    for relation in relations:
        rel_lines.extend(_rel_lines(relation))
    diag = _diag_lines(graph, relations)
    body = [header, ""] + table_lines + rel_lines + diag
    return _cut(body, token_budget, seed_line_count=2 + len(matches))


def render_table_explain(
    graph: TableGraph,
    query: str,
    *,
    token_budget: int = DEFAULT_BUDGET,
    downstream: bool = False,
) -> str:
    return render_table_query(
        graph, query, depth=1, token_budget=token_budget, downstream=downstream)


def render_table_path(
    graph: TableGraph,
    source: str,
    target: str,
    *,
    token_budget: int = DEFAULT_BUDGET,
) -> str:
    sources, source_status = resolve_table(graph, source)
    targets, target_status = resolve_table(graph, target)
    if source_status != "ok":
        return render_table_query(graph, source, depth=1, token_budget=token_budget)
    if target_status != "ok":
        return render_table_query(graph, target, depth=1, token_budget=token_budget)
    start, goal = sources[0], targets[0]
    if start == goal:
        return "Use two different tables."
    previous: dict[str, tuple[str, Relation] | None] = {start: None}
    queue = [start]
    found = False
    while queue:
        current = queue.pop(0)
        if current == goal:
            found = True
            break
        for relation in graph.by_source.get(current, []):
            nxt = _key(relation.target)
            if nxt in previous:
                continue
            previous[nxt] = (current, relation)
            queue.append(nxt)
    if not found or goal not in previous:
        return (
            f"No path from {_display(graph, start)} to {_display(graph, goal)}."
        )
    chain: list[Relation] = []
    cursor = goal
    while previous[cursor] is not None:
        prev, relation = previous[cursor]  # type: ignore[misc]
        chain.append(relation)
        cursor = prev
    chain.reverse()
    lines = [
        f"Table path: {_display(graph, start)} -> {_display(graph, goal)}",
        "",
        f"TABLE {_display(graph, start)}",
    ]
    seen = {start}
    for relation in chain:
        target_key = _key(relation.target)
        if target_key not in seen:
            lines.append(f"TABLE {_display(graph, target_key)}")
            seen.add(target_key)
        lines.extend(_rel_lines(relation))
    return _cut(lines, token_budget, seed_line_count=3)
