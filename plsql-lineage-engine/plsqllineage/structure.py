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

``%TYPE`` anchors are resolved into column references. A declaration reading
``v_qty SYNWMS.OUT_SHIP.SHIP_QTY%TYPE`` says the variable carries that column,
which is what lets layer C reconnect a value across statement boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

# Context class names, matched without the trailing "Context".
_PACKAGE_BODY = "Create_package_body"
_SUBPROGRAM = ("Procedure_body", "Function_body",
               "Create_procedure_body", "Create_function_body")
_DML = "Data_manipulation_language_statements"
_ASSIGNMENT = "Assignment_statement"
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
    """A variable or parameter. ``anchor`` is set when declared with %TYPE."""
    name: str
    type_text: str
    anchor: ColumnRef | None = None
    mode: str | None = None          # IN / OUT / IN OUT, parameters only
    line: int = 0

    @property
    def is_parameter(self) -> bool:
        return self.mode is not None


@dataclass
class Statement:
    kind: str                        # "dml" | "assignment"
    sql: str                         # original source, verbatim
    line: int
    assigns_to: str | None = None    # variable name, assignments only
    ctx: object = field(default=None, repr=False)


@dataclass
class Subprogram:
    name: str
    kind: str                        # "PROCEDURE" | "FUNCTION"
    declarations: list[Declaration] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    line: int = 0

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

    ``%ROWTYPE`` carries a table but no single column, so it yields nothing
    here; a row-level anchor is a different thing and layer C treats it as
    unresolved rather than guessing a column.
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


# --- extraction ---------------------------------------------------------------


def _parameters(subprogram_ctx: object) -> list[Declaration]:
    out: list[Declaration] = []
    for ctx in _find_all(subprogram_ctx, "Parameter"):
        name = _name_of(_first(ctx, "Parameter_name"))
        type_text = _name_of(_first(ctx, "Type_spec"))
        body = ctx.getText().upper()
        mode = "IN OUT" if "INOUT" in body.replace(" ", "") else (
            "OUT" if body[len(name):].lstrip().startswith("OUT") else "IN")
        out.append(Declaration(name, type_text, parse_type_anchor(type_text),
                               mode, ctx.start.line))
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
        out.append(Declaration(name, type_text, parse_type_anchor(type_text),
                               None, spec.start.line))
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
    found.sort(key=lambda s: s.line)
    return found


def _subprograms(scope: object, text: str) -> list[Subprogram]:
    out: list[Subprogram] = []
    for ctx in _find_all(scope, *_SUBPROGRAM):
        kind = "FUNCTION" if "FUNCTION" in _rule(ctx).upper() else "PROCEDURE"
        name = _name_of(_first(ctx, "Identifier"))
        sub = Subprogram(name=name, kind=kind, line=ctx.start.line)
        sub.declarations = _parameters(ctx) + _declarations(ctx)
        sub.statements = _statements(ctx, text)
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
    return units
