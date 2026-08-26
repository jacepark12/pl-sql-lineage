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

from .catalog import columns_for

logging.getLogger("sqlglot").setLevel(logging.ERROR)

DIRECT = "DIRECT"
TRANSFORM = "TRANSFORM"
AGGREGATE = "AGGREGATE"
ANALYTIC = "ANALYTIC"
FILTER = "INDIRECT_FILTER"
VIA_CTE = "VIA_CTE"


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
    diagnostics: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Derived:
    """A CTE, inline view, or MERGE ... USING projection.

    ``transport`` is ``CTE`` for a named WITH / FROM subquery (a lineage hop)
    and ``DERIVED`` for a transparent MERGE source (not a hop, kind unchanged).
    """
    columns: dict[str, list[Ref]]
    transport: str


# --- names --------------------------------------------------------------------


def _table_name(table: exp.Table) -> str:
    parts = [p.name for p in (table.args.get("catalog"), table.args.get("db")) if p]
    return ".".join([*parts, table.name])


def _alias_map(scope: exp.Expression,
               derived_names: set[str] | None = None
               ) -> tuple[dict[str, str], list[str]]:
    """alias/table-name -> qualified name, plus every table in source order.

    Only tables belonging to *this* scope are returned. A table inside a nested
    select is that select's business, and its alias is invisible from out here -
    but when the nested select is itself passed in as ``scope``, its own tables
    are exactly what should come back.

    Names in ``derived_names`` (CTEs, inline views, MERGE USING aliases) are
    still aliased so ``q.COL`` resolves, but they are not base tables. Treating
    them as tables is what used to invent a source named after the CTE.
    """
    derived_names = {n.upper() for n in (derived_names or set())}
    aliases: dict[str, str] = {}
    tables: list[str] = []
    for table in scope.find_all(exp.Table):
        # sqlglot models `SELECT ... INTO v_qty` by wrapping the *variable* in a
        # Table node. Counting it here leaves two candidate tables in scope, so
        # an unqualified column becomes ambiguous and resolves to neither -
        # which is why SELECT ... INTO bound nothing on real code.
        if table.find_ancestor(exp.Into) is not None:
            continue
        owner = table.find_ancestor(exp.Select)
        if isinstance(scope, exp.Select):
            if owner is not scope:       # belongs to a select nested inside
                continue
        elif owner is not None:          # UPDATE/DELETE: skip subquery tables
            continue
        qualified = _table_name(table)
        aliases[qualified.upper()] = qualified
        aliases[table.name.upper()] = qualified
        if table.alias:
            aliases[table.alias.upper()] = qualified
        if (qualified.upper() in derived_names
                or table.name.upper() in derived_names
                or (table.alias and table.alias.upper() in derived_names)):
            continue
        tables.append(qualified)
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
             variables: frozenset[str],
             derived: dict[str, Derived] | None = None,
             catalog: dict[str, list[str]] | None = None,
             diagnostics: list[tuple[str, str]] | None = None
             ) -> tuple[list[Ref], list[str], list[Ref], bool]:
    """Split what an expression reads into value sources and filter sources.

    A scalar subquery is its own scope. Its projections carry the value; its
    WHERE - including the correlation predicate joining it to the outer row -
    only decides which rows are summed. The outer half of that correlation is
    dropped by the caller: the row being written does not filter itself. Reading them all as value sources is
    wrong twice over: in ``SET q = (SELECT SUM(p.QTY) FROM PICK p WHERE
    p.K = t.K)`` it loses PICK.QTY, whose alias is invisible outside, and
    credits the outer t.K as if the value came from it.
    """
    derived = derived or {}
    catalog = catalog or {}
    diagnostics = diagnostics if diagnostics is not None else []
    values: list[Ref] = []
    unresolved: list[str] = []
    filters: list[Ref] = []

    def add(into: list[Ref], refs: list[Ref]) -> None:
        for ref in refs:
            if ref not in into:
                into.append(ref)

    for select in expression.find_all(exp.Select):
        inner_derived = _collect_derived(select, variables, catalog,
                                         diagnostics, derived)
        inner_aliases, inner_tables = _alias_map(select, set(inner_derived))
        _bind_derived(inner_aliases, inner_derived)
        # The outer scope stays visible so a correlation predicate resolves.
        scope = {**aliases, **inner_aliases}
        scope_tables = inner_tables or tables
        for projection in select.expressions:
            refs, unres = _plain_sources(projection.unalias(), scope,
                                         scope_tables, variables)
            refs, _ = _rewrite_refs(refs, inner_derived)
            add(values, refs)
            unresolved.extend(u for u in unres if u not in unresolved)
        for clause in _predicates(select):
            refs, _ = _plain_sources(clause, scope, scope_tables, variables)
            refs, _ = _rewrite_refs(refs, inner_derived)
            add(filters, refs)

    conditions = _case_conditions(expression)
    condition_columns = frozenset(
        id(column) for clause in conditions for column in clause.find_all(exp.Column))
    for clause in conditions:
        refs, _ = _plain_sources(clause, aliases, tables, variables)
        refs, _ = _rewrite_refs(refs, derived)
        add(filters, refs)

    refs, unres = _plain_sources(expression, aliases, tables, variables,
                                 condition_columns)
    refs, via_cte = _rewrite_refs(refs, derived)
    add(values, refs)
    unresolved.extend(u for u in unres if u not in unresolved)
    return values, unresolved, filters, via_cte


