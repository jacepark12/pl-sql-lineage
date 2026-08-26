"""Load engine ``edges`` JSON into the column-lineage sqlite stub.

The schema is docs/column-lineage-schema.md. This module is a smoke loader,
not a promote/review workflow. Engine rows are written ``accepted`` so the
``column_lineage_edge`` view is queryable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sqlite3
import sys

SCHEMA_SQL = pathlib.Path(__file__).resolve().parent / "sql" / "column_lineage.sql"

# Design §8 maps the truth-set INDIRECT_FILTER label to FILTER.
KIND_MAP = {"INDIRECT_FILTER": "FILTER", "INDIRECT": "FILTER"}

ASSERTED_BY = {"engine": "plsqllineage", "method": "static-parse"}


def connect(path: str | pathlib.Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    return conn


def split_table(ref: dict) -> tuple[str, str]:
    """Return (schema_, table_) with @LINK kept on table_ when remote."""

    table = str(ref.get("table") or "").strip()
    link = str(ref.get("dblink") or "").strip()
    if link and "@" not in table:
        table = f"{table}@{link}"
    base, _, dblink = table.partition("@")
    if "." in base:
        schema, name = base.split(".", 1)
    else:
        schema, name = "", base
    if dblink:
        name = f"{name}@{dblink}"
    return schema, name


def _md5(*parts: object) -> str:
    text = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def upsert_column_ref(conn: sqlite3.Connection, ref: dict) -> int:
    schema, table = split_table(ref)
    column = ref.get("column")
    if column is not None:
        column = str(column).strip() or None
    row = conn.execute(
        "SELECT id FROM column_ref "
        "WHERE schema_ = ? AND table_ = ? AND IFNULL(column_, '') = IFNULL(?, '')",
        (schema, table, column),
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO column_ref (schema_, table_, column_) VALUES (?, ?, ?)",
        (schema, table, column),
    )
    return int(cur.lastrowid)


def _kind(raw: str | None) -> str:
    folded = (raw or "DIRECT").strip().upper()
    return KIND_MAP.get(folded, folded)


def load_edges(conn: sqlite3.Connection, data: dict, *,
               source_rev: str = "unknown",
               method: str = "static-parse",
               status: str = "accepted") -> int:
    """Insert engine (or truth) edges. Returns the number of assertion rows kept."""

    inserted = 0
    for edge in data.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        target = edge.get("target")
        if not isinstance(target, dict) or not target.get("table"):
            continue
        to_id = upsert_column_ref(conn, target)
        from_ids = []
        for source in edge.get("sources") or []:
            if isinstance(source, dict) and source.get("table"):
                from_ids.append(upsert_column_ref(conn, source))
        from_ids = sorted(set(from_ids))
        kind = _kind(edge.get("kind"))
        expression = edge.get("transform") or edge.get("expression") or ""
        loc = edge.get("location") or {}
        if not isinstance(loc, dict):
            loc = {}
        path = str(loc.get("file") or "")
        body = expression or path or ""
        container = {k: loc[k] for k in ("package", "procedure", "function")
                     if loc.get(k)}
        evid = _md5(source_rev, path, body)
        conn.execute(
            "INSERT OR IGNORE INTO evidence "
            "(id, source_rev, path, container, body) VALUES (?, ?, ?, ?, ?)",
            (evid, source_rev, path, json.dumps(container, ensure_ascii=False),
             body),
        )
        span = {k: loc[k] for k in ("file", "line") if loc.get(k) is not None}
        aid = _md5(to_id, ",".join(str(i) for i in from_ids), kind,
                   expression, method)
        cur = conn.execute(
            "INSERT OR IGNORE INTO column_lineage_assertion "
            "(id, to_column, from_columns, kind, expression, evidence_id, "
            " span, method, status, asserted_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (aid, to_id, json.dumps(from_ids), kind, expression or None, evid,
             json.dumps(span, ensure_ascii=False), method, status,
             json.dumps(ASSERTED_BY, ensure_ascii=False)),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def sources_for(conn: sqlite3.Connection, schema: str, table: str,
                column: str) -> list[str]:
    """``from_fqn`` values that flow into ``schema.table.column``."""

    fqn = f"{schema}.{table}.{column}"
    rows = conn.execute(
        "SELECT from_fqn FROM column_lineage_edge WHERE to_fqn = ? "
        "ORDER BY from_fqn",
        (fqn,),
    ).fetchall()
    return [row["from_fqn"] for row in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="plsqllineage.store",
        description="엔진 edges JSON 을 sqlite 컬럼 리니지 스텁에 적재")
    ap.add_argument("--input", "-i", required=True, type=pathlib.Path)
    ap.add_argument("--db", required=True, type=pathlib.Path,
                    help="sqlite 파일 경로")
    ap.add_argument("--source-rev", default="unknown")
    args = ap.parse_args(argv)

    if not args.input.exists():
        print(f"입력을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        return 1

    data = json.loads(args.input.read_text(encoding="utf-8"))
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db)
    n = load_edges(conn, data, source_rev=args.source_rev)
    tables = conn.execute("SELECT count(*) FROM column_ref").fetchone()[0]
    print(f"assertion {n}  column_ref {tables}  db {args.db}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
