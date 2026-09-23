"""Table-to-table relations inside one SQL statement.

sqlglot parses the statement. This walk records which base table is written and
which base tables that statement reads. Column projection, expression kind, and
filter-versus-value are not decided here: a source table is any base table
named in the statement other than the write target itself.

CTE names and inline-view aliases are not tables. ``SELECT ... INTO`` writes a
PL/SQL name, so it yields no relation. An ``INSERT ... VALUES`` of literals
names no source table, so it yields no relation either.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import expressions as exp

from .sqlmap import _table_name, split_dblink

logging.getLogger("sqlglot").setLevel(logging.ERROR)

_OPERATIONS = {
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Delete: "DELETE",
    exp.Merge: "MERGE",
}


@dataclass(frozen=True)
class TableRelation:
    source: str
    target: str
    operation: str


@dataclass
class TableStatement:
    relations: list[TableRelation] = field(default_factory=list)
    error: str | None = None
    diagnostics: list[tuple[str, str]] = field(default_factory=list)


def statement_relations(sql: str) -> TableStatement:
    """Relations for one Oracle SQL statement. Empty when nothing is written."""
    diagnostics: list[tuple[str, str]] = []
    try:
        tree = sqlglot.parse_one(sql, dialect="oracle")
    except Exception as exc:
        return TableStatement(error=f"{type(exc).__name__}: {exc}")
    if tree is None or isinstance(tree, exp.Command):
        return TableStatement(error="unsupported statement")

    for table in tree.find_all(exp.Table):
        raw = table.name or ""
        if "@" in raw and split_dblink(raw)[1] is None:
            diagnostics.append((
                "DB_LINK_UNRESOLVED",
                f"DB link 를 객체 식별자에 보존하지 못했습니다: {raw}",
            ))

    operation = _OPERATIONS.get(type(tree))
    if operation is None:
        return TableStatement(diagnostics=diagnostics)
    target = _write_target(tree)
    if target is None:
        return TableStatement(diagnostics=diagnostics)
    target_name, target_node = target
    if not target_name:
        return TableStatement(diagnostics=diagnostics)

    cte_names = _cte_names(tree)
    sources = _source_tables(tree, cte_names, target_node)
    relations = [
        TableRelation(source=source, target=target_name, operation=operation)
        for source in sources
    ]
    return TableStatement(relations=relations, diagnostics=diagnostics)


def _write_target(tree: exp.Expression) -> tuple[str, exp.Table] | None:
    node = tree.this
    if isinstance(node, exp.Schema):
        node = node.this
    if not isinstance(node, exp.Table):
        return None
    return _table_name(node), node


def _cte_names(tree: exp.Expression) -> set[str]:
    names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(str(alias).upper())
    return names


def _is_cte_reference(table: exp.Table, cte_names: set[str]) -> bool:
    if table.name.upper() in cte_names:
        return True
    qualified = _table_name(table).upper()
    return qualified in cte_names


def _source_tables(tree: exp.Expression, cte_names: set[str],
                   target: exp.Table) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for table in tree.find_all(exp.Table):
        if table is target:
            continue
        if table.find_ancestor(exp.Into) is not None:
            continue
        if _is_cte_reference(table, cte_names):
            continue
        name = _table_name(table)
        if not name:
            continue
        key = name.upper()
        if key in seen:
            continue
        seen.add(key)
        found.append(name)
    return found