def _sql(expression: exp.Expression | None) -> str:
    if expression is None:
        return ""
    return " ".join(expression.sql(dialect="oracle").split())


# --- filters ------------------------------------------------------------------


def _filter_edges(scope: exp.Expression, target: str, aliases: dict[str, str],
                  tables: list[str], variables: frozenset[str],
                  derived: dict[str, Derived] | None = None,
                  catalog: dict[str, list[str]] | None = None,
                  diagnostics: list[tuple[str, str]] | None = None) -> list[Edge]:
    """Columns that decide which rows are affected, not what value is written.

    Each clause is rendered from its inner expression: a Where node's own sql()
    already begins with the keyword, so using it whole yields "WHERE WHERE ...".
    """
    clauses: list[tuple[str, exp.Expression | None]] = [
        ("WHERE", _inner(scope.args.get("where"))),
        ("GROUP BY", _inner(scope.args.get("group"))),
    ]
    for join in _scope_joins(scope):
        clauses.append(("JOIN", join.args.get("on")))

    edges: list[Edge] = []
    for label, clause in clauses:
        if clause is None:
            continue
        sources, _, _, _ = _sources(clause, aliases, tables, variables,
                                    derived, catalog, diagnostics)
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


def _note(diagnostics: list[tuple[str, str]] | None, code: str, message: str) -> None:
    if diagnostics is None:
        return
    item = (code, message)
    if item not in diagnostics:
        diagnostics.append(item)


def _is_star(node: exp.Expression) -> bool:
    value = node.unalias() if hasattr(node, "unalias") else node
    return isinstance(value, exp.Star) or (
        isinstance(value, exp.Column) and isinstance(value.this, exp.Star))


def _star_qualifier(node: exp.Expression) -> str | None:
    value = node.unalias() if hasattr(node, "unalias") else node
    if isinstance(value, exp.Column):
        return value.table or None
    return None


def _bind_derived(aliases: dict[str, str], derived: dict[str, Derived]) -> None:
    """Make CTE / subquery aliases resolvable as qualifiers."""
    for name in derived:
        aliases.setdefault(name, name)


