"""Layer C - carry values across statement boundaries through PL/SQL names.

Layer B reads one statement at a time, so a value that travels through a
variable leaves each half unresolvable:

    SELECT r.UNIT_WGT BULK COLLECT INTO t_rows FROM SYNIF.IF_ITEM_RCV r;
    FORALL i IN 1 .. t_rows.COUNT
      UPDATE SYNWMS.MST_ITEM t SET t.UNIT_WGT = t_rows(i).UNIT_WGT;

The first statement writes to no table; the second reads from none. Neither is
lineage on its own, and both parse perfectly. What joins them is remembering
what ``t_rows`` holds, which is all this layer does: walk a subprogram's
statements in order, record what each name is filled with, and substitute when
a later statement reads it.

Control flow is already flattened by layer A. An assignment inside an IF is
recorded unconditionally - "this variable can carry that value" is the question
lineage asks, not "does it on every path".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import expressions as exp

from .sqlmap import Binding, Edge, Ref

logging.getLogger("sqlglot").setLevel(logging.ERROR)

VIA_VARIABLE = "VIA_VARIABLE"


@dataclass
class Carried:
    """What a name currently holds, and how far the value has travelled."""
    sources: list[Ref]
    hops: int
    kind: str


@dataclass
class Scope:
    """Names bound within one subprogram, updated in statement order."""
    held: dict[str, Carried] = field(default_factory=dict)

    def bind(self, name: str, sources: list[Ref], hops: int, kind: str) -> None:
        if sources:
            self.held[name.upper()] = Carried(list(sources), hops, kind)

    def apply(self, bindings: list[Binding]) -> None:
        """Record what a SELECT ... INTO put into each name.

        The sources arrive already resolved to base tables by layer B, so the
        value has crossed exactly one boundary at this point.
        """
        for binding in bindings:
            self.bind(binding.variable, binding.sources, 1, binding.kind)

    def lookup(self, names: list[str]) -> tuple[list[Ref], int]:
        """Base-table sources behind these names, and the longest hop count."""
        found: list[Ref] = []
        hops = 0
        for name in names:
            carried = self.held.get(name.upper())
            if carried is None:
                continue
            hops = max(hops, carried.hops)
            for ref in carried.sources:
                if ref not in found:
                    found.append(ref)
        return found, hops


def resolve_edges(edges: list[Edge], scope: Scope) -> list[Edge]:
    """Fill in each edge's unresolved names from the scope.

    An edge whose value came only through a variable has no sources until now;
    it is completed here and re-labelled VIA_VARIABLE. An edge that already had
    table sources gains the variable's sources alongside them.
    """
    out: list[Edge] = []
    for edge in edges:
        if not edge.unresolved:
            out.append(edge)
            continue

        carried, hops = scope.lookup(edge.unresolved)
        if not carried:
            out.append(edge)             # still unknown; caller decides
            continue

        merged = list(edge.sources)
        for ref in carried:
            if ref not in merged:
                merged.append(ref)
        kind = VIA_VARIABLE if not edge.sources else edge.kind
        out.append(Edge(edge.target, merged, kind, edge.transform,
                        hops=hops + 1))
    return out


def assignment_binding(sql: str, scope: Scope) -> tuple[str, list[Ref], int] | None:
    """Read ``v := <expr>`` and work out what v now holds.

    Only names already in scope contribute. A bare identifier that nothing has
    filled carries no lineage, and treating it as a column would invent one.
    """
    head, separator, tail = sql.partition(":=")
    if not separator:
        return None
    target = head.strip().rstrip(";").strip()
    if not target or "." in target or "(" in target:
        return None                      # record or collection element: not tracked

    try:
        expression = sqlglot.parse_one(tail.strip().rstrip(";"), dialect="oracle")
    except Exception:
        return None
    if expression is None:
        return None

    names: list[str] = []
    for column in expression.find_all(exp.Column):
        name = f"{column.table}.{column.name}" if column.table else column.name
        names.append(name.upper())
    for dot in expression.find_all(exp.Dot):
        owner, field_name = dot.this, dot.expression
        if isinstance(owner, exp.Anonymous) and isinstance(field_name, exp.Identifier):
            names.append(f"{owner.this}.{field_name.name}".upper())

    sources, hops = scope.lookup(names)
    if not sources:
        return None
    return target, sources, hops
