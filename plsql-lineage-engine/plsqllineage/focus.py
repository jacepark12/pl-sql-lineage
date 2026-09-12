"""Structured agent-focus events for the localhost lineage viewer.

MCP tools keep returning budgeted COL/EDGE/DIAG text. This module projects that
same (possibly truncated) text into a JSON snapshot the canvas can paint.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COL_RE = re.compile(r"^COL (\S+)\s*$")
EDGE_RE = re.compile(r"^EDGE (\S+) (.+) --> (\S+)\s*$")
COLUMN_HEADER_RE = re.compile(r"^Column:\s+(\S+)\s*$")
PATH_ENDS_RE = re.compile(r"^\s+(\S+) -> (\S+)\s*$")

MAX_FOCUS_COLUMNS = 160
MAX_FOCUS_EDGES = 500

_ERROR_PREFIXES = (
    "No engine JSON",
    "Engine JSON is corrupted",
    "Engine JSON not found",
    "Ambiguous:",
    "No column matching",
    "No path from",
    "expected engine JSON",
)


@dataclass
class FocusEvent:
    v: int
    ts: str
    tool: str
    seed: str | None
    columns: list[str]
    edges: list[dict[str, str]]
    graph: str
    seq: int = 0
    truncated: bool = False
    omitted_columns: int = 0
    omitted_edges: int = 0
    note: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "v": self.v,
            "ts": self.ts,
            "tool": self.tool,
            "seed": self.seed,
            "columns": list(self.columns),
            "edges": [dict(edge) for edge in self.edges],
            "graph": self.graph,
            "seq": self.seq,
            "truncated": self.truncated,
        }
        if self.omitted_columns:
            payload["omitted_columns"] = self.omitted_columns
        if self.omitted_edges:
            payload["omitted_edges"] = self.omitted_edges
        if self.note:
            payload["note"] = self.note
        return payload


class FocusHub:
    """Latest-focus snapshot plus a condition variable for SSE waiters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._seq = 0
        self._event: FocusEvent | None = None

    def publish(self, event: FocusEvent) -> FocusEvent:
        with self._cv:
            self._seq += 1
            event.seq = self._seq
            self._event = event
            self._cv.notify_all()
            return event

    def snapshot(self) -> FocusEvent | None:
        with self._lock:
            return self._event

    def wait_after(self, seq: int, timeout: float) -> FocusEvent | None:
        with self._cv:
            if self._event is not None and self._event.seq > seq:
                return self._event
            self._cv.wait(timeout)
            if self._event is not None and self._event.seq > seq:
                return self._event
            return None

    def clear(self) -> None:
        with self._cv:
            self._event = None
            self._cv.notify_all()


def digest_file(path: Path | str) -> str:
    data = Path(path).read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def projection_is_focusable(text: str, tool: str = "") -> bool:
    """True when the tool result is a successful projection, not an error string."""
    del tool
    if not text or not str(text).strip():
        return False
    stripped = str(text).lstrip()
    for prefix in _ERROR_PREFIXES:
        if stripped.startswith(prefix):
            return False
    if "both resolved to" in stripped and "Use two different FQNs" in stripped:
        return False
    return True


def _split_sources(raw: str) -> list[str]:
    parts = [part.strip() for part in raw.split(",")]
    return [part for part in parts if part]


def parse_projection(text: str) -> tuple[str | None, list[str], list[dict[str, str]], bool]:
    """Pull seed / columns / edges from rendered COL/EDGE text."""
    seed: str | None = None
    columns: list[str] = []
    seen_cols: set[str] = set()
    edges: list[dict[str, str]] = []
    truncated = False

    def add_column(fqn: str) -> None:
        if not fqn or fqn == "(unresolved)":
            return
        key = fqn.upper()
        if key in seen_cols:
            return
        seen_cols.add(key)
        columns.append(fqn)

    for line in text.splitlines():
        if line.startswith("[!] TRUNCATED") or line.startswith("... (truncated"):
            truncated = True
        header = COLUMN_HEADER_RE.match(line)
        if header and seed is None:
            seed = header.group(1)
            add_column(seed)
            continue
        path_ends = PATH_ENDS_RE.match(line)
        if path_ends and seed is None:
            seed = path_ends.group(1)
            add_column(path_ends.group(1))
            add_column(path_ends.group(2))
            continue
        col = COL_RE.match(line)
        if col:
            add_column(col.group(1))
            if seed is None:
                seed = col.group(1)
            continue
        edge = EDGE_RE.match(line)
        if not edge:
            continue
        kind, raw_sources, target = edge.group(1), edge.group(2), edge.group(3)
        add_column(target)
        for source in _split_sources(raw_sources):
            add_column(source)
            if source == "(unresolved)":
                continue
            edges.append({"kind": kind, "source": source, "target": target})
    return seed, columns, edges, truncated


def cap_focus(
    seed: str | None,
    columns: list[str],
    edges: list[dict[str, str]],
    *,
    max_columns: int = MAX_FOCUS_COLUMNS,
    max_edges: int = MAX_FOCUS_EDGES,
) -> tuple[list[str], list[dict[str, str]], int, int]:
    """Prefer the seed and its incident neighbors when the walk exceeds canvas caps."""
    if len(columns) <= max_columns and len(edges) <= max_edges:
        return columns, edges, 0, 0
    seed_key = seed.upper() if seed else ""
    incident: list[dict[str, str]] = []
    rest: list[dict[str, str]] = []
    for edge in edges:
        if seed_key and (
            edge["source"].upper() == seed_key or edge["target"].upper() == seed_key
        ):
            incident.append(edge)
        else:
            rest.append(edge)
    keep_edges = (incident + rest)[:max_edges]
    kept_cols: list[str] = []
    seen: set[str] = set()

    def add(fqn: str) -> None:
        if not fqn or fqn == "(unresolved)":
            return
        key = fqn.upper()
        if key in seen:
            return
        seen.add(key)
        kept_cols.append(fqn)

    if seed:
        add(seed)
    for edge in keep_edges:
        add(edge["source"])
        add(edge["target"])
        if len(kept_cols) >= max_columns:
            break
    if len(kept_cols) < max_columns:
        for fqn in columns:
            add(fqn)
            if len(kept_cols) >= max_columns:
                break
    omitted_columns = max(0, len(columns) - len(kept_cols))
    omitted_edges = max(0, len(edges) - len(keep_edges))
    return kept_cols, keep_edges, omitted_columns, omitted_edges


def focus_event_from_text(
    text: str,
    *,
    tool: str,
    graph: str,
    seed_hint: str | None = None,
) -> FocusEvent | None:
    if not projection_is_focusable(text, tool):
        return None
    seed, columns, edges, truncated = parse_projection(text)
    if seed is None and seed_hint and columns:
        seed = seed_hint
    if seed is None and seed_hint and tool in {"query_lineage", "explain_column"}:
        seed = seed_hint
    columns, edges, omitted_columns, omitted_edges = cap_focus(seed, columns, edges)
    note = None
    if tool in {"diagnose", "graph_stats"} and not columns and not edges:
        first = next((line for line in text.splitlines() if line.strip()), tool)
        note = first[:160]
    return FocusEvent(
        v=1,
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tool=tool,
        seed=seed,
        columns=columns,
        edges=edges,
        graph=graph,
        truncated=truncated or omitted_columns > 0 or omitted_edges > 0,
        omitted_columns=omitted_columns,
        omitted_edges=omitted_edges,
        note=note,
    )