def _rewrite_refs(refs: list[Ref], derived: dict[str, Derived]
                  ) -> tuple[list[Ref], bool]:
    """Replace CTE / USING aliases with the base-table columns behind them."""

    if not derived:
        return refs, False
    out: list[Ref] = []
    via_cte = False
    for ref in refs:
        rel = derived.get(ref.table.upper())
        if rel is None or ref.column is None:
            if ref not in out:
                out.append(ref)
            continue
        mapped = rel.columns.get(ref.column.upper())
        if not mapped:
            if ref not in out:
                out.append(ref)
            continue
        if rel.transport == "CTE":
            via_cte = True
        for source in mapped:
            if source not in out:
                out.append(source)
    return out, via_cte


def _value_kind(expression: exp.Expression, via_cte: bool) -> str:
    kind = _classify(expression)
    if via_cte and kind == DIRECT:
        return VIA_CTE
    return kind


def _scope_joins(scope: exp.Expression) -> list[exp.Join]:
    found: list[exp.Join] = []
    for join in scope.find_all(exp.Join):
        owner = join.find_ancestor(exp.Select)
        if isinstance(scope, exp.Select) and owner is not scope:
            continue
        found.append(join)
    return found


def _scope_subqueries(select: exp.Select) -> list[exp.Subquery]:
    found: list[exp.Subquery] = []
    for subquery in select.find_all(exp.Subquery):
        owner = subquery.find_ancestor(exp.Select)
        if owner is select:
            found.append(subquery)
    return found


def _refers_to(node: exp.Expression, name: str) -> bool:
    key = name.upper()
    return any(table.name.upper() == key for table in node.find_all(exp.Table))


def _star_owners(qualifier: str | None, aliases: dict[str, str],
                 tables: list[str]) -> list[str]:
    if qualifier:
        owner = aliases.get(qualifier.upper())
        return [owner] if owner else []
    seen: list[str] = []
    for table in tables:
        if table not in seen:
            seen.append(table)
    return seen


def _output_columns(select: exp.Select, aliases: dict[str, str],
                    tables: list[str], catalog: dict[str, list[str]],
                    diagnostics: list[tuple[str, str]],
                    insert_columns: list[str] | None
                    ) -> list[tuple[str | None, exp.Expression]]:
    """Projection list after expanding ``*`` / ``alias.*`` against the catalog."""

    expanded: list[tuple[str | None, exp.Expression]] = []
    for projection in select.expressions:
        if not _is_star(projection):
            name = projection.alias_or_name or None
            expanded.append((name, projection.unalias()))
            continue
        qualifier = _star_qualifier(projection)
        owners = _star_owners(qualifier, aliases, tables)
        if not owners:
            _note(diagnostics, "STAR_UNRESOLVED",
                  "SELECT * 대상을 알 수 없어 전개하지 못했습니다")
            continue
        for owner in owners:
            cols = columns_for(catalog, owner)
            if not cols:
                _note(diagnostics, "STAR_UNRESOLVED",
                      f"{owner} 의 컬럼 목록이 카탈로그에 없어 * 를 전개하지 못했습니다")
                continue
            for column in cols:
                table_alias = qualifier or owner
                expanded.append((column, exp.column(column, table=table_alias)))
    if insert_columns:
        paired: list[tuple[str | None, exp.Expression]] = []
        for index, column in enumerate(insert_columns):
            if index >= len(expanded):
                break
            paired.append((column, expanded[index][1]))
        return paired
    return expanded


