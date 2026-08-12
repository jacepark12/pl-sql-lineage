"""JDBC adapter services: the metadata, the binary blob, and the node.ndf.

This is where the lineage actually lives. The XML around it says almost nothing
useful - which connection, which schema, which table, which column each field
lands in, and what expression the database applies on the way in are all inside
the base64 ``IRTNODE_PROPERTY`` blob. ``update.expression`` is the sharpest
example: a value like ``SYNCRYPT.FN_ENC(?)`` appears as SQL text nowhere in the
package, so an engine that skips the blob cannot know the column is encrypted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from synplsql import schema as S

from . import wmvalues

TEMPLATE_PREFIX = "com.wm.adapter.wmjdbc.services"

SELECT = "Select"
INSERT = "Insert"
UPDATE = "Update"
CUSTOM_SQL = "CustomSQL"

#: java.sql.Types codes, as the adapter records them in ``tables.columnInfo``.
_JDBC_TYPES = {"VARCHAR2": 12, "CHAR": 1, "NUMBER": 3, "DATE": 93}


def jdbc_type(dtype: str) -> int:
    return _JDBC_TYPES.get(dtype.split("(")[0].upper(), 12)


def column_info(table: S.Table) -> list[str]:
    """``tables.columnInfo`` entries: name, declared type, JDBC type, nullability."""

    out = []
    for c in table.columns:
        not_null = " NOT NULL" if c.name in table.pk else ""
        nullable = 0 if c.name in table.pk else 1
        out.append(f"{c.name}\n{c.dtype}{not_null}\n{jdbc_type(c.dtype)}\n{nullable}\n")
    return out


@dataclass
class Adapter:
    """One adapter service, in the form the pipeline simulator needs."""

    name: str                        # IF_ITEM_RCV_I_01
    template: str                    # Select | Insert | Update | CustomSQL
    connection: str
    schema: str
    table: str
    #: Select: output field name -> source column. Insert/Update: target column
    #: -> pipeline input field name.
    field_map: dict[str, str] = field(default_factory=dict)
    #: Insert/Update only: target column -> SQL expression, ``?`` when plain.
    expressions: dict[str, str] = field(default_factory=dict)
    #: Update only: columns in the WHERE clause. They gate the write, so they
    #: are INDIRECT_FILTER sources, not value sources.
    where_columns: tuple[str, ...] = ()
    #: Select only: extra joined tables, as (schema, table, left_col, right_col).
    joins: tuple[tuple[str, str, str, str], ...] = ()
    #: Select only: which table each referenced column belongs to. A joined
    #: Select reads columns from more than one table, and the truth has to name
    #: the right one.
    column_table: dict[str, str] = field(default_factory=dict)
    #: Select only: WHERE predicates, as (fq table, column, operator, literal).
    filter_columns: tuple[tuple[str, str, str, str], ...] = ()
    #: CustomSQL only.
    sql: str | None = None

    @property
    def fq_table(self) -> str:
        return f"{self.schema}.{self.table}"

    @property
    def template_name(self) -> str:
        return f"{TEMPLATE_PREFIX}.{self.template}"

    def values(self) -> dict:
        """The record that gets serialised into IRTNODE_PROPERTY."""

        table = S.CATALOG[self.fq_table]
        rec: dict = {
            "serviceTemplateName": self.template_name,
            "adapterTypeName": "JDBCAdapter",
            "connectionName": self.connection,
            "tables.realSchemaName": self.schema,
            "tables.schemaName": self.schema,
            "tables.tableName": self.table,
            "tables.columnInfo": column_info(table),
        }
        if self.joins:
            rec["joins.leftTable"] = [j[0] + "." + j[1] for j in self.joins]
            rec["joins.leftColumn"] = [j[2] for j in self.joins]
            rec["joins.rightColumn"] = [j[3] for j in self.joins]

        if self.template == SELECT:
            fields = list(self.field_map.keys())
            rec["select.outputField"] = fields
            rec["select.refColumn"] = [self.field_map[f] for f in fields]
            rec["select.refTable"] = [
                self.column_table.get(self.field_map[f], self.fq_table) for f in fields]
            rec["select.maxRows"] = 0
            if self.filter_columns:
                rec["select.whereColumn"] = [c for _, c, _, _ in self.filter_columns]
                rec["select.whereOperator"] = [o for _, _, o, _ in self.filter_columns]
                rec["select.whereValue"] = [v for _, _, _, v in self.filter_columns]
        elif self.template in (INSERT, UPDATE):
            columns = list(self.field_map.keys())
            rec["update.column"] = columns
            rec["update.inputField"] = [self.field_map[c] for c in columns]
            rec["update.expression"] = [self.expressions.get(c, "?") for c in columns]
            rec["update.batchSize"] = 1000
            if self.template == UPDATE:
                rec["update.whereColumn"] = list(self.where_columns)
                rec["update.whereExpression"] = ["?" for _ in self.where_columns]
        elif self.template == CUSTOM_SQL:
            rec["customSQL.sql"] = self.sql or ""
            rec["customSQL.inputField"] = list(self.field_map.values())
            rec["customSQL.outputField"] = list(self.field_map.keys())
        return rec

    def blob(self) -> str:
        return wmvalues.encode_b64(self.values())


def _sig_fields(names: list[str], indent: int) -> list[str]:
    pad = "  " * indent
    out = []
    for n in names:
        out.append(f'{pad}<record javaclass="com.wm.util.Values">')
        out.append(f'{pad}  <value name="field_name">{escape(n)}</value>')
        out.append(f'{pad}  <value name="field_type">0</value>')
        out.append(f'{pad}  <value name="field_dim">0</value>')
        out.append(f'{pad}  <value name="field_opt">true</value>')
        out.append(f"{pad}</record>")
    return out


def _wrap_b64(text: str, width: int = 76) -> str:
    return "\n".join(text[i:i + width] for i in range(0, len(text), width))


def render_node_ndf(adapter: Adapter, ns: str) -> str:
    """The adapter service node. Everything that matters is in the blob."""

    table = S.CATALOG[adapter.fq_table]
    if adapter.template == SELECT:
        in_fields = [c for c in table.column_names if c in adapter.field_map.values()][:2]
        out_fields = list(adapter.field_map.keys())
    else:
        in_fields = [adapter.field_map[c] for c in adapter.field_map]
        out_fields = ["updateCount"]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Values version="2.0">',
        '  <value name="node_type">adapterService</value>',
        '  <value name="svc_type">adapterService</value>',
        '  <value name="adapterTypeName">JDBCAdapter</value>',
        f'  <value name="adapterServiceTemplateName">{escape(adapter.template_name)}</value>',
        f'  <value name="node_nsName">{escape(ns)}:{escape(adapter.name)}</value>',
        '  <value name="node_comment">합성 코퍼스 자동 생성 어댑터. 실제 연계가 아닙니다.</value>',
        '  <!-- 연결/스키마/테이블/컬럼 바인딩은 아래 IRTNODE_PROPERTY 안에만 있습니다. -->',
        '  <value name="IRTNODE_PROPERTY">',
        _wrap_b64(adapter.blob()),
        '  </value>',
        '  <record name="sig" javaclass="com.wm.util.Values">',
        '    <record name="in" javaclass="com.wm.util.Values">',
        '      <array name="rec_fields" depth="1" type="record"'
        ' javaclass="[Lcom.wm.util.Values;">',
    ]
    lines += _sig_fields(in_fields, 4)
    lines += [
        '      </array>',
        '    </record>',
        '    <record name="out" javaclass="com.wm.util.Values">',
        '      <array name="rec_fields" depth="1" type="record"'
        ' javaclass="[Lcom.wm.util.Values;">',
    ]
    lines += _sig_fields(out_fields, 4)
    lines += [
        '      </array>',
        '    </record>',
        '  </record>',
        '</Values>',
    ]
    return "\n".join(lines) + "\n"


# --- builders -----------------------------------------------------------------


def build_select(iface: S.EaiInterface, doc_fields: dict[str, str]) -> Adapter:
    """Select adapter: reads the source table into the source document type."""

    src = S.CATALOG[iface.source]
    joins = tuple(
        (j.fq.split(".")[0], j.fq.split(".")[1], left, right)
        for j in iface.joins for left, right in j.on
    )
    owner: dict[str, str] = {c: iface.source for c in src.column_names}
    for j in iface.joins:
        for c in S.CATALOG[j.fq].column_names:
            owner.setdefault(c, j.fq)

    filters = tuple(
        (owner.get(col, iface.source), col, op, literal)
        for col, op, literal in iface.filters
    )
    return Adapter(
        name=f"{iface.source_table}_S_01",
        template=SELECT,
        connection=iface.source_conn,
        schema=iface.source.split(".")[0],
        table=src.name,
        field_map=dict(doc_fields),
        joins=joins,
        column_table=owner,
        filter_columns=filters,
    )


def build_writer(iface: S.EaiInterface, field_map: dict[str, str]) -> Adapter:
    """Insert or Update adapter: writes the target document into the table."""

    tgt = S.CATALOG[iface.target]
    where = tuple(c for c in iface.key_columns if tgt.has(c)) or (tgt.pk[0],)
    return Adapter(
        name=f"{iface.target_table}_{'U' if iface.write_op == UPDATE else 'I'}_01",
        template=iface.write_op,
        connection=iface.target_conn,
        schema=iface.target.split(".")[0],
        table=tgt.name,
        field_map=dict(field_map),
        expressions=dict(iface.expressions),
        where_columns=where if iface.write_op == UPDATE else (),
    )


def build_custom_sql(iface: S.EaiInterface) -> Adapter:
    """CustomSQL adapter: arbitrary SQL, so it needs the SQL engine, not the
    adapter reader. That shared need is why one lineage engine should cover
    both corpora."""

    tgt = S.CATALOG[iface.target]
    key = (iface.key_columns or tgt.pk)[0]
    return Adapter(
        name=f"{iface.target_table}_X_01",
        template=CUSTOM_SQL,
        connection=iface.target_conn,
        schema=iface.target.split(".")[0],
        table=tgt.name,
        field_map={"rowCount": "IF_YMD"},
        sql=(f"UPDATE {iface.target} SET IF_STAT_CD = '90' "
             f"WHERE {key} = ? AND IF_STAT_CD = '10'"),
    )
