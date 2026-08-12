"""Pipeline state simulator - the thing that turns FLOW steps into truth.

Collecting every ``MAPCOPY`` in a package and calling the result lineage
produces answers that look right and are not. The pipeline is mutable shared
state: a ``MAPDELETE`` or a ``pub.flow:clearPipeline`` partway through makes
every later reference to that path dead, and a mapping written before the delete
says nothing about what the adapter finally wrote. So the steps are replayed in
order and the truth is read off the resulting state, never off the step list.

The output is the same :class:`~synplsql.core.Edge` the SQL generator emits, so
both corpora land in one graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from synplsql.core import (
    CONSTANT,
    DIRECT,
    INDIRECT_FILTER,
    SEVERED,
    TRANSFORM,
    UNRESOLVED,
    VIA_PIPELINE,
    Edge,
)

from .adapters import CUSTOM_SQL, INSERT, SELECT, UPDATE, Adapter
from .flow import (
    Branch,
    Invoke,
    Loop,
    Map,
    MapCopy,
    MapDelete,
    MapInvoke,
    MapSet,
    Path,
    Sequence,
    Step,
)

CLEAR_PIPELINE = "pub.flow:clearPipeline"


@dataclass(frozen=True)
class Origin:
    """What a pipeline slot currently holds, in lineage terms."""

    sources: tuple[tuple[str, str], ...] = ()
    kind: str = DIRECT
    transform: str = ""
    hops: int = 1
    via: tuple[str, ...] = ()
    #: Set when the slot was removed. A read of a severed slot is a real answer
    #: ("the lineage ends here"), not a gap in the truth set.
    severed_by: str | None = None

    @property
    def is_live(self) -> bool:
        return self.severed_by is None


@dataclass
class Context:
    """Everything the simulator needs that is not the step list itself."""

    interface: str
    target_table: str
    artifact: str = ""
    #: Conditions currently gating execution, as (switch label, origin).
    conditions: list[tuple[str, Origin]] = field(default_factory=list)
    #: Loop nesting, for the note on edges produced with changed cardinality.
    loops: list[str] = field(default_factory=list)


class Pipeline:
    """The webMethods pipeline, reduced to what lineage needs."""

    def __init__(self) -> None:
        self.slots: dict[str, Origin] = {}
        self.severed: dict[str, str] = {}

    def read(self, path: Path) -> Origin | None:
        key = path.key
        if key in self.slots:
            return self.slots[key]
        if key in self.severed:
            return Origin(kind=SEVERED, severed_by=self.severed[key],
                          transform=f"pipeline field removed at {self.severed[key]}")
        return None

    def write(self, path: Path, origin: Origin) -> None:
        self.slots[path.key] = origin
        self.severed.pop(path.key, None)

    def delete(self, path: Path, step_path: str) -> None:
        prefix = path.key
        for key in [k for k in self.slots
                    if k == prefix or k.startswith(prefix + "/")]:
            del self.slots[key]
            self.severed[key] = step_path

    def clear(self, preserve: list[str], step_path: str) -> None:
        keep = set(preserve)
        for key in list(self.slots):
            head = key.split("/")[0]
            if head in keep or key in keep:
                continue
            del self.slots[key]
            self.severed[key] = step_path


# --- simulation ---------------------------------------------------------------


def _carry(origin: Origin) -> Origin:
    """Move a value one hop along the pipeline."""

    if not origin.is_live:
        return origin
    kind = VIA_PIPELINE if origin.kind == DIRECT else origin.kind
    via = origin.via if "PIPELINE" in origin.via else origin.via + ("PIPELINE",)
    return replace(origin, kind=kind, via=via, hops=origin.hops + 1)


def _merge(origins: list[Origin], service: str) -> Origin:
    """Combine transformer inputs into one output value."""

    sources: list[tuple[str, str]] = []
    hops = 1
    via: list[str] = []
    for o in origins:
        if not o.is_live:
            continue
        for s in o.sources:
            if s not in sources:
                sources.append(s)
        hops = max(hops, o.hops)
        for v in o.via:
            if v not in via:
                via.append(v)
    return Origin(tuple(sources), TRANSFORM, service, hops + 1, tuple(via))


def _filter_edges(ctx: Context, origin: Origin, label: str,
                  step_path: str) -> list[Edge]:
    if not origin.is_live or not origin.sources:
        return []
    return [Edge(ctx.target_table, None, list(origin.sources), INDIRECT_FILTER,
                 label, 1, list(origin.via), step_path)]


def _adapter_of(step: Invoke, adapters: dict[str, Adapter]) -> Adapter | None:
    return adapters.get(step.adapter) if step.adapter else None


def _run_select(adapter: Adapter, ctx: Context, pipe: Pipeline,
                doc_path, step_path: str) -> list[Edge]:
    """A Select adapter fills the source document from the source table."""

    out: list[Edge] = []
    for field_name, column in adapter.field_map.items():
        table = adapter.column_table.get(column, adapter.fq_table)
        pipe.write(doc_path(adapter, field_name),
                   Origin(((table, column),), DIRECT,
                          f"select.outputField[{field_name}] = {column}", 1))
    for table, column, op, literal in adapter.filter_columns:
        out.append(Edge(ctx.target_table, None, [(table, column)], INDIRECT_FILTER,
                        f"WHERE {column} {op} {literal}", 1, [], step_path))
    return out


def _run_writer(adapter: Adapter, ctx: Context, pipe: Pipeline,
                doc_path, step_path: str) -> list[Edge]:
    """An Insert/Update adapter is where pipeline fields become columns."""

    out: list[Edge] = []
    for column, field_name in adapter.field_map.items():
        expression = adapter.expressions.get(column, "?")
        origin = pipe.read(doc_path(adapter, field_name))

        if origin is None:
            out.append(Edge(adapter.fq_table, column, [], SEVERED,
                            f"pipeline field {field_name} never set", 1, [],
                            step_path,
                            note="쓰기 시점에 파이프라인에 값이 없음"))
            continue
        if not origin.is_live:
            out.append(Edge(adapter.fq_table, column, [], SEVERED,
                            origin.transform, 1, [], step_path,
                            note=f"{origin.severed_by} 에서 파이프라인 필드가 제거됨"))
            continue
        if origin.kind == CONSTANT:
            out.append(Edge(adapter.fq_table, column, [], CONSTANT,
                            origin.transform, 1, [], step_path,
                            note="상수 대입 - 원천 컬럼 없음"))
            continue

        kind = origin.kind
        transform = origin.transform
        if expression != "?":
            # The DB-side expression exists only inside the adapter blob, so an
            # engine that skips the blob loses this transform entirely.
            kind = TRANSFORM
            transform = f"{transform} → {expression}"
        out.append(Edge(adapter.fq_table, column, list(origin.sources), kind,
                        transform, origin.hops + 1, list(origin.via), step_path,
                        note=_context_note(ctx)))

    for column in adapter.where_columns:
        origin = pipe.read(doc_path(adapter, column))
        if origin is not None and origin.is_live and origin.sources:
            out.append(Edge(adapter.fq_table, None, list(origin.sources),
                            INDIRECT_FILTER, f"UPDATE WHERE {column} = ?", 1,
                            list(origin.via), step_path))

    for label, origin in ctx.conditions:
        out.extend(_filter_edges(ctx, origin, f"BRANCH {label}", step_path))
    return out


def _run_custom_sql(adapter: Adapter, ctx: Context, step_path: str) -> list[Edge]:
    """CustomSQL holds arbitrary SQL. Reading it needs the SQL engine, not the
    adapter reader - which is the argument for one engine over both corpora."""

    return [Edge(adapter.fq_table, None, [], UNRESOLVED,
                 (adapter.sql or "")[:120], 1, [], step_path,
                 note="CustomSQL - SQL 파서 필요 (PL/SQL 엔진 재사용 지점)")]


def _context_note(ctx: Context) -> str | None:
    parts = []
    if ctx.loops:
        parts.append("배열 반복 구간 (" + ", ".join(ctx.loops) + ")")
    if ctx.conditions:
        parts.append("조건부 실행 (" + ", ".join(l for l, _ in ctx.conditions) + ")")
    return " / ".join(parts) if parts else None


def simulate(steps: list[Step], ctx: Context, adapters: dict[str, Adapter],
             doc_path, pipe: Pipeline | None = None) -> tuple[list[Edge], Pipeline]:
    """Replay steps in order, returning the edges they produce.

    ``doc_path(adapter, field_name)`` resolves an adapter field to the pipeline
    path it reads or writes - the source side sits under a document reference,
    the target side is a plain record, and only the caller knows which.
    """

    pipe = pipe or Pipeline()
    edges: list[Edge] = []

    for step in steps:
        if isinstance(step, MapCopy):
            origin = pipe.read(step.frm)
            if origin is None:
                continue
            pipe.write(step.to, _carry(origin))

        elif isinstance(step, MapSet):
            pipe.write(step.to, Origin((), CONSTANT, step.value, 1))

        elif isinstance(step, MapDelete):
            pipe.delete(step.target, step.step_path)

        elif isinstance(step, MapInvoke):
            inputs = [pipe.read(path) for path in step.inputs.values()]
            live = [o for o in inputs if o is not None]
            if not live or all(not o.is_live for o in live):
                severed_by = next((o.severed_by for o in live if o.severed_by), None)
                pipe.write(step.output,
                           Origin(kind=SEVERED, severed_by=severed_by or step.step_path,
                                  transform=f"{step.service} (입력 소실)"))
            else:
                pipe.write(step.output, _merge(live, step.service))

        elif isinstance(step, Invoke):
            if step.service == CLEAR_PIPELINE:
                pipe.clear(step.preserve, step.step_path)
                continue
            adapter = _adapter_of(step, adapters)
            if adapter is None:
                continue
            # The adapter name rides along on the anchor: an edge has to say
            # which blob it came from, so the truth can be checked against that
            # blob's contents rather than only against the flow XML.
            at = f"{step.step_path}#{adapter.name}"
            if adapter.template == SELECT:
                edges.extend(_run_select(adapter, ctx, pipe, doc_path, at))
            elif adapter.template in (INSERT, UPDATE):
                edges.extend(_run_writer(adapter, ctx, pipe, doc_path, at))
            elif adapter.template == CUSTOM_SQL:
                edges.extend(_run_custom_sql(adapter, ctx, at))

        elif isinstance(step, (Map, Sequence)):
            sub, pipe = simulate(step.children, ctx, adapters, doc_path, pipe)
            edges.extend(sub)

        elif isinstance(step, Loop):
            ctx.loops.append(step.in_array.key)
            sub, pipe = simulate(step.children, ctx, adapters, doc_path, pipe)
            edges.extend(sub)
            ctx.loops.pop()

        elif isinstance(step, Branch):
            switch = pipe.read(step.switch)
            # Each case runs against a copy of the pipeline: what one branch
            # deletes must not appear deleted in its sibling.
            merged = Pipeline()
            merged.slots = dict(pipe.slots)
            merged.severed = dict(pipe.severed)
            for label, child in step.cases:
                branch_pipe = Pipeline()
                branch_pipe.slots = dict(pipe.slots)
                branch_pipe.severed = dict(pipe.severed)
                if switch is not None:
                    ctx.conditions.append((f"{step.switch.key}={label}", switch))
                sub, branch_pipe = simulate([child], ctx, adapters, doc_path,
                                            branch_pipe)
                if switch is not None:
                    ctx.conditions.pop()
                edges.extend(sub)
                for key, origin in branch_pipe.slots.items():
                    merged.slots.setdefault(key, origin)
            pipe = merged

    return edges, pipe