def _collect_derived(select: exp.Select, variables: frozenset[str],
                     catalog: dict[str, list[str]],
                     diagnostics: list[tuple[str, str]],
                     inherited: dict[str, Derived] | None = None
                     ) -> dict[str, Derived]:
    """CTEs and FROM-subqueries visible in this select, keyed by alias."""

    derived: dict[str, Derived] = dict(inherited or {})
    with_ = select.args.get("with_")
    if isinstance(with_, exp.With):
        if with_.args.get("recursive"):
            _note(diagnostics, "UNSUPPORTED_CTE",
                  "recursive WITH 는 전개하지 않습니다")
        for cte in with_.expressions:
            if not isinstance(cte, exp.CTE):
                continue
            name = cte.alias
            body = cte.this
            if not name or body is None:
                continue
            if _refers_to(body, name):
                _note(diagnostics, "UNSUPPORTED_CTE",
                      f"recursive CTE {name} 는 전개하지 않습니다")
                continue
            if not isinstance(body, exp.Select):
                _note(diagnostics, "UNSUPPORTED_CTE",
                      f"CTE {name} 본문이 단일 SELECT 가 아니라 전개하지 않습니다")
                continue
            derived[name.upper()] = _derived_from_select(
                body, variables, catalog, diagnostics, derived, "CTE")
    for subquery in _scope_subqueries(select):
        alias = subquery.alias
        body = subquery.this
        if not alias or not isinstance(body, exp.Select):
            continue
        derived[alias.upper()] = _derived_from_select(
            body, variables, catalog, diagnostics, derived, "CTE")
    return derived


def _derived_from_select(select: exp.Select, variables: frozenset[str],
                         catalog: dict[str, list[str]],
                         diagnostics: list[tuple[str, str]],
                         inherited: dict[str, Derived],
                         transport: str) -> Derived:
    inner = _collect_derived(select, variables, catalog, diagnostics, inherited)
    aliases, tables = _alias_map(select, set(inner))
    columns: dict[str, list[Ref]] = {}
    for name, value in _output_columns(select, aliases, tables, catalog,
                                       diagnostics, None):
        if not name:
            continue
        sources, _, _, _ = _sources(value, aliases, tables, variables, inner,
                                    catalog, diagnostics)
        columns[name.upper()] = sources
    return Derived(columns=columns, transport=transport)


# --- statements ---------------------------------------------------------------


def _insert(statement: exp.Insert, variables: frozenset[str],
            catalog: dict[str, list[str]] | None = None,
            diagnostics: list[tuple[str, str]] | None = None) -> list[Edge]:
    catalog = catalog or {}
    diagnostics = diagnostics if diagnostics is not None else []
    table = statement.this
    columns: list[str] = []
    if isinstance(table, exp.Schema):
        columns = [c.name for c in table.expressions]
        table = table.this
    target = _table_name(table)

    select = statement.expression
    if isinstance(select, exp.Values):
        return _insert_values(target, columns, select, variables, catalog, diagnostics)
    if not isinstance(select, exp.Select):
        return []
    derived = _collect_derived(select, variables, catalog, diagnostics)
    aliases, tables = _alias_map(select, set(derived))
    _bind_derived(aliases, derived)
    if not columns:
        columns = columns_for(catalog, target)

    edges: list[Edge] = []
    for name, value in _output_columns(select, aliases, tables, catalog,
                                       diagnostics, columns or None):
        if not name:
            continue
        sources, unresolved, filters, via_cte = _sources(
            value, aliases, tables, variables, derived, catalog, diagnostics)
        kind = _value_kind(value, via_cte)
        if sources or unresolved:
            edges.append(Edge(Ref(target, name), sources, kind,
                              _sql(value), unresolved))
        # Emitted independently of the value edge: a condition still reaches the
        # target when every branch is constant, as in
        # CASE WHEN r.ITEM_CD IS NULL THEN SYSDATE ELSE SYSDATE END.
        correlated = [ref for ref in filters if ref.table != target]
        if correlated:
            edges.append(Edge(Ref(target, name), correlated, FILTER,
                              f"PREDICATE {_sql(value)}"))
    edges.extend(_filter_edges(select, target, aliases, tables, variables,
                               derived, catalog, diagnostics))
    return edges


