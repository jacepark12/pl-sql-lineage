"""Layer B - read column lineage out of one SQL statement.

sqlglot parses the statement; this walks the result. ``sqlglot.lineage()`` is
not used: it traces one output column at a time and reports only value sources,
while a third of the edges that matter here are the indirect ones - the columns
a WHERE, JOIN or GROUP BY reads to decide *which* rows are written. Those never
appear in a value trace, so the AST is walked directly and both kinds come out
of one pass.

Everything here is statement-local. A value arriving through a PL/SQL variable
leaves the statement as an unresolved source and layer C reconnects it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import expressions as exp

logging.getLogger("sqlglot").setLevel(logging.ERROR)

DIRECT = "DIRECT"
TRANSFORM = "TRANSFORM"
AGGREGATE = "AGGREGATE"
ANALYTIC = "ANALYTIC"
FILTER = "INDIRECT_FILTER"


@dataclass(frozen=True)
class Ref:
    """A column, or a whole table when ``column`` is None."""
    table: str
    column: str | None = None


@dataclass
class Edge:
    target: Ref
    sources: list[Ref]
    kind: str
    transform: str
    unresolved: list[str] = field(default_factory=list)   # PL/SQL names
    hops: int = 1


@dataclass
class Binding:
    """A PL/SQL name filled by this statement, and what filled it.

    ``variable`` is either a plain name (``V_QTY``) or a dotted one
    (``T_ROWS.UNIT_WGT``) when a collection or record field is written.
    """
    variable: str
    sources: list[Ref]
    kind: str
    transform: str


@dataclass
class StatementLineage:
    edges: list[Edge] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    error: str | None = None


# --- names --------------------------------------------------------------------


def _table_name(table: exp.Table) -> str:
    parts = [p.name for p in (table.args.get("catalog"), table.args.get("db")) if p]
    return ".".join([*parts, table.name])


def _alias_map(scope: exp.Expression) -> tuple[dict[str, str], list[str]]:
    """alias/table-name -> qualified name, plus every table in source order.

    Only tables belonging to *this* scope are returned. A table inside a nested
    select is that select's business, and its alias is invisible from out here -
    but when the nested select is itself passed in as ``scope``, its own tables
    are exactly what should come back.
    """
    aliases: dict[str, str] = {}
    tables: list[str] = []
    for table in scope.find_all(exp.Table):
        owner = table.find_ancestor(exp.Select)
        if isinstance(scope, exp.Select):
            if owner is not scope:       # belongs to a select nested inside
                continue
        elif owner is not None:          # UPDATE/DELETE: skip subquery tables
            continue
        qualified = _table_name(table)
        tables.append(qualified)
        aliases[qualified.upper()] = qualified
        aliases[table.name.upper()] = qualified
        if table.alias:
            aliases[table.alias.upper()] = qualified
    return aliases, tables


def _resolve(column: exp.Column, aliases: dict[str, str], tables: list[str],
             variables: frozenset[str]) -> Ref | None:
    """Bind a column reference to a base table, or give up.

    sqlglot cannot tell a bare column from a PL/SQL variable - both are plain
    identifiers - so ``variables`` carries the names layer A saw declared in the
    enclosing subprogram. Without it, ``WHERE t.SEQ = p_seq`` invents a column
    named ``p_seq`` on the target table.

    An unqualified name that is not a known variable is attributed to the only
    table in scope. With more than one it is genuinely ambiguous absent a
    catalog, and guessing an owner would fabricate lineage, so it is dropped.
    """
    qualifier = column.table
    if qualifier:
        owner = aliases.get(qualifier.upper())
        return Ref(owner, column.name) if owner else None
    if column.name.upper() in variables:
        return None
    if len(set(tables)) == 1:
        return Ref(tables[0], column.name)
    return None


def _pl_reference(node: exp.Expression) -> str | None:
    """The PL/SQL name a node denotes, if it is not a base-table column.

    Two shapes reach here. ``rec.ITEM_CD`` is a Column whose qualifier names no
    table in scope - a cursor record. ``t_rows(i).UNIT_WGT`` is a Dot over an
    Anonymous call, because sqlglot cannot tell collection subscripting from a
    function call; the subscript itself is discarded, since which element is
    read says nothing about where the value came from.
    """
    if isinstance(node, exp.Dot):
        owner = node.this
        field = node.expression
        if isinstance(owner, exp.Anonymous) and isinstance(field, exp.Identifier):
            return f"{owner.this}.{field.name}".upper()
    return None


def _classify(expression: exp.Expression) -> str:
    """How the value is derived, judged on the outer expression only.

    A nested select is a separate computation whose shape says nothing about
    how its result reaches the target: ``NVL((SELECT SUM(q) ...), 0)`` delivers
    a transformed scalar, not an aggregate of the target's own rows.
    """
    if isinstance(expression, exp.Column):
        return DIRECT
    nested = list(expression.find_all(exp.Select))

    def outer(node_type) -> bool:
        return any(node for node in expression.find_all(node_type)
                   if not any(node is inner for select in nested
                              for inner in select.find_all(node_type)))

    if outer(exp.Window):
        return ANALYTIC
    if outer(exp.AggFunc):
        return AGGREGATE
    return TRANSFORM


def _predicates(select: exp.Select) -> list[exp.Expression]:
    """WHERE, GROUP BY and JOIN ON of one select scope."""
    found = [_inner(select.args.get("where")), _inner(select.args.get("group"))]
    for join in select.find_all(exp.Join):
        found.append(join.args.get("on"))
    return [clause for clause in found if clause is not None]


def _case_conditions(expression: exp.Expression) -> list[exp.Expression]:
    """The deciding half of every CASE: WHEN tests and any simple-CASE operand.

    ``CASE WHEN d.STAT = '10' THEN d.ORD_NO ELSE ' ' END`` carries d.ORD_NO into
    the target, but d.STAT only picks which branch runs. Counting the test as a
    value source would claim the target is derived from a column it never
    copies.
    """
    found: list[exp.Expression] = []
    for case in expression.find_all(exp.Case):
        if case.this is not None:
            found.append(case.this)
        for branch in case.args.get("ifs") or []:
            if branch.this is not None:
                found.append(branch.this)

    # DECODE(search, cmp1, result1, cmp2, result2, ..., default) arrives as one
    # flat list rather than a Case tree: the search expression and every value
    # it is compared against decide the branch, the results carry the value.
    for decode in expression.find_all(exp.DecodeCase):
        arguments = decode.expressions
        if not arguments:
            continue
        found.append(arguments[0])
        found.extend(arguments[index] for index in range(1, len(arguments) - 1, 2))
    return found


def _plain_sources(expression: exp.Expression, aliases: dict[str, str],
                   tables: list[str], variables: frozenset[str],
                   exclude: frozenset[int] = frozenset()) -> tuple[list[Ref], list[str]]:
    """Columns an expression reads directly, ignoring any nested select."""
    nested = list(expression.find_all(exp.Select))
    found: list[Ref] = []
    unresolved: list[str] = []

    def remember(name: str) -> None:
        if name not in unresolved:
            unresolved.append(name)

    dotted = list(expression.find_all(exp.Dot))
    for node in dotted:
        reference = _pl_reference(node)
        if reference:
            remember(reference)

    for column in expression.find_all(exp.Column):
        if id(column) in exclude:
            continue
        if any(column is inner for select in nested
               for inner in select.find_all(exp.Column)):
            continue
        if any(column is inner for node in dotted
               for inner in node.find_all(exp.Column)):
            continue                     # the subscript of a collection access
        ref = _resolve(column, aliases, tables, variables)
        if ref is not None:
            if ref not in found:
                found.append(ref)
        elif column.table:
            remember(f"{column.table}.{column.name}".upper())
        else:
            remember(column.name.upper())
    return found, unresolved


def _sources(expression: exp.Expression, aliases: dict[str, str],
             tables: list[str],
             variables: frozenset[str]) -> tuple[list[Ref], list[str], list[Ref]]:
    """Split what an expression reads into value sources and filter sources.

    A scalar subquery is its own scope. Its projections carry the value; its
    WHERE - including the correlation predicate joining it to the outer row -
    only decides which rows are summed. The outer half of that correlation is
    dropped by the caller: the row being written does not filter itself. Reading them all as value sources is
    wrong twice over: in ``SET q = (SELECT SUM(p.QTY) FROM PICK p WHERE
    p.K = t.K)`` it loses PICK.QTY, whose alias is invisible outside, and
    credits the outer t.K as if the value came from it.
    """
    values: list[Ref] = []
    unresolved: list[str] = []
    filters: list[Ref] = []

    def add(into: list[Ref], refs: list[Ref]) -> None:
        for ref in refs:
            if ref not in into:
                into.append(ref)

    for select in expression.find_all(exp.Select):
        inner_aliases, inner_tables = _alias_map(select)
        # The outer scope stays visible so a correlation predicate resolves.
        scope = {**aliases, **inner_aliases}
        scope_tables = inner_tables or tables
        for projection in select.expressions:
            refs, unres = _plain_sources(projection.unalias(), scope,
                                         scope_tables, variables)
            add(values, refs)
            unresolved.extend(u for u in unres if u not in unresolved)
        for clause in _predicates(select):
            refs, _ = _plain_sources(clause, scope, scope_tables, variables)
            add(filters, refs)

    conditions = _case_conditions(expression)
    condition_columns = frozenset(
        id(column) for clause in conditions for column in clause.find_all(exp.Column))
    for clause in conditions:
        refs, _ = _plain_sources(clause, aliases, tables, variables)
        add(filters, refs)

    refs, unres = _plain_sources(expression, aliases, tables, variables,
                                 condition_columns)
    add(values, refs)
    unresolved.extend(u for u in unres if u not in unresolved)
    return values, unresolved, filters


def _sql(expression: exp.Expression | None) -> str:
    if expression is None:
        return ""
    return " ".join(expression.sql(dialect="oracle").split())


# --- filters ------------------------------------------------------------------


def _filter_edges(scope: exp.Expression, target: str, aliases: dict[str, str],
                  tables: list[str], variables: frozenset[str]) -> list[Edge]:
    """Columns that decide which rows are affected, not what value is written.

    Each clause is rendered from its inner expression: a Where node's own sql()
    already begins with the keyword, so using it whole yields "WHERE WHERE ...".
    """
    clauses: list[tuple[str, exp.Expression | None]] = [
        ("WHERE", _inner(scope.args.get("where"))),
        ("GROUP BY", _inner(scope.args.get("group"))),
    ]
    for join in scope.find_all(exp.Join):
        clauses.append(("JOIN", join.args.get("on")))

    edges: list[Edge] = []
    for label, clause in clauses:
        if clause is None:
            continue
        sources, _, _ = _sources(clause, aliases, tables, variables)
        if not sources:
            continue
        edges.append(Edge(Ref(target, None), sources, FILTER,
                          f"{label} {_sql(clause)}"))
    return edges


def _inner(clause: exp.Expression | None) -> exp.Expression | None:
    """The predicate inside a WHERE / GROUP BY wrapper, without the keyword."""
    if clause is None:
        return None
    if isinstance(clause, exp.Where):
        return clause.this
    if isinstance(clause, exp.Group):
        expressions = clause.expressions
        return exp.Tuple(expressions=expressions) if expressions else None
    return clause


# --- statements ---------------------------------------------------------------


def _insert(statement: exp.Insert, variables: frozenset[str]) -> list[Edge]:
    table = statement.this
    columns: list[str] = []
    if isinstance(table, exp.Schema):
        columns = [c.name for c in table.expressions]
        table = table.this
    target = _table_name(table)

    select = statement.expression
    if not isinstance(select, exp.Select):
        return []                       # INSERT ... VALUES handled by the caller
    aliases, tables = _alias_map(select)

    edges: list[Edge] = []
    projections = select.expressions
    for index, projection in enumerate(projections):
        if index >= len(columns) and columns:
            break
        name = columns[index] if columns else (projection.alias_or_name or None)
        if not name:
            continue
        value = projection.unalias()
        sources, unresolved, filters = _sources(value, aliases, tables, variables)
        if sources or unresolved:
            edges.append(Edge(Ref(target, name), sources, _classify(value),
                              _sql(value), unresolved))
        # Emitted independently of the value edge: a condition still reaches the
        # target when every branch is constant, as in
        # CASE WHEN r.ITEM_CD IS NULL THEN SYSDATE ELSE SYSDATE END.
        correlated = [ref for ref in filters if ref.table != target]
        if correlated:
            edges.append(Edge(Ref(target, name), correlated, FILTER,
                              f"PREDICATE {_sql(value)}"))
    edges.extend(_filter_edges(select, target, aliases, tables, variables))
    return edges


def _update(statement: exp.Update, variables: frozenset[str]) -> list[Edge]:
    target = _table_name(statement.this) if isinstance(statement.this, exp.Table) else ""
    if not target:
        return []
    aliases, tables = _alias_map(statement)
    if target.upper() not in aliases:
        aliases[target.upper()] = target
    if not tables:
        tables = [target]

    edges: list[Edge] = []
    for assignment in statement.expressions:
        if not isinstance(assignment, exp.EQ):
            continue
        column = assignment.this
        if not isinstance(column, exp.Column):
            continue
        value = assignment.expression
        sources, unresolved, filters = _sources(value, aliases, tables, variables)
        if sources or unresolved:
            edges.append(Edge(Ref(target, column.name), sources, _classify(value),
                              _sql(value), unresolved))
        correlated = [ref for ref in filters if ref.table != target]
        if correlated:
            edges.append(Edge(Ref(target, column.name), correlated, FILTER,
                              f"PREDICATE {_sql(value)}"))
    edges.extend(_filter_edges(statement, target, aliases, tables, variables))
    return edges


def _delete(statement: exp.Delete, variables: frozenset[str]) -> list[Edge]:
    if not isinstance(statement.this, exp.Table):
        return []
    target = _table_name(statement.this)
    aliases, tables = _alias_map(statement)
    return _filter_edges(statement, target, aliases, tables or [target], variables)


def _select_into(statement: exp.Select,
                 variables: frozenset[str]) -> tuple[list[Edge], list[Binding]]:
    """SELECT ... INTO / BULK COLLECT INTO: fills names, not table columns.

    Writes no lineage edge on its own - the value has not reached a table yet.
    What it produces is a binding, so that when a later statement reads the
    name, layer C can rejoin the two halves into one edge.
    """
    into = statement.args.get("into")
    if into is None:
        return [], []

    aliases, tables = _alias_map(statement)
    bulk = bool(into.args.get("bulk_collect"))
    targets = [node.name or node.sql() for node in (into.expressions or [])]
    if not targets and into.this is not None:
        targets = [into.this.name or into.this.sql()]

    bindings: list[Binding] = []
    projections = statement.expressions

    if bulk and len(targets) == 1:
        # One collection receives whole rows: bind each projection as a field,
        # which is how it is read back (t_rows(i).UNIT_WGT).
        collection = targets[0]
        for projection in projections:
            name = projection.alias_or_name
            if not name:
                continue
            value = projection.unalias()
            sources, _, _ = _sources(value, aliases, tables, variables)
            if sources:
                bindings.append(Binding(f"{collection}.{name}".upper(), sources,
                                        _classify(value), _sql(value)))
        return [], bindings

    for index, target in enumerate(targets):
        if index >= len(projections):
            break
        value = projections[index].unalias()
        sources, _, _ = _sources(value, aliases, tables, variables)
        if sources:
            bindings.append(Binding(target.upper(), sources, _classify(value),
                                    _sql(value)))
    return [], bindings


_HANDLERS = {exp.Insert: _insert, exp.Update: _update, exp.Delete: _delete}


def analyze_projections(sql: str,
                        variables: frozenset[str] = frozenset()
                        ) -> list[tuple[str, list[Ref], str]]:
    """Each output column of a SELECT, with the base-table columns behind it.

    Used for queries that write no table - a cursor a loop record is drawn
    from - where the projection *is* the lineage.
    """
    try:
        tree = sqlglot.parse_one(sql, dialect="oracle")
    except Exception:
        return []
    if not isinstance(tree, exp.Select):
        return []

    aliases, tables = _alias_map(tree)
    out: list[tuple[str, list[Ref], str]] = []
    for projection in tree.expressions:
        name = projection.alias_or_name
        if not name:
            continue
        value = projection.unalias()
        sources, _, _ = _sources(value, aliases, tables, variables)
        if sources:
            out.append((name, sources, _classify(value)))
    return out


def analyze(sql: str, variables: frozenset[str] = frozenset()) -> StatementLineage:
    """Column lineage for one SQL statement.

    ``variables`` are the PL/SQL names in scope - pass them, or bare identifiers
    become invented columns on the target table.
    """
    try:
        tree = sqlglot.parse_one(sql, dialect="oracle")
    except Exception as exc:
        return StatementLineage(error=f"{type(exc).__name__}: {exc}")
    if tree is None or isinstance(tree, exp.Command):
        return StatementLineage(error="unsupported statement")

    if isinstance(tree, exp.Select):
        if tree.args.get("into") is None:
            return StatementLineage(error="unhandled: Select")
        edges, bindings = _select_into(tree, variables)
        return StatementLineage(edges=edges, bindings=bindings)

    handler = _HANDLERS.get(type(tree))
    if handler is None:
        return StatementLineage(error=f"unhandled: {type(tree).__name__}")
    return StatementLineage(edges=handler(tree, variables))
