"""Read a DDL catalog into ``table -> column names``.

The corpus writes ``out/ddl/catalog.sql`` so ``SELECT *`` / ``alias.*`` can be
expanded to real columns. The generator emits one column per line, which keeps
parsing simple: ``NUMBER(13,3)`` commas never split a definition.
"""

from __future__ import annotations

import re

_TABLE = re.compile(
    r"CREATE\s+TABLE\s+([\w.]+)\s*\((.*?)\);",
    re.IGNORECASE | re.DOTALL,
)


def load_catalog(sql: str) -> dict[str, list[str]]:
    """Parse ``CREATE TABLE schema.name (...)`` blocks into column lists."""

    catalog: dict[str, list[str]] = {}
    for match in _TABLE.finditer(sql):
        table = match.group(1).upper()
        columns: list[str] = []
        for raw in match.group(2).splitlines():
            line = raw.strip().rstrip(",")
            if not line or line.upper().startswith("CONSTRAINT"):
                continue
            name = line.split()[0]
            if name:
                columns.append(name)
        if columns:
            catalog[table] = columns
    return catalog


def columns_for(catalog: dict[str, list[str]], table: str) -> list[str]:
    """Columns of ``table``, matching a qualified name or an unambiguous short name.

    ``schema.table@LINK`` looks up the local ``schema.table`` shape. Identity of
    the remote object stays on the lineage Ref; the catalog only supplies names.
    """

    key = table.upper().split("@")[0]
    if key in catalog:
        return catalog[key]
    short = key.split(".")[-1]
    matches = [cols for name, cols in catalog.items() if name.split(".")[-1] == short]
    return matches[0] if len(matches) == 1 else []
