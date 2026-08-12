"""IR model, PL/SQL renderer, and lineage extractor.

Design principle 1 of the plan (Generate-from-Truth): a single IR is the only
source of both artifacts.

    IR --render()--> PL/SQL text
       --edges()---> lineage truth

Expressions are modelled as *template + reference list* rather than a full AST.
Rendering is ``template.format(*refs)``; lineage is the reference list. That is
exact for both directions at a fraction of the cost of a real expression tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- edge kinds ---------------------------------------------------------------

DIRECT = "DIRECT"
TRANSFORM = "TRANSFORM"
AGGREGATE = "AGGREGATE"
ANALYTIC = "ANALYTIC"
INDIRECT_FILTER = "INDIRECT_FILTER"
VIA_VARIABLE = "VIA_VARIABLE"
VIA_CTE = "VIA_CTE"
UNRESOLVED = "UNRESOLVED"

# --- EAI additions ---
# The EAI layer needs three kinds the SQL layer has no use for. They live here
# rather than in syneai/ so both generators, the validator and the scorer share
# one vocabulary and one merged truth file.
VIA_PIPELINE = "VIA_PIPELINE"   # carried through the webMethods pipeline
CONSTANT = "CONSTANT"           # literal assignment - a target with no source
SEVERED = "SEVERED"             # lineage deliberately ends here

#: VIA_PIPELINE counts as a value-carrying kind so a merged chain can cross the
#: EAI segment. CONSTANT and SEVERED carry no value and stay out.
VALUE_KINDS = (DIRECT, TRANSFORM, AGGREGATE, ANALYTIC, VIA_VARIABLE, VIA_CTE,
               VIA_PIPELINE)

NON_VALUE_KINDS = (INDIRECT_FILTER, UNRESOLVED, CONSTANT, SEVERED)


def esc(text: str) -> str:
    """Escape a raw SQL fragment so it survives ``str.format``."""

    return text.replace("{", "{{").replace("}", "}}")


# --- references ---------------------------------------------------------------


@dataclass(frozen=True)
class ColRef:
    """A column reference. ``table`` is a fully qualified table, a CTE name, or
    an inline-view alias; ``alias`` is what actually gets printed."""

    table: str
    column: str
    alias: str | None = None

    def sql(self) -> str:
        return f"{self.alias}.{self.column}" if self.alias else self.column


@dataclass(frozen=True)
class Var:
    name: str

    def sql(self) -> str:
        return self.name


@dataclass(frozen=True)
class Lit:
    text: str

    def sql(self) -> str:
        return self.text


@dataclass(frozen=True)
class Star:
    """``alias.*`` - only resolvable against the DDL catalog."""

    table: str
    alias: str | None = None

    def sql(self) -> str:
        return f"{self.alias}.*" if self.alias else "*"


@dataclass(frozen=True)
class ScalarSubquery:
    """A single-column correlated subquery used as a value expression."""

    select: "Select"

    def sql(self) -> str:
        return "(" + render_select(self.select, inline=True) + ")"


Ref = ColRef | Var | Lit | Star | ScalarSubquery


# --- expressions --------------------------------------------------------------


@dataclass(frozen=True)
class Expr:
    template: str
    refs: tuple[Ref, ...] = ()
    kind: str = DIRECT
    cond_refs: tuple[Ref, ...] = ()

    def parts(self) -> tuple[Ref, ...]:
        return tuple(self.refs) + tuple(self.cond_refs)

    def sql(self) -> str:
        parts = self.parts()
        if not parts:
            return self.template
        return self.template.format(*[r.sql() for r in parts])


def e_col(ref: ColRef) -> Expr:
    return Expr("{0}", (ref,), DIRECT)


def e_lit(text: str) -> Expr:
    return Expr(esc(text), (), DIRECT)


def cond(template: str, *refs: Ref) -> Expr:
    return Expr(template, tuple(refs), INDIRECT_FILTER)


# --- query model --------------------------------------------------------------


@dataclass
class TableRef:
    table: str | None = None
    alias: str = "a"
    subquery: "Select | None" = None
    join: str | None = None  # None = first entry / comma join
    on: tuple[Expr, ...] = ()
    pivot: str | None = None  # raw PIVOT(...) clause text
    transparent: bool = False  # derived source that adds no lineage hop (MERGE USING)

    def source_sql(self) -> str:
        return self.table if self.table else "(inline)"


@dataclass
class Select:
    items: list[tuple[str | None, Expr]] = field(default_factory=list)
    tables: list[TableRef] = field(default_factory=list)
    where: list[Expr] = field(default_factory=list)
    group_by: list[Ref] = field(default_factory=list)
    having: list[Expr] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    ctes: list[tuple[str, "Select"]] = field(default_factory=list)
    start_with: list[Expr] = field(default_factory=list)
    connect_by: list[Expr] = field(default_factory=list)
    hint: str | None = None
    distinct: bool = False
    old_style_join: bool = False

    def sub_sources(self) -> dict[str, tuple["Select", bool]]:
        """Name -> (sub-select, transparent). Transparent sources are derived
        tables that do not count as a lineage hop, such as MERGE ... USING."""

        m: dict[str, tuple[Select, bool]] = {name: (sub, False) for name, sub in self.ctes}
        for t in self.tables:
            if t.subquery is not None:
                m[t.alias] = (t.subquery, t.transparent)
        return m

    def filter_exprs(self) -> list[tuple[str, Expr]]:
        out: list[tuple[str, Expr]] = []
        for t in self.tables:
            for c in t.on:
                out.append(("JOIN", c))
        for c in self.where:
            out.append(("WHERE", c))
        for c in self.having:
            out.append(("HAVING", c))
        for c in self.start_with:
            out.append(("START WITH", c))
        for c in self.connect_by:
            out.append(("CONNECT BY", c))
        return out


# --- statements ---------------------------------------------------------------


@dataclass
class Stmt:
    sid: int = field(default=0, init=False, repr=False)
    comment: str | None = field(default=None, kw_only=True)


@dataclass
class InsertSelect(Stmt):
    target: str
    columns: list[str] | None
    select: Select
    hint: str | None = None


@dataclass
class InsertValues(Stmt):
    target: str
    columns: list[str]
    values: list[Expr]


@dataclass
class Update(Stmt):
    target: str
    alias: str
    sets: list[tuple[str, Expr]]
    where: list[Expr] = field(default_factory=list)
    hint: str | None = None


@dataclass
class Delete(Stmt):
    target: str
    alias: str
    where: list[Expr] = field(default_factory=list)


@dataclass
class Merge(Stmt):
    target: str
    alias: str
    using: Select
    using_alias: str
    on: list[Expr]
    update_sets: list[tuple[str, Expr]]
    insert_columns: list[str]
    insert_values: list[Expr]
    hint: str | None = None


@dataclass
class SelectInto(Stmt):
    targets: list[str]
    select: Select
    bulk: bool = False


@dataclass
class ExecImmediate(Stmt):
    assign_lines: list[str]
    target_hint: str | None = None
    using: list[str] = field(default_factory=list)
    reason: str = "동적 SQL - 객체명이 변수로 결정되어 정적 해석 불가"


@dataclass
class OpenRefCursor(Stmt):
    out_param: str
    select: Select


@dataclass
class CursorLoop(Stmt):
    record: str
    select: Select
    body: list[Stmt] = field(default_factory=list)
    cursor_name: str | None = None  # set => declared cursor, FOR rec IN c_name


@dataclass
class ForAll(Stmt):
    collection: str
    index: str
    body: Stmt = None  # type: ignore[assignment]


@dataclass
class IfBlock(Stmt):
    condition: str
    body: list[Stmt] = field(default_factory=list)
    else_body: list[Stmt] = field(default_factory=list)
    elsif: list[tuple[str, list[Stmt]]] = field(default_factory=list)


@dataclass
class Assign(Stmt):
    """``v_x := <expr>;`` - propagates lineage into a PL/SQL variable."""

    target: str
    expr: "Expr"
    accumulate: bool = False


@dataclass
class ForLoop(Stmt):
    """Plain numeric FOR loop; the FORALL-free variant of a bulk apply."""

    index: str
    bound: str
    body: list[Stmt] = field(default_factory=list)


@dataclass
class Raw(Stmt):
    lines: list[str] = field(default_factory=list)


CONTAINER_FIELDS = {
    CursorLoop: ("body",),
    IfBlock: ("body", "else_body"),
}


def walk(stmts: list[Stmt]):
    """Depth-first statement walk. Render and extract must use the same order."""

    for s in stmts:
        yield s
        if isinstance(s, IfBlock):
            yield from walk(s.body)
            for _, blk in s.elsif:
                yield from walk(blk)
            yield from walk(s.else_body)
        elif isinstance(s, CursorLoop):
            yield from walk(s.body)
        elif isinstance(s, ForAll) and s.body is not None:
            yield from walk([s.body])
        elif isinstance(s, ForLoop):
            yield from walk(s.body)


# --- program units ------------------------------------------------------------


@dataclass
class Param:
    name: str
    mode: str
    dtype: str


@dataclass
class Subprogram:
    name: str
    kind: str  # PROCEDURE | FUNCTION
    params: list[Param] = field(default_factory=list)
    return_type: str | None = None
    decls: list[str] = field(default_factory=list)
    stmts: list[Stmt] = field(default_factory=list)
    comment: str = ""
    autonomous: bool = False
    tail: list[str] = field(default_factory=list)


@dataclass
class Package:
    schema: str
    name: str
    comment: str
    subprograms: list[Subprogram] = field(default_factory=list)
    tier: int = 0
    scenarios: list[str] = field(default_factory=list)

    @property
    def fq(self) -> str:
        return f"{self.schema}.{self.name}"


# --- rendering ----------------------------------------------------------------


class Block:
    """Rendered lines plus anchor keys pointing at line offsets."""

    __slots__ = ("lines", "anchors", "_last")

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.anchors: dict[str, int] = {}
        self._last: int = 0

    def add(self, text: str = "") -> int:
        """Append text and return the index of its *first* physical line.

        Rendered fragments legitimately contain newlines - a multi-parameter
        subprogram signature, a multi-branch CASE expression. Appending such a
        fragment as one entry would make every later line number too small, so
        it is split here and the caller anchors on the first line.
        """

        start = len(self.lines)
        if "\n" in text:
            self.lines.extend(text.split("\n"))
        else:
            self.lines.append(text)
        self._last = start
        return start

    def mark(self, key: str, index: int | None = None) -> None:
        self.anchors[key] = self._last if index is None else index

    def merge(self, other: "Block", indent: int = 0) -> None:
        off = len(self.lines)
        pad = " " * indent
        for line in other.lines:
            self.lines.append(pad + line if line else line)
        for k, v in other.anchors.items():
            self.anchors[k] = v + off


def _pad(name: str, width: int) -> str:
    return name.ljust(width)


def _drop_item_anchors(block: "Block") -> "Block":
    """Remove a nested select's projection anchors before merging it upward.

    ``item:N`` keys are positional and local to one projection list. Letting an
    inline view's keys reach the enclosing block would silently overwrite the
    outer projection's anchors, and every edge of the outer statement would then
    point into the subquery instead.
    """

    block.anchors = {k: v for k, v in block.anchors.items()
                     if not k.startswith("item:")}
    return block


def pred_key(sid: int, text: str) -> str:
    """Anchor key for one predicate, so a WHERE/JOIN edge can point at the line
    that actually carries it instead of at the head of the statement."""

    return f"{sid}:pred:{' '.join(text.split())}"


def render_select(sel: Select, indent: int = 0, inline: bool = False,
                  sid: int = 0) -> str | Block:
    """Render a SELECT. ``inline=True`` collapses it to a single line."""

    if inline:
        return _render_select_inline(sel)
    b = Block()
    _render_select_block(sel, b, sid)
    if indent:
        shifted = Block()
        shifted.merge(b, indent)
        return shifted
    return b


def _render_select_inline(sel: Select) -> str:
    items = ", ".join(_item_sql(name, expr) for name, expr in sel.items)
    parts = [f"SELECT {items}", f"FROM {_from_inline(sel)}"]
    conds = [c.sql() for c in sel.where]
    for t in sel.tables:
        if sel.old_style_join or t.join is None:
            conds = [c.sql() for c in t.on] + conds
    if conds:
        parts.append("WHERE " + " AND ".join(conds))
    if sel.group_by:
        parts.append("GROUP BY " + ", ".join(r.sql() for r in sel.group_by))
    return " ".join(parts)


def _from_inline(sel: Select) -> str:
    chunks = []
    for t in sel.tables:
        src = t.table if t.table else "(" + _render_select_inline(t.subquery) + ")"
        if t.join and not sel.old_style_join:
            on = " AND ".join(c.sql() for c in t.on)
            chunks.append(f"{t.join} {src} {t.alias} ON ({on})")
        else:
            chunks.append(f"{src} {t.alias}" if not chunks else f", {src} {t.alias}")
    return " ".join(chunks).replace(" , ", ", ")


def _item_sql(name: str | None, expr: Expr) -> str:
    text = expr.sql()
    if name and not text.endswith("*"):
        return f"{text} AS {name}"
    return text


def _render_select_block(sel: Select, b: Block, sid: int = 0) -> None:
    if sel.ctes:
        for i, (name, sub) in enumerate(sel.ctes):
            head = "WITH " if i == 0 else "   , "
            b.add(f"{head}{name} AS (")
            inner = Block()
            _render_select_block(sub, inner, sid)
            b.merge(_drop_item_anchors(inner), 8)
            b.add("     )")

    head = "SELECT"
    if sel.hint:
        head += f" /*+ {sel.hint} */"
    if sel.distinct:
        head += " DISTINCT"
    b.add(head)

    for i, (name, expr) in enumerate(sel.items):
        sep = "," if i < len(sel.items) - 1 else ""
        text = expr.sql()
        if name and not text.endswith("*"):
            text = f"{text} AS {name}"
        b.mark(f"item:{i}", b.add(f"       {text}{sep}"))

    pending = _render_from(sel, b, sid)

    predicates = pending + [(c.sql(), c.sql()) for c in sel.where]
    for i, (text, source_text) in enumerate(predicates):
        kw = " WHERE" if i == 0 else "   AND"
        b.anchors[pred_key(sid, source_text)] = b.add(f"{kw} {text}")
    for c in sel.start_with:
        b.anchors[pred_key(sid, c.sql())] = len(b.lines)
    if sel.start_with:
        b.add(" START WITH " + " AND ".join(c.sql() for c in sel.start_with))
    for c in sel.connect_by:
        b.anchors[pred_key(sid, c.sql())] = len(b.lines)
    if sel.connect_by:
        b.add(" CONNECT BY " + " AND ".join(c.sql() for c in sel.connect_by))
    if sel.group_by:
        group_text = ", ".join(r.sql() for r in sel.group_by)
        b.anchors[pred_key(sid, group_text)] = b.add(" GROUP BY " + group_text)
    for c in sel.having:
        b.anchors[pred_key(sid, c.sql())] = len(b.lines)
    if sel.having:
        b.add(" HAVING " + " AND ".join(c.sql() for c in sel.having))
    if sel.order_by:
        b.add(" ORDER BY " + ", ".join(sel.order_by))


def _render_from(sel: Select, b: Block, sid: int = 0) -> list[tuple[str, str]]:
    """Render the FROM clause.

    Returns ``(rendered, original)`` predicate pairs that belong in WHERE:
    old-style comma joins carry their conditions there, with ``(+)`` markers, so
    the rendered text differs from the expression the lineage edge was built
    from and both are needed - one to print, one to anchor on.
    """

    pending: list[tuple[str, str]] = []
    first = True
    for t in sel.tables:
        if t.subquery is not None:
            b.add("  FROM (" if first else "     , (")
            inner = Block()
            _render_select_block(t.subquery, inner, sid)
            b.merge(_drop_item_anchors(inner), 8)
            b.add(f"       ) {t.alias}" + (f" {t.pivot}" if t.pivot else ""))
            first = False
            for c in t.on:
                pending.append((c.sql(), c.sql()))
            continue

        src = t.table
        if first:
            b.add(f"  FROM {src} {t.alias}")
            first = False
            for c in t.on:
                pending.append((c.sql(), c.sql()))
            continue

        if sel.old_style_join or t.join is None:
            b.add(f"     , {src} {t.alias}")
            for c in t.on:
                pending.append((_outer_marker(c, t), c.sql()))
        else:
            b.add(f"  {t.join} {src} {t.alias}")
            on_text = " AND ".join(c.sql() for c in t.on)
            line = b.add(f"    ON ({on_text})")
            for c in t.on:
                b.anchors[pred_key(sid, c.sql())] = line

    return pending


def _outer_marker(c: Expr, t: TableRef) -> str:
    """Render an old-style join predicate, adding ``(+)`` on the outer side."""

    text = c.sql()
    if not t.join or "LEFT" not in t.join:
        return text
    left, _, right = text.partition(" = ")
    if right and left.startswith(f"{t.alias}."):
        return f"{left}(+) = {right}"
    if right:
        return f"{left} = {right}(+)"
    return text


def render_stmt(s: Stmt) -> Block:
    b = Block()
    if s.comment:
        for line in s.comment.splitlines():
            b.add(f"-- {line}")
    # Statement-level fallback anchor: some edges (a MERGE ON predicate on a
    # key-only upsert, for instance) have no column line of their own.
    b.anchors[f"{s.sid}:stmt"] = len(b.lines)

    if isinstance(s, InsertSelect):
        _render_insert_select(s, b)
    elif isinstance(s, InsertValues):
        _render_insert_values(s, b)
    elif isinstance(s, Update):
        _render_update(s, b)
    elif isinstance(s, Delete):
        _render_delete(s, b)
    elif isinstance(s, Merge):
        _render_merge(s, b)
    elif isinstance(s, SelectInto):
        _render_select_into(s, b)
    elif isinstance(s, ExecImmediate):
        _render_exec_immediate(s, b)
    elif isinstance(s, OpenRefCursor):
        _render_open_ref_cursor(s, b)
    elif isinstance(s, CursorLoop):
        _render_cursor_loop(s, b)
    elif isinstance(s, ForAll):
        _render_forall(s, b)
    elif isinstance(s, ForLoop):
        _render_for_loop(s, b)
    elif isinstance(s, Assign):
        b.anchors[f"{s.sid}:var"] = b.add(f"{s.target} := {s.expr.sql()};")
    elif isinstance(s, IfBlock):
        _render_if(s, b)
    elif isinstance(s, Raw):
        for line in s.lines:
            b.add(line)
    else:  # pragma: no cover - defensive
        raise TypeError(f"unrenderable statement: {type(s).__name__}")
    return b


def _render_column_list(columns: list[str], b: Block, open_text: str) -> None:
    b.add(f"{open_text} (")
    for i, c in enumerate(columns):
        sep = "," if i < len(columns) - 1 else ""
        b.add(f"       {c}{sep}")
    b.add("     )")


def _terminate(b: Block) -> None:
    """Attach the statement terminator to the last rendered line."""

    if b.lines:
        b.lines[-1] = b.lines[-1] + ";"
    else:
        b.add(";")


def _render_insert_select(s: InsertSelect, b: Block) -> None:
    hint = f" /*+ {s.hint} */" if s.hint else ""
    if s.columns:
        _render_column_list(s.columns, b, f"INSERT{hint} INTO {s.target}")
    else:
        b.add(f"INSERT{hint} INTO {s.target}")
    sub = Block()
    _render_select_block(s.select, sub, s.sid)
    base = len(b.lines)
    b.merge(sub)
    for key, value in sub.anchors.items():
        if key.startswith(f"{s.sid}:"):
            b.anchors[key] = value + base
    for i, _ in enumerate(s.select.items):
        key = f"item:{i}"
        if key in sub.anchors:
            b.anchors[f"{s.sid}:col:{i}"] = sub.anchors[key] + base
    _terminate(b)


def _render_insert_values(s: InsertValues, b: Block) -> None:
    _render_column_list(s.columns, b, f"INSERT INTO {s.target}")
    b.add("VALUES (")
    for i, v in enumerate(s.values):
        sep = "," if i < len(s.values) - 1 else ""
        b.anchors[f"{s.sid}:col:{i}"] = b.add(f"       {v.sql()}{sep}")
    b.add("     );")


def _render_update(s: Update, b: Block) -> None:
    hint = f" /*+ {s.hint} */" if s.hint else ""
    b.add(f"UPDATE{hint} {s.target} {s.alias}")
    width = max(len(c) for c, _ in s.sets) if s.sets else 0
    for i, (colname, expr) in enumerate(s.sets):
        kw = "   SET" if i == 0 else "      "
        sep = "," if i < len(s.sets) - 1 else ""
        b.anchors[f"{s.sid}:col:{i}"] = b.add(
            f"{kw} {s.alias}.{_pad(colname, width)} = {expr.sql()}{sep}")
    for i, c in enumerate(s.where):
        kw = " WHERE" if i == 0 else "   AND"
        b.anchors[pred_key(s.sid, c.sql())] = b.add(f"{kw} {c.sql()}")
    _terminate(b)


def _render_delete(s: Delete, b: Block) -> None:
    b.add(f"DELETE FROM {s.target} {s.alias}")
    for i, c in enumerate(s.where):
        kw = " WHERE" if i == 0 else "   AND"
        b.anchors[pred_key(s.sid, c.sql())] = b.add(f"{kw} {c.sql()}")
    _terminate(b)


def _render_merge(s: Merge, b: Block) -> None:
    hint = f" /*+ {s.hint} */" if s.hint else ""
    b.add(f"MERGE{hint} INTO {s.target} {s.alias}")
    b.add("USING (")
    inner = Block()
    _render_select_block(s.using, inner, s.sid)
    _drop_item_anchors(inner)
    base = len(b.lines)
    b.merge(inner, 6)
    for key, value in inner.anchors.items():
        if key.startswith(f"{s.sid}:"):
            b.anchors[key] = value + base
    b.add(f"     ) {s.using_alias}")
    on_line = b.add("    ON (" + (" AND ".join(c.sql() for c in s.on)) + ")")
    for c in s.on:
        b.anchors[pred_key(s.sid, c.sql())] = on_line
    b.add("WHEN MATCHED THEN")
    b.add("  UPDATE SET")
    width = max([len(c) for c, _ in s.update_sets] + [0])
    for i, (colname, expr) in enumerate(s.update_sets):
        sep = "," if i < len(s.update_sets) - 1 else ""
        b.anchors[f"{s.sid}:upd:{i}"] = b.add(
            f"    {s.alias}.{_pad(colname, width)} = {expr.sql()}{sep}")
    b.add("WHEN NOT MATCHED THEN")
    b.add("  INSERT (")
    for i, c in enumerate(s.insert_columns):
        sep = "," if i < len(s.insert_columns) - 1 else ""
        b.add(f"       {c}{sep}")
    b.add("     )")
    b.add("  VALUES (")
    for i, v in enumerate(s.insert_values):
        sep = "," if i < len(s.insert_values) - 1 else ""
        b.anchors[f"{s.sid}:ins:{i}"] = b.add(f"       {v.sql()}{sep}")
    b.add("     );")


def _render_select_into(s: SelectInto, b: Block) -> None:
    sub = Block()
    _render_select_block(s.select, sub, s.sid)
    into_kw = "  BULK COLLECT INTO " if s.bulk else "  INTO "
    # INTO goes right after the projection list, before FROM.
    from_at = next((i for i, line in enumerate(sub.lines) if line.startswith("  FROM")), len(sub.lines))
    sub.lines.insert(from_at, into_kw + ", ".join(s.targets))
    for k, v in list(sub.anchors.items()):
        if v >= from_at:
            sub.anchors[k] = v + 1
    base = len(b.lines)
    b.merge(sub)
    for i, _ in enumerate(s.select.items):
        key = f"item:{i}"
        if key in sub.anchors:
            b.anchors[f"{s.sid}:col:{i}"] = sub.anchors[key] + base
    _terminate(b)


def _render_exec_immediate(s: ExecImmediate, b: Block) -> None:
    for line in s.assign_lines:
        b.add(line)
    using = ""
    if s.using:
        using = " USING " + ", ".join(s.using)
    b.anchors[f"{s.sid}:dyn"] = b.add(f"EXECUTE IMMEDIATE v_sql{using};")


def _render_open_ref_cursor(s: OpenRefCursor, b: Block) -> None:
    b.add(f"OPEN {s.out_param} FOR")
    sub = Block()
    _render_select_block(s.select, sub, s.sid)
    base = len(b.lines)
    b.merge(sub)
    for i, _ in enumerate(s.select.items):
        key = f"item:{i}"
        if key in sub.anchors:
            b.anchors[f"{s.sid}:cur:{i}"] = sub.anchors[key] + base
    _terminate(b)


def _render_cursor_loop(s: CursorLoop, b: Block) -> None:
    if s.cursor_name:
        b.add(f"FOR {s.record} IN {s.cursor_name} LOOP")
    else:
        b.add(f"FOR {s.record} IN (")
        sub = Block()
        _render_select_block(s.select, sub, s.sid)
        base = len(b.lines)
        b.merge(sub, 2)
        for i, _ in enumerate(s.select.items):
            key = f"item:{i}"
            if key in sub.anchors:
                b.anchors[f"{s.sid}:cur:{i}"] = sub.anchors[key] + base
        b.add(") LOOP")
    for st in s.body:
        inner = render_stmt(st)
        b.merge(inner, 2)
        b.add("")
    while b.lines and b.lines[-1] == "":
        b.lines.pop()
    b.add("END LOOP;")


def _render_forall(s: ForAll, b: Block) -> None:
    b.add(f"FORALL {s.index} IN 1 .. {s.collection}.COUNT")
    inner = render_stmt(s.body)
    b.merge(inner, 2)


def _render_for_loop(s: ForLoop, b: Block) -> None:
    b.add(f"FOR {s.index} IN 1 .. {s.bound} LOOP")
    for st in s.body:
        b.merge(render_stmt(st), 2)
    b.add("END LOOP;")


def _render_if(s: IfBlock, b: Block) -> None:
    b.add(f"IF {s.condition} THEN")
    for st in s.body:
        b.merge(render_stmt(st), 2)
    for cond_text, blk in s.elsif:
        b.add(f"ELSIF {cond_text} THEN")
        for st in blk:
            b.merge(render_stmt(st), 2)
    if s.else_body:
        b.add("ELSE")
        for st in s.else_body:
            b.merge(render_stmt(st), 2)
    b.add("END IF;")


# --- lineage extraction -------------------------------------------------------


@dataclass
class Edge:
    target_table: str
    target_column: str | None
    sources: list[tuple[str, str]]
    kind: str
    transform: str
    hops: int = 1
    via: list[str] = field(default_factory=list)
    anchor: str | None = None
    note: str | None = None


@dataclass
class RefCursorProjection:
    out_param: str
    columns: list[tuple[str, list[tuple[str, str]], str]]
    anchor: str | None = None


class ProcContext:
    """Per-subprogram variable bindings produced by SELECT INTO / FETCH."""

    def __init__(self) -> None:
        self.var_sources: dict[str, list[tuple[str, str, int]]] = {}
        self.ref_cursors: list[RefCursorProjection] = []

    def bind(self, name: str, sources: list[tuple[str, str, int]]) -> None:
        if sources:
            self.var_sources[name] = sources

    def copy(self) -> "ProcContext":
        c = ProcContext()
        c.var_sources = dict(self.var_sources)
        c.ref_cursors = self.ref_cursors
        return c


def _dedup(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for p in pairs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_ref(ref: Ref, sel: Select | None, ctx: ProcContext,
                catalog: dict | None = None, depth: int = 0) -> list[tuple[str, str, str | None, int]]:
    """Resolve one reference to base-table columns.

    Returns ``(table, column, transport, extra_hops)`` tuples, where transport is
    ``None`` for a plain base-table column, ``"CTE"`` when the value travelled
    through a CTE / inline view, ``"DERIVED"`` through a MERGE ... USING
    projection, and ``"VARIABLE"`` through a PL/SQL variable.
    """

    if depth > 8:
        return []

    if isinstance(ref, ColRef):
        subs = sel.sub_sources() if sel is not None else {}
        entry = subs.get(ref.table)
        if entry is None:
            return [(ref.table, ref.column, None, 0)]
        sub, transparent = entry
        # A transparent source (MERGE ... USING) is not a lineage hop, but the
        # value still travelled through a derived projection: recording that as
        # DERIVED keeps the edge kind honest while telling consumers that the
        # source column name will not appear in the outer expression text.
        bump = 0 if transparent else 1
        label = "DERIVED" if transparent else "CTE"
        out: list[tuple[str, str, str | None, int]] = []
        for name, expr in sub.items:
            if name == ref.column:
                for r in expr.refs:
                    for t, c, tr, h in resolve_ref(r, sub, ctx, catalog, depth + 1):
                        out.append((t, c, tr or label, h + bump))
                return out
        # not projected by name: fall back to a star projection
        for _, expr in sub.items:
            for r in expr.refs:
                if isinstance(r, Star):
                    return [(r.table, ref.column, label, bump)]
        return out

    if isinstance(ref, Var):
        return [(t, c, "VARIABLE", h + 1) for t, c, h in ctx.var_sources.get(ref.name, ())]

    if isinstance(ref, ScalarSubquery):
        out = []
        if ref.select.items:
            _, expr = ref.select.items[0]
            for r in expr.refs:
                out.extend(resolve_ref(r, ref.select, ctx, catalog, depth + 1))
        return out

    if isinstance(ref, Star):
        return []

    return []


def _resolve_all(refs, sel, ctx, catalog) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for r in refs:
        for t, c, _, _ in resolve_ref(r, sel, ctx, catalog):
            out.append((t, c))
    return _dedup(out)


def value_edges(target_table: str, target_column: str | None, expr: Expr,
                sel: Select | None, ctx: ProcContext, catalog: dict | None,
                anchor: str | None) -> list[Edge]:
    """Edges for one assigned value (a SELECT item, SET clause, or VALUES slot)."""

    groups: dict[tuple[str, int, tuple[str, ...]], list[tuple[str, str]]] = {}
    for r in expr.refs:
        for t, c, transport, extra in resolve_ref(r, sel, ctx, catalog):
            kind = expr.kind
            via: tuple[str, ...] = ()
            if transport:
                via = (transport,)
                if kind == DIRECT and transport == "CTE":
                    kind = VIA_CTE
                elif kind == DIRECT and transport == "VARIABLE":
                    kind = VIA_VARIABLE
            groups.setdefault((kind, 1 + extra, via), []).append((t, c))

    text = expr.sql()
    edges = [
        Edge(target_table, target_column, _dedup(srcs), kind, text, hops, list(via), anchor)
        for (kind, hops, via), srcs in groups.items()
    ]

    cond_srcs = _resolve_all(expr.cond_refs, sel, ctx, catalog)
    if cond_srcs:
        edges.append(Edge(target_table, target_column, cond_srcs, INDIRECT_FILTER,
                          text, 1, [], anchor, note="조건절 참조"))
    return edges


def filter_edges(target_table: str, sel: Select, ctx: ProcContext,
                 catalog: dict | None, sid: int) -> list[Edge]:
    """Table-level INDIRECT_FILTER edges from WHERE / JOIN / GROUP BY / CONNECT BY.

    Each edge anchors on the line that carries its own predicate, not on the
    head of the statement, so a wrong filter edge points straight at the clause
    that produced it.
    """

    out: list[Edge] = []
    for label, c in sel.filter_exprs():
        srcs = _resolve_all(c.refs, sel, ctx, catalog)
        if srcs:
            out.append(Edge(target_table, None, srcs, INDIRECT_FILTER,
                            f"{label} {c.sql()}", 1, [], pred_key(sid, c.sql())))
    if sel.group_by:
        srcs = _resolve_all(sel.group_by, sel, ctx, catalog)
        if srcs:
            group_text = ", ".join(r.sql() for r in sel.group_by)
            out.append(Edge(target_table, None, srcs, INDIRECT_FILTER,
                            "GROUP BY " + group_text, 1, [],
                            pred_key(sid, group_text)))
    return out


def _expand_items(sel: Select, catalog: dict) -> list[tuple[str | None, Expr]]:
    """Expand ``alias.*`` projections using the DDL catalog."""

    out: list[tuple[str | None, Expr]] = []
    for name, expr in sel.items:
        star = next((r for r in expr.refs if isinstance(r, Star)), None)
        if star is None:
            out.append((name, expr))
            continue
        tbl = catalog.get(star.table.split("@")[0])
        if tbl is None:
            out.append((name, expr))
            continue
        for c in tbl.column_names:
            out.append((c, e_col(ColRef(star.table, c, star.alias))))
    return out


def stmt_edges(s: Stmt, ctx: ProcContext, catalog: dict) -> list[Edge]:
    """Lineage edges produced by one statement. Mutates ``ctx`` for bindings."""

    out: list[Edge] = []

    if isinstance(s, InsertSelect):
        items = _expand_items(s.select, catalog)
        columns = s.columns
        if columns is None:
            tbl = catalog.get(s.target.split("@")[0])
            columns = list(tbl.column_names) if tbl else []
        star_expanded = len(items) != len(s.select.items)
        for i, colname in enumerate(columns):
            if i >= len(items):
                break
            _, expr = items[i]
            anchor = f"{s.sid}:col:{0 if star_expanded else i}"
            new = value_edges(s.target, colname, expr, s.select, ctx, catalog, anchor)
            if star_expanded:
                for edge in new:
                    edge.note = "SELECT * 전개 (DDL 카탈로그 필요)"
            out.extend(new)
        out.extend(filter_edges(s.target, s.select, ctx, catalog, s.sid))

    elif isinstance(s, InsertValues):
        for i, colname in enumerate(s.columns):
            if i >= len(s.values):
                break
            out.extend(value_edges(s.target, colname, s.values[i], None, ctx, catalog,
                                   f"{s.sid}:col:{i}"))

    elif isinstance(s, Update):
        for i, (colname, expr) in enumerate(s.sets):
            out.extend(value_edges(s.target, colname, expr, None, ctx, catalog,
                                   f"{s.sid}:col:{i}"))
        for c in s.where:
            srcs = _resolve_all(c.refs, None, ctx, catalog)
            if srcs:
                out.append(Edge(s.target, None, srcs, INDIRECT_FILTER,
                                f"UPDATE WHERE {c.sql()}", 1, [],
                                pred_key(s.sid, c.sql())))

    elif isinstance(s, Delete):
        for c in s.where:
            srcs = _resolve_all(c.refs, None, ctx, catalog)
            if srcs:
                out.append(Edge(s.target, None, srcs, INDIRECT_FILTER,
                                f"DELETE WHERE {c.sql()}", 1, [],
                                pred_key(s.sid, c.sql())))

    elif isinstance(s, Merge):
        # MERGE clauses reference the USING projection by its alias, so resolve
        # them against a wrapper that exposes it as a transparent derived table.
        scope = Select(tables=[TableRef(subquery=s.using, alias=s.using_alias,
                                        transparent=True)])
        for i, (colname, expr) in enumerate(s.update_sets):
            out.extend(value_edges(s.target, colname, expr, scope, ctx, catalog,
                                   f"{s.sid}:upd:{i}"))
        for i, colname in enumerate(s.insert_columns):
            if i >= len(s.insert_values):
                break
            out.extend(value_edges(s.target, colname, s.insert_values[i], scope, ctx,
                                   catalog, f"{s.sid}:ins:{i}"))
        for c in s.on:
            srcs = _resolve_all(c.refs, scope, ctx, catalog)
            if srcs:
                out.append(Edge(s.target, None, srcs, INDIRECT_FILTER,
                                f"MERGE ON {c.sql()}", 1, [],
                                pred_key(s.sid, c.sql())))
        out.extend(filter_edges(s.target, s.using, ctx, catalog, s.sid))

    elif isinstance(s, SelectInto):
        if s.bulk:
            # BULK COLLECT INTO t_rows binds the *element fields*, referenced
            # downstream as t_rows(i).COLUMN inside a FORALL.
            collection = s.targets[0]
            for name, expr in s.select.items:
                if not name:
                    continue
                bound = []
                for r in expr.refs:
                    for t, c, _, extra in resolve_ref(r, s.select, ctx, catalog):
                        bound.append((t, c, extra))
                ctx.bind(f"{collection}(i).{name}", bound)
        else:
            for i, target in enumerate(s.targets):
                if i >= len(s.select.items):
                    break
                _, expr = s.select.items[i]
                bound = []
                for r in expr.refs:
                    for t, c, _, extra in resolve_ref(r, s.select, ctx, catalog):
                        bound.append((t, c, extra))
                ctx.bind(target, bound)

    elif isinstance(s, CursorLoop):
        for i, (name, expr) in enumerate(s.select.items):
            if not name:
                continue
            bound = []
            for r in expr.refs:
                for t, c, _, extra in resolve_ref(r, s.select, ctx, catalog):
                    bound.append((t, c, extra))
            ctx.bind(f"{s.record}.{name}", bound)

    elif isinstance(s, OpenRefCursor):
        cols = []
        for i, (name, expr) in enumerate(s.select.items):
            srcs = _resolve_all(expr.refs, s.select, ctx, catalog)
            cols.append((name or f"COL_{i + 1}", srcs, expr.kind))
        ctx.ref_cursors.append(RefCursorProjection(s.out_param, cols, f"{s.sid}:cur:0"))

    elif isinstance(s, Assign):
        bound: list[tuple[str, str, int]] = []
        for r in s.expr.refs:
            for tbl, col, _, extra in resolve_ref(r, None, ctx, catalog):
                bound.append((tbl, col, extra))
        if s.accumulate:
            bound = list(ctx.var_sources.get(s.target, [])) + bound
        ctx.bind(s.target, bound)

    elif isinstance(s, ExecImmediate):
        out.append(Edge(s.target_hint or "UNKNOWN", None, [], UNRESOLVED,
                        "EXECUTE IMMEDIATE v_sql", 1, [], f"{s.sid}:dyn", note=s.reason))

    return out


def assign_ids(pkg: Package) -> None:
    counter = 0
    for sub in pkg.subprograms:
        for s in walk(sub.stmts):
            counter += 1
            s.sid = counter


def extract_package_edges(
    pkg: Package, catalog: dict
) -> tuple[list[tuple[str, Edge]], list[tuple[str, RefCursorProjection]]]:
    """Edges plus ref-cursor projections for a whole package.

    Both lists are tagged with the owning subprogram name so the truth file can
    record ``location.procedure``.
    """

    edges: list[tuple[str, Edge]] = []
    cursors: list[tuple[str, RefCursorProjection]] = []
    for sub in pkg.subprograms:
        ctx = ProcContext()
        for s in walk(sub.stmts):
            for e in stmt_edges(s, ctx, catalog):
                edges.append((sub.name, e))
        for rc in ctx.ref_cursors:
            cursors.append((sub.name, rc))
    return edges, cursors


# --- package rendering --------------------------------------------------------


def render_package(pkg: Package) -> tuple[str, dict[str, int]]:
    """Render a package spec+body. Returns text and ``anchor -> 1-based line``."""

    b = Block()
    b.add(f"-- {'=' * 74}")
    b.add(f"-- 패키지 : {pkg.fq}")
    b.add(f"-- 설명   : {pkg.comment}")
    b.add(f"-- 난이도 : Tier {pkg.tier}")
    b.add(f"-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.")
    b.add(f"-- {'=' * 74}")
    b.add("")
    b.add(f"CREATE OR REPLACE PACKAGE {pkg.fq} AS")
    b.add("")
    for sub in pkg.subprograms:
        b.add(f"  -- {sub.comment}")
        b.add(f"  {_signature(sub)};")
        b.add("")
    b.add(f"END {pkg.name};")
    b.add("/")
    b.add("")
    b.add(f"CREATE OR REPLACE PACKAGE BODY {pkg.fq} AS")
    b.add("")
    b.add("  g_job_id    VARCHAR2(30) := 'JOB_" + pkg.name + "';")
    b.add("  g_step_no   NUMBER(5)    := 0;")
    b.add("")

    for sub in pkg.subprograms:
        b.add(f"  -- {'-' * 70}")
        b.add(f"  -- {sub.name} : {sub.comment}")
        b.add(f"  -- {'-' * 70}")
        b.add(f"  {_signature(sub)}")
        b.add("  IS")
        if sub.autonomous:
            b.add("    PRAGMA AUTONOMOUS_TRANSACTION;")
        for d in sub.decls:
            b.add(f"    {d}")
        b.add("  BEGIN")
        b.add("")
        for s in sub.stmts:
            inner = render_stmt(s)
            b.merge(inner, 4)
            b.add("")
        for line in sub.tail:
            b.add(f"    {line}")
        b.add("  EXCEPTION")
        b.add("    WHEN NO_DATA_FOUND THEN")
        b.add("      NULL;")
        b.add("    WHEN OTHERS THEN")
        b.add("      ROLLBACK;")
        b.add(f"      SYNWMS.PKG_COMMON.p_log_error(g_job_id, '{sub.name}', SQLERRM);")
        b.add("      RAISE;")
        b.add(f"  END {sub.name};")
        b.add("")

    b.add(f"END {pkg.name};")
    b.add("/")
    b.add("")

    text = "\n".join(b.lines)
    anchors = {k: v + 1 for k, v in b.anchors.items()}
    return text, anchors


COMMON_PACKAGE = """-- ==========================================================================
-- 패키지 : SYNWMS.PKG_COMMON
-- 설명   : 배치 공통 유틸리티 (로그 기록, 기준일자 산출)
-- 난이도 : Tier 0
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_COMMON AS

  -- 오류 로그 기록
  PROCEDURE p_log_error (
    p_job_id  IN VARCHAR2,
    p_step_nm IN VARCHAR2,
    p_err_msg IN VARCHAR2
  );

  -- 기준일자 산출
  FUNCTION fn_base_ymd (
    p_offset IN NUMBER
  )
  RETURN VARCHAR2;

