"""FLOW service IR, pipeline path syntax, and flow.xml rendering.

A webMethods FLOW is not a program with local variables; it mutates a single
global namespace called the pipeline. That is what makes its lineage harder than
it first looks: ``MAPCOPY`` is an explicit field-to-field mapping and needs no
SQL inference, but ``MAPDELETE`` and ``clearPipeline`` invalidate paths partway
through, so collecting mappings without replaying step order produces lineage
that is confidently wrong.

This module models the steps and renders the XML. ``pipeline.py`` replays them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

# --- pipeline paths -----------------------------------------------------------
#
# A path segment is  NAME;typecode;dimension[;nsref]
#   typecode   1 = string, 2 = record, 4 = record reference
#   dimension  0 = scalar, 1 = array
# The trailing nsref appears only on a document-type reference.

T_STRING = 1
T_RECORD = 2
T_RECREF = 4

DIM_SCALAR = 0
DIM_ARRAY = 1


@dataclass(frozen=True)
class Seg:
    name: str
    type_code: int = T_STRING
    dim: int = DIM_SCALAR
    nsref: str | None = None

    def render(self) -> str:
        base = f"{self.name};{self.type_code};{self.dim}"
        return f"{base};{self.nsref}" if self.nsref else base


@dataclass(frozen=True)
class Path:
    segs: tuple[Seg, ...]

    @property
    def depth(self) -> int:
        return len(self.segs)

    def render(self) -> str:
        return "".join("/" + s.render() for s in self.segs)

    @property
    def key(self) -> str:
        """Name-only form. Two paths that differ solely in type/dimension
        metadata address the same pipeline slot, so lineage keys on this."""

        return "/".join(s.name for s in self.segs)

    def child(self, seg: Seg) -> "Path":
        return Path(self.segs + (seg,))

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return self.render()


def p(*segs: Seg) -> Path:
    return Path(tuple(segs))


def scalar(name: str) -> Path:
    return p(Seg(name, T_STRING, DIM_SCALAR))


def parse_path(text: str) -> Path:
    segs = []
    for chunk in text.split("/"):
        if not chunk:
            continue
        parts = chunk.split(";")
        segs.append(Seg(parts[0],
                        int(parts[1]) if len(parts) > 1 else T_STRING,
                        int(parts[2]) if len(parts) > 2 else DIM_SCALAR,
                        parts[3] if len(parts) > 3 else None))
    return Path(tuple(segs))


# --- steps --------------------------------------------------------------------


@dataclass
class Step:
    #: Tree coordinate such as ``SEQUENCE[0]/MAP[2]/MAPCOPY[17]``. FLOW has no
    #: stable line numbers - a GUI shows the step tree - so the truth set
    #: addresses steps by path, not by line.
    step_path: str = field(default="", init=False, repr=False)
    comment: str | None = field(default=None, kw_only=True)


@dataclass
class MapCopy(Step):
    frm: Path
    to: Path


@dataclass
class MapSet(Step):
    to: Path
    value: str


@dataclass
class MapDelete(Step):
    target: Path


@dataclass
class MapInvoke(Step):
    service: str
    inputs: dict[str, Path]      # transformer input name -> pipeline path
    output: Path
    output_name: str = "value"
    literals: dict[str, str] = field(default_factory=dict)


@dataclass
class Map(Step):
    children: list[Step] = field(default_factory=list)
    mode: str = "STANDALONE"


@dataclass
class Invoke(Step):
    service: str
    #: Adapter services carry their lineage in the blob, so the simulator needs
    #: to know which adapter a plain INVOKE refers to.
    adapter: str | None = None
    inputs: dict[str, Path] = field(default_factory=dict)
    preserve: list[str] = field(default_factory=list)   # pub.flow:clearPipeline


@dataclass
class Sequence(Step):
    name: str = "main"
    exit_on: str = "FAILURE"
    children: list[Step] = field(default_factory=list)


@dataclass
class Branch(Step):
    switch: Path
    cases: list[tuple[str, Step]] = field(default_factory=list)


@dataclass
class Loop(Step):
    in_array: Path
    children: list[Step] = field(default_factory=list)


@dataclass
class FlowService:
    name: str
    steps: list[Step]
    comment: str = ""


CONTAINERS = (Sequence, Map, Loop)


def assign_step_paths(steps: list[Step], prefix: str = "") -> None:
    """Number the step tree so every step has a stable coordinate."""

    counters: dict[str, int] = {}
    for step in steps:
        kind = type(step).__name__.upper()
        idx = counters.get(kind, 0)
        counters[kind] = idx + 1
        step.step_path = f"{prefix}{kind}[{idx}]"
        if isinstance(step, (Sequence, Map, Loop)):
            assign_step_paths(step.children, step.step_path + "/")
        elif isinstance(step, Branch):
            for label, child in step.cases:
                assign_step_paths([child], f"{step.step_path}/{label}/")


def walk(steps: list[Step]):
    """Execution order: a step, then whatever it contains."""

    for step in steps:
        yield step
        if isinstance(step, (Sequence, Map, Loop)):
            yield from walk(step.children)
        elif isinstance(step, Branch):
            for _, child in step.cases:
                yield from walk([child])


# --- rendering ----------------------------------------------------------------


def _attr(value: str) -> str:
    return quoteattr(value)


class _Xml:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, indent: int, text: str) -> None:
        self.lines.append("  " * indent + text)


def _render_step(step: Step, x: _Xml, indent: int) -> None:
    if step.comment:
        x.add(indent, f"<!-- {escape(step.comment)} -->")

    if isinstance(step, MapCopy):
        x.add(indent, f"<MAPCOPY FROM={_attr(step.frm.render())} "
                      f"TO={_attr(step.to.render())}/>")
    elif isinstance(step, MapSet):
        x.add(indent, f"<MAPSET FIELD={_attr(step.to.render())}>")
        x.add(indent + 1, f"<VALUE NAME={_attr(step.to.segs[-1].name)}>"
                          f"{escape(step.value)}</VALUE>")
        x.add(indent, "</MAPSET>")
    elif isinstance(step, MapDelete):
        x.add(indent, f"<MAPDELETE FIELD={_attr(step.target.render())}/>")
    elif isinstance(step, MapInvoke):
        x.add(indent, f"<MAPINVOKE SERVICE={_attr(step.service)} "
                      f"TIMEOUT=\"\" VALIDATE-IN=\"$none\" VALIDATE-OUT=\"$none\">")
        x.add(indent + 1, "<MAP MODE=\"INPUT\">")
        for name, path in step.inputs.items():
            x.add(indent + 2, f"<MAPCOPY FROM={_attr(path.render())} "
                              f"TO={_attr('/' + name + ';1;0')}/>")
        for name, value in step.literals.items():
            x.add(indent + 2, f"<MAPSET FIELD={_attr('/' + name + ';1;0')}>")
            x.add(indent + 3, f"<VALUE NAME={_attr(name)}>{escape(value)}</VALUE>")
            x.add(indent + 2, "</MAPSET>")
        x.add(indent + 1, "</MAP>")
        x.add(indent + 1, "<MAP MODE=\"OUTPUT\">")
        x.add(indent + 2, f"<MAPCOPY FROM={_attr('/' + step.output_name + ';1;0')} "
                          f"TO={_attr(step.output.render())}/>")
        x.add(indent + 1, "</MAP>")
        x.add(indent, "</MAPINVOKE>")
    elif isinstance(step, Map):
        x.add(indent, f"<MAP MODE={_attr(step.mode)}>")
        for child in step.children:
            _render_step(child, x, indent + 1)
        x.add(indent, "</MAP>")
    elif isinstance(step, Invoke):
        x.add(indent, f"<INVOKE SERVICE={_attr(step.service)} "
                      f"TIMEOUT=\"\" VALIDATE-IN=\"$none\" VALIDATE-OUT=\"$none\">")
        if step.inputs or step.preserve:
            x.add(indent + 1, "<MAP MODE=\"INPUT\">")
            for name, path in step.inputs.items():
                x.add(indent + 2, f"<MAPCOPY FROM={_attr(path.render())} "
                                  f"TO={_attr('/' + name + ';1;0')}/>")
            if step.preserve:
                x.add(indent + 2, "<MAPSET FIELD=\"/preserve;1;1\">")
                for name in step.preserve:
                    x.add(indent + 3, f"<VALUE NAME=\"preserve\">{escape(name)}</VALUE>")
                x.add(indent + 2, "</MAPSET>")
            x.add(indent + 1, "</MAP>")
        x.add(indent, "</INVOKE>")
    elif isinstance(step, Sequence):
        x.add(indent, f"<SEQUENCE NAME={_attr(step.name)} "
                      f"EXIT-ON={_attr(step.exit_on)}>")
        for child in step.children:
            _render_step(child, x, indent + 1)
        x.add(indent, "</SEQUENCE>")
    elif isinstance(step, Branch):
        x.add(indent, f"<BRANCH SWITCH={_attr(step.switch.render())}>")
        for label, child in step.cases:
            x.add(indent + 1, f"<!-- case {escape(label)} -->")
            _render_step(child, x, indent + 1)
        x.add(indent, "</BRANCH>")
    elif isinstance(step, Loop):
        x.add(indent, f"<LOOP IN-ARRAY={_attr(step.in_array.render())}>")
        for child in step.children:
            _render_step(child, x, indent + 1)
        x.add(indent, "</LOOP>")
    else:  # pragma: no cover - defensive
        raise TypeError(f"unrenderable step: {type(step).__name__}")


def render_flow(service: FlowService) -> str:
    x = _Xml()
    x.add(0, '<?xml version="1.0" encoding="UTF-8"?>')
    if service.comment:
        x.add(0, f"<!-- {escape(service.comment)} -->")
    x.add(0, '<FLOW VERSION="3.0" CLEANUP="true">')
    for step in service.steps:
        _render_step(step, x, 1)
    x.add(0, "</FLOW>")
    return "\n".join(x.lines) + "\n"
