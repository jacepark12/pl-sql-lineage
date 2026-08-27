"""Layer A - pull PL/SQL structure out of the parse tree.

What the later layers need from PL/SQL is narrow: where each subprogram begins
and ends, what is declared in it, where each SQL statement starts and stops, and
which variable each assignment writes. Statement *interiors* are not read here -
they are handed to sqlglot as original source text.

Two details matter downstream.

``Statement.sql`` is a slice of the original source, not ``getText()``. ANTLR
concatenates token text without whitespace, so ``getText()`` returns
``INSERTINTOT(A,B)SELECT...`` which no SQL parser will accept. Slicing by token
offsets keeps the statement exactly as written.

``%TYPE`` anchors are resolved into column references for the declaration
record. That is a type, not a value that flowed: layer C does **not** turn
``v T.COL%TYPE`` into a source of ``T.COL``. Doing so would invent lineage
when the variable is filled from a parameter, a literal, or another column.
``%ROWTYPE`` is different — ``r.COL`` names a field of table ``T``, so the
field access itself is the column.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

# Context class names, matched without the trailing "Context".
_PACKAGE_BODY = "Create_package_body"
_SUBPROGRAM = ("Procedure_body", "Function_body",
               "Create_procedure_body", "Create_function_body")
_TRIGGER = "Create_trigger"
_DML = "Data_manipulation_language_statements"
_ASSIGNMENT = "Assignment_statement"
_EXECUTE_IMMEDIATE = "Execute_immediate"
_OPEN_FOR = "Open_for_statement"
_SEQ_OF_STATEMENTS = "Seq_of_statements"


@dataclass(frozen=True)
class ColumnRef:
    schema: str | None
    table: str
    column: str

    def __str__(self) -> str:
        prefix = f"{self.schema}." if self.schema else ""
        return f"{prefix}{self.table}.{self.column}"


@dataclass
class Declaration:
    """A variable or parameter.

    ``anchor`` is set for ``TABLE.COLUMN%TYPE`` (type only — not a value
    source). ``rowtype`` is the table named by ``T%ROWTYPE``.
    """
    name: str
    type_text: str
    anchor: ColumnRef | None = None
    rowtype: str | None = None       # SCHEMA.T or T, from %ROWTYPE
    mode: str | None = None          # IN / OUT / IN OUT, parameters only
    line: int = 0

    @property
    def is_parameter(self) -> bool:
        return self.mode is not None


@dataclass
class Statement:
    kind: str                        # "dml" | "assignment" | "dynamic_sql"
    sql: str                         # original source, verbatim
    line: int
    assigns_to: str | None = None    # variable name, assignments only
    ctx: object = field(default=None, repr=False)


@dataclass
class Cursor:
    """``CURSOR c IS SELECT ...`` - a named query the loop record is drawn from."""
    name: str
    sql: str
    line: int = 0


@dataclass
class LoopRecord:
    """``FOR rec IN c LOOP`` or ``FOR rec IN (SELECT ...) LOOP``.

    ``rec.COLUMN`` inside the body reads the query's projection, so binding the
    record to that query is what lets a value cross out of the loop.
    """
    record: str
    cursor: str | None = None
    sql: str | None = None
    line: int = 0


@dataclass
class Subprogram:
    name: str
    kind: str                        # "PROCEDURE" | "FUNCTION"
    declarations: list[Declaration] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    cursors: list[Cursor] = field(default_factory=list)
    loops: list[LoopRecord] = field(default_factory=list)
    line: int = 0

    def cursor(self, name: str) -> Cursor | None:
        folded = name.upper()
        for item in self.cursors:
            if item.name.upper() == folded:
                return item
        return None

    def declaration(self, name: str) -> Declaration | None:
        folded = name.upper()
        for decl in self.declarations:
            if decl.name.upper() == folded:
                return decl
        return None


@dataclass
class PackageUnit:
    schema: str | None
    name: str
    subprograms: list[Subprogram] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


# --- tree helpers -------------------------------------------------------------


def _rule(node: object) -> str:
    return type(node).__name__.removesuffix("Context")


def _children(node: object) -> Iterator[object]:
    getter = getattr(node, "getChildren", None)
    if getter is not None:
        yield from getter()


def _walk(node: object) -> Iterator[object]:
    yield node
    for child in _children(node):
        yield from _walk(child)


def _find_all(node: object, *rules: str) -> Iterator[object]:
    """Every descendant matching one of ``rules``, outermost match only."""
    if _rule(node) in rules:
        yield node
        return
    for child in _children(node):
        yield from _find_all(child, *rules)


def _first(node: object, *rules: str) -> object | None:
    return next(_find_all(node, *rules), None)


def _source(node: object, text: str) -> str:
    """The original slice this node covers, whitespace and all."""
    return text[node.start.start:node.stop.stop + 1]


def _name_of(node: object | None) -> str:
    return node.getText() if node is not None else ""


# --- %TYPE ---------------------------------------------------------------


def parse_type_anchor(type_text: str) -> ColumnRef | None:
    """``SYNWMS.OUT_SHIP.SHIP_QTY%TYPE`` -> ColumnRef, else None.

    Only ``TABLE.COLUMN%TYPE`` / ``SCHEMA.TABLE.COLUMN%TYPE`` count. A
    variable%TYPE chain (``v2 v1%TYPE``) has one segment and is dropped —
    following it as a value source would confuse "declared like v1" with
    "holds what v1 holds".
    """
    upper = type_text.upper()
    if not upper.endswith("%TYPE") or upper.endswith("%ROWTYPE"):
        return None
    parts = type_text[: -len("%TYPE")].split(".")
    if len(parts) == 3:
        return ColumnRef(parts[0], parts[1], parts[2])
    if len(parts) == 2:
        return ColumnRef(None, parts[0], parts[1])
    return None


def parse_rowtype_anchor(type_text: str) -> str | None:
    """``SYNWMS.MST_ITEM%ROWTYPE`` -> ``SYNWMS.MST_ITEM``, else None.

    ``c%ROWTYPE`` for a cursor is a single name and is still returned; the
    caller distinguishes a known cursor from a table.
    """
    compact = type_text.replace(" ", "")
    if not compact.upper().endswith("%ROWTYPE"):
        return None
    owner = compact[: -len("%ROWTYPE")].strip(".")
    parts = [p for p in owner.split(".") if p]
    if len(parts) in (1, 2):
        return ".".join(parts)
    return None


# --- extraction ---------------------------------------------------------------


def _parameters(subprogram_ctx: object) -> list[Declaration]:
    out: list[Declaration] = []
    for ctx in _find_all(subprogram_ctx, "Parameter"):
        name = _name_of(_first(ctx, "Parameter_name"))
        type_text = _name_of(_first(ctx, "Type_spec"))
        body = ctx.getText().upper()
        mode = "IN OUT" if "INOUT" in body.replace(" ", "") else (
            "OUT" if body[len(name):].lstrip().startswith("OUT") else "IN")
        out.append(Declaration(
            name, type_text,
            anchor=parse_type_anchor(type_text),
            rowtype=parse_rowtype_anchor(type_text),
            mode=mode, line=ctx.start.line))
    return out


def _declarations(subprogram_ctx: object) -> list[Declaration]:
    out: list[Declaration] = []
    for spec in _find_all(subprogram_ctx, "Declare_spec"):
        variable = _first(spec, "Variable_declaration")
        if variable is None:
            continue
        name = _name_of(_first(variable, "Identifier"))
        type_text = _name_of(_first(variable, "Type_spec"))
        if not name:
            continue
        out.append(Declaration(
            name, type_text,
            anchor=parse_type_anchor(type_text),
            rowtype=parse_rowtype_anchor(type_text),
            line=spec.start.line))
    return out


def _statements(subprogram_ctx: object, text: str) -> list[Statement]:
    """DML and assignments in source order, flattened out of control flow.

    Nesting is deliberately dropped. Layer C reasons about which variable held
    what by the order statements execute in, and a straight-line reading is a
    sound approximation of that for lineage: an assignment inside an IF still
    means the variable *can* carry that value.
    """
    body = _first(subprogram_ctx, "Body") or subprogram_ctx
    found: list[Statement] = []
    for node in _walk(body):
        rule = _rule(node)
        if rule == _DML:
            found.append(Statement("dml", _source(node, text), node.start.line,
                                   ctx=node))
        elif rule == _ASSIGNMENT:
            target = _first(node, "General_element")
            found.append(Statement("assignment", _source(node, text),
                                   node.start.line,
                                   assigns_to=_name_of(target) or None, ctx=node))
        elif rule == _EXECUTE_IMMEDIATE:
            found.append(Statement("dynamic_sql", _source(node, text),
                                   node.start.line, ctx=node))
        elif rule == _OPEN_FOR and _first(node, "Select_statement") is None:
            # OPEN c FOR <expression> is native dynamic SQL; OPEN c FOR SELECT
            # is a static cursor and is not diagnosed here.
            found.append(Statement("dynamic_sql", _source(node, text),
                                   node.start.line, ctx=node))
    found.sort(key=lambda s: s.line)
    return found


def _cursors(subprogram_ctx: object, text: str) -> list[Cursor]:
    out: list[Cursor] = []
    for ctx in _find_all(subprogram_ctx, "Cursor_declaration"):
        name = _name_of(_first(ctx, "Identifier"))
        select = _first(ctx, "Select_statement")
        if name and select is not None:
            out.append(Cursor(name, _source(select, text), ctx.start.line))
    return out


def _loops(subprogram_ctx: object, text: str) -> list[LoopRecord]:
    out: list[LoopRecord] = []
    for ctx in _find_all(subprogram_ctx, "Cursor_loop_param"):
        record = _name_of(_first(ctx, "Record_name"))
        if not record:
            continue
        cursor = _first(ctx, "Cursor_name")
        select = _first(ctx, "Select_statement")
        out.append(LoopRecord(
            record,
            _name_of(cursor) if cursor is not None else None,
            _source(select, text) if select is not None else None,
            ctx.start.line))
    return out


def _subprograms(scope: object, text: str) -> list[Subprogram]:
    out: list[Subprogram] = []
    for ctx in _find_all(scope, *_SUBPROGRAM):
        kind = "FUNCTION" if "FUNCTION" in _rule(ctx).upper() else "PROCEDURE"
        name = _name_of(_first(ctx, "Identifier"))
        sub = Subprogram(name=name, kind=kind, line=ctx.start.line)
        sub.declarations = _parameters(ctx) + _declarations(ctx)
        sub.statements = _statements(ctx, text)
        sub.cursors = _cursors(ctx, text)
        sub.loops = _loops(ctx, text)
        out.append(sub)
    return out


def extract(tree: object, text: str) -> list[PackageUnit]:
    """Every package body in one parsed source unit.

    Standalone procedures and functions - those not inside a package - are
    returned under a package whose name is empty, so callers have one shape to
    handle rather than two.
    """
    units: list[PackageUnit] = []
    package_ctxs = list(_find_all(tree, _PACKAGE_BODY))
    for ctx in package_ctxs:
        schema = _name_of(_first(ctx, "Schema_object_name")) or None
        name = _name_of(_first(ctx, "Package_name"))
        units.append(PackageUnit(schema, name, _subprograms(ctx, text)))

    if not package_ctxs:
        loose = _subprograms(tree, text)
        if loose:
            units.append(PackageUnit(None, "", loose))

    # Standalone CREATE TRIGGER (or ALL_SOURCE dumps wrapped into one). A
    # trigger is not a procedure_body, so without this the DML inside would
    # vanish after a successful parse.
    for ctx in _find_all(tree, _TRIGGER):
        name = _name_of(_first(ctx, "Trigger_name"))
        sub = Subprogram(name=name, kind="TRIGGER", line=ctx.start.line)
        sub.declarations = _declarations(ctx)
        sub.statements = _statements(ctx, text)
        units.append(PackageUnit(None, name, [sub]))
    return units