END PKG_COMMON;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_COMMON AS

  -- 로그는 본 트랜잭션과 분리해 기록한다.
  PROCEDURE p_log_error (
    p_job_id  IN VARCHAR2,
    p_step_nm IN VARCHAR2,
    p_err_msg IN VARCHAR2
  )
  IS
    PRAGMA AUTONOMOUS_TRANSACTION;
  BEGIN
    INSERT INTO SYNARC.ARC_JOB_LOG (
           LOG_SEQ,
           JOB_ID,
           JOB_NM,
           STEP_NO,
           ERR_MSG,
           STA_DTM
         )
    VALUES (
           SYNWMS.SEQ_JOB_LOG.NEXTVAL,
           p_job_id,
           p_step_nm,
           0,
           SUBSTR(p_err_msg, 1, 2000),
           SYSDATE
         );
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN
      ROLLBACK;
  END p_log_error;

  FUNCTION fn_base_ymd (
    p_offset IN NUMBER
  )
  RETURN VARCHAR2
  IS
  BEGIN
    RETURN TO_CHAR(TRUNC(SYSDATE) - NVL(p_offset, 0), 'YYYYMMDD');
  END fn_base_ymd;

END PKG_COMMON;
/
"""


def _signature(sub: Subprogram) -> str:
    if not sub.params:
        head = f"{sub.kind} {sub.name}"
    else:
        width = max(len(p.name) for p in sub.params)
        parts = [f"{_pad(p.name, width)} {p.mode} {p.dtype}" for p in sub.params]
        head = f"{sub.kind} {sub.name} (\n    " + ",\n    ".join(parts) + "\n  )"
    if sub.kind == "FUNCTION":
        head += f"\n  RETURN {sub.return_type}"
    return head