def _insert_values(target: str, columns: list[str], values: exp.Values,
                   variables: frozenset[str],
                   catalog: dict[str, list[str]] | None = None,
                   diagnostics: list[tuple[str, str]] | None = None) -> list[Edge]:
    """INSERT ... VALUES - one row of expressions positionally matched to columns.

    There is no FROM clause, so a qualified reference is the only kind that can
    name a table; everything else is a literal, a sequence, or a PL/SQL name
    that layer C resolves later. Interface-table loads are written this way, and
    they sit exactly on the source-to-warehouse seam, so dropping them loses the
    join between two halves of a chain.
    """
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for row in values.expressions:
        items = row.expressions if isinstance(row, exp.Tuple) else [row]
        for index, value in enumerate(items):
            if index >= len(columns):
                break
            name = columns[index]
            sources, unresolved, filters, via_cte = _sources(
                value, {}, [], variables, None, catalog, diagnostics)
            if not sources and not unresolved:
                continue                # a constant carries no lineage
            key = (name.upper(), _sql(value))
            if key in seen:
                continue                # the same column in a second VALUES row
            seen.add(key)
            edges.append(Edge(Ref(target, name), sources, _value_kind(value, via_cte),
                              _sql(value), unresolved))
            if filters:
                edges.append(Edge(Ref(target, name), filters, FILTER,
                                  f"PREDICATE {_sql(value)}"))
    return edges


def _update(statement: exp.Update, variables: frozenset[str],
            catalog: dict[str, list[str]] | None = None,
            diagnostics: list[tuple[str, str]] | None = None) -> list[Edge]:
    catalog = catalog or {}
    diagnostics = diagnostics if diagnostics is not None else []
    target = _table_name(statement.this) if isinstance(statement.this, exp.Table) else ""
    if not target:
        return []
    derived: dict[str, Derived] = {}
    aliases, tables = _alias_map(statement, set(derived))
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
        sources, unresolved, filters, via_cte = _sources(
            value, aliases, tables, variables, derived, catalog, diagnostics)
        if sources or unresolved:
            edges.append(Edge(Ref(target, column.name), sources,
                              _value_kind(value, via_cte),
                              _sql(value), unresolved))
        correlated = [ref for ref in filters if ref.table != target]
        if correlated:
            edges.append(Edge(Ref(target, column.name), correlated, FILTER,
                              f"PREDICATE {_sql(value)}"))
    edges.extend(_filter_edges(statement, target, aliases, tables, variables,
                               derived, catalog, diagnostics))
    return edges


def _delete(statement: exp.Delete, variables: frozenset[str],
            catalog: dict[str, list[str]] | None = None,
            diagnostics: list[tuple[str, str]] | None = None) -> list[Edge]:
    if not isinstance(statement.this, exp.Table):
        return []
    target = _table_name(statement.this)
    aliases, tables = _alias_map(statement)
    return _filter_edges(statement, target, aliases, tables or [target],
                         variables, None, catalog, diagnostics)


def _select_into(statement: exp.Select,
                 variables: frozenset[str],
                 catalog: dict[str, list[str]] | None = None,
                 diagnostics: list[tuple[str, str]] | None = None
                 ) -> tuple[list[Edge], list[Binding]]:
    """SELECT ... INTO / BULK COLLECT INTO: fills names, not table columns.

    Writes no lineage edge on its own - the value has not reached a table yet.
    What it produces is a binding, so that when a later statement reads the
    name, layer C can rejoin the two halves into one edge.
    """
    catalog = catalog or {}
    diagnostics = diagnostics if diagnostics is not None else []
    into = statement.args.get("into")
    if into is None:
        return [], []

    derived = _collect_derived(statement, variables, catalog, diagnostics)
    aliases, tables = _alias_map(statement, set(derived))
    _bind_derived(aliases, derived)
    bulk = bool(into.args.get("bulk_collect"))
    targets = [node.name or node.sql() for node in (into.expressions or [])]
    if not targets and into.this is not None:
        targets = [into.this.name or into.this.sql()]

    bindings: list[Binding] = []
    pairs = _output_columns(statement, aliases, tables, catalog, diagnostics, None)

    if bulk and len(targets) == 1:
        # One collection receives whole rows: bind each projection as a field,
        # which is how it is read back (t_rows(i).UNIT_WGT).
        collection = targets[0]
        for name, value in pairs:
            if not name:
                continue
            sources, _, _, via_cte = _sources(
                value, aliases, tables, variables, derived, catalog, diagnostics)
            if sources:
                bindings.append(Binding(f"{collection}.{name}".upper(), sources,
                                        _value_kind(value, via_cte), _sql(value)))
        return [], bindings

    for index, target in enumerate(targets):
        if index >= len(pairs):
            break
        value = pairs[index][1]
        sources, _, _, via_cte = _sources(
            value, aliases, tables, variables, derived, catalog, diagnostics)
        if sources:
            bindings.append(Binding(target.upper(), sources,
                                    _value_kind(value, via_cte), _sql(value)))
    return [], bindings


def _merge_insert_parts(insert: exp.Insert) -> tuple[list[str], list[exp.Expression]]:
    this, expression = insert.this, insert.expression
    columns: list[str] = []
    values: list[exp.Expression] = []
    if isinstance(this, exp.Tuple):
        columns = [c.name for c in this.expressions if isinstance(c, (exp.Column, exp.Identifier))]
    elif isinstance(this, exp.Schema):
        columns = [c.name for c in this.expressions]
        if isinstance(this.this, exp.Tuple):
            columns = [c.name for c in this.this.expressions]
    if isinstance(expression, exp.Tuple):
        values = list(expression.expressions)
    elif isinstance(expression, exp.Values):
        row = expression.expressions[0] if expression.expressions else None
        if isinstance(row, exp.Tuple):
            values = list(row.expressions)
        elif row is not None:
            values = [row]
    return columns, values


def _merge(statement: exp.Merge, variables: frozenset[str],
           catalog: dict[str, list[str]] | None = None,
           diagnostics: list[tuple[str, str]] | None = None) -> list[Edge]:
    """MERGE INTO ... USING ... ON ... WHEN MATCHED / NOT MATCHED."""

    catalog = catalog or {}
    diagnostics = diagnostics if diagnostics is not None else []
    if not isinstance(statement.this, exp.Table):
        return []
    target = _table_name(statement.this)
    derived: dict[str, Derived] = {}
    aliases: dict[str, str] = {target.upper(): target}
    tables: list[str] = [target]
    if statement.this.alias:
        aliases[statement.this.alias.upper()] = target

    using = statement.args.get("using")
    using_select: exp.Select | None = None
    if isinstance(using, exp.Subquery):
        using_select = using.this if isinstance(using.this, exp.Select) else None
        alias = using.alias
        if using_select is not None and alias:
            derived[alias.upper()] = _derived_from_select(
                using_select, variables, catalog, diagnostics, {}, "DERIVED")
            aliases[alias.upper()] = alias
    elif isinstance(using, exp.Table):
        name = _table_name(using)
        tables.append(name)
        aliases[name.upper()] = name
        aliases[using.name.upper()] = name
        if using.alias:
            aliases[using.alias.upper()] = name

    _bind_derived(aliases, derived)
    edges: list[Edge] = []
    whens = statement.args.get("whens")
    when_list = whens.expressions if isinstance(whens, exp.Whens) else []
    for when in when_list:
        then = when.args.get("then") if isinstance(when, exp.When) else None
        if isinstance(then, exp.Update):
            for assignment in then.expressions:
                if not isinstance(assignment, exp.EQ):
                    continue
                column = assignment.this
                if not isinstance(column, exp.Column):
                    continue
                value = assignment.expression
                sources, unresolved, filters, via_cte = _sources(
                    value, aliases, tables, variables, derived, catalog, diagnostics)
                if sources or unresolved:
                    edges.append(Edge(Ref(target, column.name), sources,
                                      _value_kind(value, via_cte),
                                      _sql(value), unresolved))
                correlated = [ref for ref in filters if ref.table != target]
                if correlated:
                    edges.append(Edge(Ref(target, column.name), correlated, FILTER,
                                      f"PREDICATE {_sql(value)}"))
        elif isinstance(then, exp.Insert):
            columns, values = _merge_insert_parts(then)
            for index, name in enumerate(columns):
                if index >= len(values):
                    break
                value = values[index]
                sources, unresolved, filters, via_cte = _sources(
                    value, aliases, tables, variables, derived, catalog, diagnostics)
                if not sources and not unresolved:
                    continue
                edges.append(Edge(Ref(target, name), sources,
                                  _value_kind(value, via_cte),
                                  _sql(value), unresolved))
                if filters:
                    edges.append(Edge(Ref(target, name), filters, FILTER,
                                      f"PREDICATE {_sql(value)}"))

    on = statement.args.get("on")
    if on is not None:
        sources, _, _, _ = _sources(on, aliases, tables, variables,
                                    derived, catalog, diagnostics)
        if sources:
            edges.append(Edge(Ref(target, None), sources, FILTER,
                              f"MERGE ON {_sql(on)}"))
    if using_select is not None:
        inner = _collect_derived(using_select, variables, catalog, diagnostics)
        inner_aliases, inner_tables = _alias_map(using_select, set(inner))
        _bind_derived(inner_aliases, inner)
        edges.extend(_filter_edges(using_select, target, inner_aliases,
                                   inner_tables, variables, inner, catalog,
                                   diagnostics))
    return edges


_HANDLERS = {
    exp.Insert: _insert,
    exp.Update: _update,
    exp.Delete: _delete,
    exp.Merge: _merge,
}


def analyze_projections(sql: str,
                        variables: frozenset[str] = frozenset(),
                        catalog: dict[str, list[str]] | None = None
                        ) -> list[tuple[str, list[Ref], str]]:
    """Each output column of a SELECT, with the base-table columns behind it.

    Used for queries that write no table - a cursor a loop record is drawn
    from - where the projection *is* the lineage.
    """
    catalog = catalog or {}
    diagnostics: list[tuple[str, str]] = []
    try:
        tree = sqlglot.parse_one(sql, dialect="oracle")
    except Exception:
        return []
    if not isinstance(tree, exp.Select):
        return []

    derived = _collect_derived(tree, variables, catalog, diagnostics)
    aliases, tables = _alias_map(tree, set(derived))
    _bind_derived(aliases, derived)
    out: list[tuple[str, list[Ref], str]] = []
    for name, value in _output_columns(tree, aliases, tables, catalog,
                                       diagnostics, None):
        if not name:
            continue
        sources, _, _, via_cte = _sources(
            value, aliases, tables, variables, derived, catalog, diagnostics)
        if sources:
            out.append((name, sources, _value_kind(value, via_cte)))
    return out


def analyze(sql: str, variables: frozenset[str] = frozenset(),
            catalog: dict[str, list[str]] | None = None) -> StatementLineage:
    """Column lineage for one SQL statement.

    ``variables`` are the PL/SQL names in scope - pass them, or bare identifiers
    become invented columns on the target table.
    """
    catalog = catalog or {}
    diagnostics: list[tuple[str, str]] = []
    try:
        tree = sqlglot.parse_one(sql, dialect="oracle")
    except Exception as exc:
        return StatementLineage(error=f"{type(exc).__name__}: {exc}")
    if tree is None or isinstance(tree, exp.Command):
        return StatementLineage(error="unsupported statement")

    if isinstance(tree, exp.Select):
        if tree.args.get("into") is None:
            return StatementLineage(error="unhandled: Select")
        edges, bindings = _select_into(tree, variables, catalog, diagnostics)
        return StatementLineage(edges=edges, bindings=bindings,
                                diagnostics=diagnostics)

    handler = _HANDLERS.get(type(tree))
    if handler is None:
        return StatementLineage(error=f"unhandled: {type(tree).__name__}")
    return StatementLineage(edges=handler(tree, variables, catalog, diagnostics),
                            diagnostics=diagnostics)
