"""Scenario builders: one construct family per builder, tagged by tier.

A scenario turns a :class:`~synplsql.schema.Flow` into IR statements. The tier
of a scenario decides which packages may contain it (see the tier mix in
``profile.json``). Every construct a scenario emits is reported to the
:class:`Budget` so the corpus converges on the measured syntax distribution
instead of whatever the templates happen to produce.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field

from . import schema as S
from .core import (
    AGGREGATE,
    ANALYTIC,
    DIRECT,
    TRANSFORM,
    ColRef,
    CursorLoop,
    Delete,
    Expr,
    ExecImmediate,
    Assign,
    ForAll,
    ForLoop,
    IfBlock,
    InsertSelect,
    InsertValues,
    Lit,
    Merge,
    OpenRefCursor,
    Package,
    Param,
    Raw,
    ScalarSubquery,
    Select,
    SelectInto,
    Star,
    Stmt,
    Subprogram,
    TableRef,
    Update,
    Var,
    cond,
    e_col,
    e_lit,
    esc,
)

# --- construct budget ---------------------------------------------------------


class Budget:
    """Paces construct emission against the measured per-1K-line rates."""

    def __init__(self, profile: dict, target_lines: int) -> None:
        self.total_lines = max(1, target_lines)
        self.target: dict[str, float] = {}
        for name, cfg in profile["constructs"].items():
            self.target[name] = cfg["per_1k_lines"] * self.total_lines / 1000.0
        self.count: dict[str, int] = defaultdict(int)
        self.lines = 0

    def note_lines(self, n: int) -> None:
        self.lines += n

    @property
    def progress(self) -> float:
        return min(1.0, self.lines / self.total_lines)

    def allowance(self, name: str, slack: float = 0.15) -> float:
        """How much of a construct's quota may be spent at the current point of
        the run. Pacing keeps the distribution even across the corpus instead of
        front-loading every construct into the first few packages."""

        t = self.target.get(name, 0.0)
        return t * min(1.0, self.progress + slack)

    def want(self, name: str, slack: float = 0.15) -> bool:
        if self.target.get(name, 0.0) <= 0:
            return False
        return self.count[name] < self.allowance(name, slack)

    def pressure(self, name: str) -> float:
        """0.0 = quota spent for now, 1.0 = nothing emitted yet."""

        t = self.target.get(name, 0.0)
        if t <= 0:
            return 0.0
        return max(0.0, (self.allowance(name) - self.count[name]) / t)

    def take(self, name: str, n: int = 1) -> None:
        self.count[name] += n

    def report(self) -> dict[str, dict[str, float]]:
        return {
            name: {"target": round(t, 1), "emitted": self.count[name]}
            for name, t in sorted(self.target.items())
        }


# --- naming -------------------------------------------------------------------

DOMAIN_BY_TARGET = {
    "SYNWMS.MST_ITEM": ("MST", "품목 기준정보"),
    "SYNWMS.INB_ORDER_D": ("INB", "입고예정"),
    "SYNWMS.INB_RESULT": ("INB", "입고실적"),
    "SYNWMS.STK_ONHAND": ("STK", "재고"),
    "SYNWMS.STK_TRX": ("STK", "재고이동"),
    "SYNWMS.OUT_ALLOC": ("OUT", "출고할당"),
    "SYNWMS.OUT_PICK": ("OUT", "피킹"),
    "SYNWMS.OUT_SHIP": ("OUT", "출고확정"),
    "SYNIF.IF_ORDER_SND": ("IFC", "출고 인터페이스"),
    "SYNIF.IF_STOCK_SND": ("IFC", "재고 인터페이스"),
    "SYNWMS.RPT_DAILY_STK": ("RPT", "일별 재고집계"),
    "SYNWMS.RPT_MONTHLY_TRX": ("RPT", "월별 거래집계"),
    "SYNARC.ARC_STK_TRX": ("ARC", "이동이력 아카이브"),
    "SYNARC.ARC_OUT_SHIP": ("ARC", "출고 아카이브"),
}

VERBS = (
    ("APPLY", "반영"), ("SYNC", "동기화"), ("MAKE", "생성"), ("CLOSE", "마감"),
    ("SEND", "송신"), ("MERGE", "병합"), ("CALC", "산출"), ("MOVE", "이관"),
    ("CHECK", "점검"), ("CLEAN", "정리"), ("SPLIT", "분할"), ("SUM", "집계"),
)

NOUNS = (
    ("RESULT", "실적"), ("STOCK", "재고"), ("ORDER", "전표"), ("BATCH", "배치"),
    ("SNAP", "스냅샷"), ("DAILY", "일마감"), ("HIST", "이력"), ("PLAN", "계획"),
)


# --- flow helpers -------------------------------------------------------------


class FlowCtx:
    """Alias/column bookkeeping for one flow."""

    def __init__(self, flow: S.Flow, rng: random.Random, link: str | None = None) -> None:
        self.flow = flow
        self.rng = rng
        self.alias_map = dict(flow.alias_map)
        self.link = link

    def table_of(self, alias: str) -> str:
        fq = self.alias_map[alias]
        if self.link and fq == self.flow.base[0]:
            return f"{fq}@{self.link}"
        return fq

    def parse(self, spec: str) -> ColRef | None:
        if "." not in spec:
            return None
        alias, _, col = spec.partition(".")
        if alias not in self.alias_map:
            return None
        tbl = S.CATALOG.get(self.alias_map[alias])
        if tbl is None or not tbl.has(col):
            return None
        return ColRef(self.table_of(alias), col, alias)

    def refs(self, predicate) -> list[ColRef]:
        out: list[ColRef] = []
        for alias, fq in self.alias_map.items():
            for c in S.CATALOG[fq].columns:
                if predicate(c.name):
                    out.append(ColRef(self.table_of(alias), c.name, alias))
        return out

    def code_ref(self) -> ColRef | None:
        pool = self.refs(lambda n: n.endswith(("_CD", "_YN")))
        return self.rng.choice(pool) if pool else None

    def qty_ref(self) -> ColRef | None:
        pool = self.refs(lambda n: "QTY" in n or "WGT" in n)
        return self.rng.choice(pool) if pool else None

    def date_ref(self) -> ColRef | None:
        pool = self.refs(lambda n: n.endswith(("_YMD", "_DTM")))
        return self.rng.choice(pool) if pool else None

    def base_ref(self, column: str) -> ColRef:
        return ColRef(self.table_of(self.flow.base[1]), column, self.flow.base[1])


def is_numeric(flow: S.Flow, column: str) -> bool:
    tbl = S.CATALOG[flow.target]
    return tbl.has(column) and tbl.column(column).dtype.startswith("NUMBER")


# --- expression decorators ----------------------------------------------------


def _case_value(g: "Gen", fctx: FlowCtx, ref: ColRef, numeric: bool) -> Expr:
    c = fctx.code_ref()
    if c is None:
        return e_col(ref)
    g.budget.take("CASE_WHEN")
    zero = "0" if numeric else "' '"
    return Expr(
        "CASE WHEN {1} = '10' THEN {0} ELSE " + zero + " END",
        (ref,), TRANSFORM, (c,),
    )


def _case_two_branch(g: "Gen", fctx: FlowCtx, ref: ColRef, numeric: bool) -> Expr:
    c = fctx.code_ref()
    alt = fctx.qty_ref() if numeric else None
    if c is None or alt is None:
        return _case_value(g, fctx, ref, numeric)
    g.budget.take("CASE_WHEN")
    return Expr(
        "CASE WHEN {2} IN ('10', '20') THEN {0}\n"
        "                 WHEN {2} = '30'          THEN {1}\n"
        "                 ELSE 0\n"
        "            END",
        (ref, alt), TRANSFORM, (c,),
    )


def _decode(g: "Gen", fctx: FlowCtx, ref: ColRef, numeric: bool) -> Expr:
    c = fctx.code_ref()
    if c is None:
        return e_col(ref)
    g.budget.take("DECODE")
    default = "0" if numeric else "'*'"
    return Expr("DECODE({1}, 'Y', {0}, 'N', " + default + ", {0})", (ref,), TRANSFORM, (c,))


def _nvl(g: "Gen", fctx: FlowCtx, ref: ColRef, numeric: bool) -> Expr:
    if numeric:
        return Expr("NVL({0}, 0)", (ref,), TRANSFORM)
    return Expr("NVL(TRIM({0}), '-')", (ref,), TRANSFORM)


def _arith(g: "Gen", fctx: FlowCtx, ref: ColRef, numeric: bool) -> Expr:
    other = fctx.qty_ref()
    if not numeric or other is None:
        return _nvl(g, fctx, ref, numeric)
    return Expr("ROUND(NVL({0}, 0) * NVL({1}, 1), 3)", (ref, other), TRANSFORM)


def _aggregate(g: "Gen", fctx: FlowCtx, ref: ColRef, numeric: bool) -> Expr:
    if not numeric:
        return Expr("MAX({0})", (ref,), AGGREGATE)
    fn = g.rng.choice(("SUM", "SUM", "MAX", "MIN"))
    return Expr(f"{fn}(NVL({{0}}, 0))", (ref,), AGGREGATE)


def _analytic(g: "Gen", fctx: FlowCtx, ref: ColRef, numeric: bool) -> Expr:
    part = fctx.code_ref() or fctx.base_ref(S.CATALOG[fctx.flow.base[0]].column_names[0])
    g.budget.take("ANALYTIC_OVER")
    if numeric:
        return Expr("SUM({0}) OVER (PARTITION BY {1} ORDER BY {0})", (ref, part), ANALYTIC)
    return Expr("MAX({0}) OVER (PARTITION BY {1})", (ref, part), ANALYTIC)


DECORATORS = {
    "CASE_WHEN": _case_value,
    "CASE_WHEN2": _case_two_branch,
    "DECODE": _decode,
    "NVL": _nvl,
    "ARITH": _arith,
}

DECORATOR_QUOTA = {"CASE_WHEN": "CASE_WHEN", "CASE_WHEN2": "CASE_WHEN", "DECODE": "DECODE"}


# --- generator state ----------------------------------------------------------


@dataclass
class Gen:
    rng: random.Random
    budget: Budget
    profile: dict
    seq: int = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def pick_decorator(self, tier: int) -> str | None:
        if tier <= 0:
            return None
        names = ["NVL", "ARITH"]
        weights = [1.0, 0.6]
        for name in ("CASE_WHEN", "CASE_WHEN2", "DECODE"):
            quota = DECORATOR_QUOTA[name]
            p = self.budget.pressure(quota)
            if self.budget.want(quota):
                names.append(name)
                weights.append(1.0 + 6.0 * p)
        if self.rng.random() < 0.30:
            return None
        return self.rng.choices(names, weights=weights, k=1)[0]


def build_value(g: Gen, fctx: FlowCtx, target_col: str, spec: str, tier: int,
                allow_aggregate: bool = False) -> Expr:
    """Turn one flow mapping entry into a rendered/lineage-carrying expression."""

    ref = fctx.parse(spec)
    numeric = is_numeric(fctx.flow, target_col)
    if ref is None:
        # literal source: still worth a conditional so filter lineage exists.
        # Sequence pseudocolumns are excluded - NEXTVAL is not legal in a CASE.
        if (tier >= 1 and "NEXTVAL" not in spec
                and g.budget.want("CASE_WHEN") and g.rng.random() < 0.25):
            c = fctx.code_ref()
            if c is not None:
                g.budget.take("CASE_WHEN")
                return Expr("CASE WHEN {0} IS NULL THEN " + esc(spec) + " ELSE " + esc(spec) + " END",
                            (), TRANSFORM, (c,))
        return e_lit(spec)

    if allow_aggregate and target_col in fctx.flow.quantity_columns:
        return _aggregate(g, fctx, ref, numeric)

    name = g.pick_decorator(tier)
    if name is None:
        return e_col(ref)
    return DECORATORS[name](g, fctx, ref, numeric)


def build_from(g: Gen, fctx: FlowCtx, old_style: bool = False, hint: str | None = None) -> Select:
    flow = fctx.flow
    tables = [TableRef(table=fctx.table_of(flow.base[1]), alias=flow.base[1])]
    for j in flow.joins:
        join_kw = "LEFT JOIN" if j.outer else "JOIN"
        on = tuple(
            cond("{0} = {1}", fctx.parse(l) or Lit(l), fctx.parse(r) or Lit(r))
            for l, r in j.on
        )
        tables.append(TableRef(table=j.fq, alias=j.alias, join=join_kw, on=on))
    if hint is None and g.budget.want("OPTIMIZER_HINT") and g.rng.random() < 0.85:
        hint = g.rng.choice((
            f"INDEX({flow.base[1]} PK_{S.CATALOG[flow.base[0]].name})",
            "USE_HASH(%s)" % " ".join([flow.base[1]] + [j.alias for j in flow.joins]),
            "FULL(%s) PARALLEL(%s 4)" % (flow.base[1], flow.base[1]),
            "LEADING(%s)" % flow.base[1],
        ))
    sel = Select(tables=tables, old_style_join=old_style, hint=hint)
    if old_style:
        # one (+) marker is rendered per predicate of each outer-joined table
        g.budget.take("OLD_OUTER_JOIN", sum(len(j.on) for j in flow.joins if j.outer))
    if hint:
        g.budget.take("OPTIMIZER_HINT")
    for left, op, right in flow.filters:
        ref = fctx.parse(left)
        if ref is not None:
            sel.where.append(cond("{0} " + esc(op) + " " + esc(right), ref))
    return sel


def flow_columns(g: Gen, flow: S.Flow, tier: int, limit: int | None = None) -> list[str]:
    cols = list(flow.mapping.keys())
    if limit is not None and len(cols) > limit:
        keep = list(flow.key_columns)
        rest = [c for c in cols if c not in keep]
        g.rng.shuffle(rest)
        cols = keep + rest[: max(0, limit - len(keep))]
        cols = [c for c in flow.mapping if c in set(cols)]
    return cols


# --- declaration + filler helpers ---------------------------------------------

_PLAIN_TYPES = ("NUMBER", "NUMBER(13,3)", "VARCHAR2(30)", "VARCHAR2(200)", "DATE")


SCRATCH_VARS = tuple(f"v_tmp_{i:02d}" for i in range(6))


def decl_block(g: Gen, fctx: FlowCtx, n: int) -> list[str]:
    """Local declarations. %TYPE anchors are emitted under budget control."""

    out: list[str] = []
    used: set[str] = set()
    pool = fctx.refs(lambda name: True)
    g.rng.shuffle(pool)
    for i in range(n):
        if pool and g.budget.want("TYPE_ANCHOR"):
            ref = pool[i % len(pool)]
            var = f"v_{ref.column.lower()}"
            if var in used:
                var = f"{var}_{i:02d}"
            used.add(var)
            g.budget.take("TYPE_ANCHOR")
            out.append(f"{var:<22} {ref.table.split('@')[0]}.{ref.column}%TYPE;")
        else:
            var = f"v_val_{i:02d}"
            out.append(f"{var:<22} {g.rng.choice(_PLAIN_TYPES)};")
    if g.budget.want("TYPE_ANCHOR") and pool:
        g.budget.take("TYPE_ANCHOR")
        out.append(f"{'r_row':<22} {S.CATALOG[fctx.flow.target].fq}%ROWTYPE;")
    # scratch variables the procedural filler is allowed to touch
    for i, var in enumerate(SCRATCH_VARS):
        out.append(f"{var:<22} {'VARCHAR2(30)' if i % 2 else 'NUMBER'};")
    out.append(f"{'v_cnt':<22} NUMBER := 0;")
    out.append(f"{'v_err_cnt':<22} NUMBER := 0;")
    out.append(f"{'v_sql':<22} VARCHAR2(4000);")
    return out


_LOG_MSGS = (
    "처리 시작", "대상 건수 확인", "집계 구간 산출", "마감 대상 조회",
    "이관 대상 필터", "인터페이스 상태 갱신", "처리 종료", "구간 분할 처리",
    "재처리 대상 판정", "임계치 비교", "누적 카운터 갱신", "예외 건 분류",
    "배치 단위 조정", "선행 단계 완료 확인", "후처리 플래그 설정",
)

_ERR_MSGS = (
    "처리 대상이 임계치를 초과했습니다.",
    "선행 배치가 완료되지 않았습니다.",
    "기준 정보가 존재하지 않습니다.",
    "집계 구간이 올바르지 않습니다.",
)


def filler(g: Gen, fctx: FlowCtx, lines_wanted: int) -> list[Stmt]:
    """Non-lineage-bearing PL/SQL that only touches local variables.

    Filler exists for two reasons: real packages are mostly this, and the
    CASE/DECODE rates in ``profile.json`` are only reachable if procedural code
    contributes them too. Because it never references a table column, it adds
    no lineage the truth file would have to account for.
    """

    def num_var() -> str:
        return g.rng.choice(SCRATCH_VARS[0::2])

    def txt_var() -> str:
        return g.rng.choice(SCRATCH_VARS[1::2])

    stmts: list[Stmt] = []
    produced = 0
    while produced < lines_wanted:
        choice = g.rng.random()
        # The measured CASE rate (12.7 / 1K lines) is only reachable if
        # procedural code contributes too, so lean harder when it is behind.
        case_gate = 0.30 + 0.60 * g.budget.pressure("CASE_WHEN")
        if g.budget.want("CASE_WHEN") and choice < case_gate:
            g.budget.take("CASE_WHEN")
            var = txt_var()
            pad = " " * (len(var) + 3)
            stmts.append(Raw(lines=[
                f"-- {g.rng.choice(_LOG_MSGS)}",
                f"{var} := CASE WHEN v_cnt  > {g.rng.randrange(1, 900)} THEN '{g.rng.randrange(10, 99)}'",
                f"{pad}     WHEN v_cnt  = 0 THEN '00'",
                f"{pad}     WHEN v_err_cnt > 0 THEN '90'",
                f"{pad}     ELSE '99'",
                f"{pad}END;",
            ]))
            produced += 6
        elif g.budget.want("DECODE") and choice < case_gate + 0.13:
            g.budget.take("DECODE")
            stmts.append(Raw(lines=[
                f"{txt_var()} := DECODE(SIGN(v_cnt - {g.rng.randrange(1, 50)}), 1, 'Y', 0, 'E', 'N');",
            ]))
            produced += 1
        elif choice < 0.70:
            stmts.append(IfBlock(
                condition=f"v_cnt > {g.rng.randrange(0, 500)} AND {txt_var()} IS NOT NULL",
                body=[Raw(lines=[
                    "g_step_no := g_step_no + 1;",
                    f"{num_var()} := NVL({num_var()}, 0) + {g.rng.randrange(1, 9)};",
                ])],
                elsif=[(f"v_err_cnt > {g.rng.randrange(1, 20)}", [Raw(lines=[
                    "v_err_cnt := v_err_cnt + 1;",
                ])])],
                else_body=[Raw(lines=["g_step_no := g_step_no + 1;"])],
                comment=g.rng.choice(_LOG_MSGS),
            ))
            produced += 11
        elif choice < 0.80:
            var = num_var()
            stmts.append(Raw(lines=[
                f"-- {g.rng.choice(_LOG_MSGS)}",
                f"FOR i IN 1 .. {g.rng.randrange(2, 12)} LOOP",
                f"  {var} := NVL({var}, 0) + i;",
                f"  EXIT WHEN {var} > {g.rng.randrange(100, 9999)};",
                "END LOOP;",
            ]))
            produced += 5
        elif choice < 0.88:
            stmts.append(Raw(lines=[
                f"{txt_var()} := TO_CHAR(SYSDATE - {g.rng.randrange(1, 400)}, 'YYYYMMDD');",
                f"{num_var()} := TRUNC(NVL(v_cnt, 0) / {g.rng.randrange(2, 40)});",
            ]))
            produced += 2
        elif choice < 0.94:
            stmts.append(Raw(lines=[
                f"IF v_err_cnt > {g.rng.randrange(10, 200)} THEN",
                f"  RAISE_APPLICATION_ERROR(-{g.rng.randrange(20001, 20999)}, "
                f"'{g.rng.choice(_ERR_MSGS)}');",
                "END IF;",
            ]))
            produced += 3
        else:
            stmts.append(Raw(lines=[
                f"-- {g.rng.choice(_LOG_MSGS)}",
                "g_step_no := g_step_no + 1;",
            ]))
            produced += 2
    return stmts


# --- scenarios ----------------------------------------------------------------


@dataclass
class Built:
    stmts: list[Stmt] = field(default_factory=list)
    decls: list[str] = field(default_factory=list)
    params: list[Param] = field(default_factory=list)
    constructs: list[str] = field(default_factory=list)
    autonomous: bool = False


def sc_insert_simple(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 0 - single source table, 1:1 column mapping, explicit column list."""

    flow = fctx.flow
    cols = [c for c in flow.mapping if fctx.parse(flow.mapping[c]) is not None
            and fctx.parse(flow.mapping[c]).alias == flow.base[1]]
    cols = cols[:6] or list(flow.mapping)[:4]
    sel = Select(tables=[TableRef(table=fctx.table_of(flow.base[1]), alias=flow.base[1])])
    for c in cols:
        sel.items.append((c, build_value(g, fctx, c, flow.mapping[c], tier=0)))
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(target=flow.target, columns=cols, select=sel,
                                     comment=f"{flow.name} 단순 적재")],
                 constructs=["INSERT_INTO"])


def sc_update_simple(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 0 - status update driven by parameters only."""

    flow = fctx.flow
    tbl = S.CATALOG[flow.target]
    sets: list[tuple[str, Expr]] = []
    stat = next((c.name for c in tbl.columns if c.name.endswith("STAT_CD")), None)
    if stat:
        sets.append((stat, e_lit("'90'")))
    dtm = next((c.name for c in tbl.columns if c.name.endswith("_DTM")), None)
    if dtm:
        sets.append((dtm, e_lit("SYSDATE")))
    if not sets:
        # last resort: keep the assigned literal compatible with the column type
        col = tbl.columns[-1]
        sets.append((col.name,
                     e_lit("0" if col.dtype.startswith("NUMBER") else "'90'")))
    key = tbl.pk[0]
    where = [Expr("{0} = p_" + key.lower(), (ColRef(flow.target, key, "t"),))]
    g.budget.take("UPDATE_SET")
    return Built(
        stmts=[Update(target=flow.target, alias="t", sets=sets, where=where,
                      comment="상태 코드 갱신")],
        params=[Param(f"p_{key.lower()}", "IN", f"{flow.target}.{key}%TYPE")],
        constructs=["UPDATE_SET"],
    )


def sc_delete(g: Gen, fctx: FlowCtx) -> Built:
    flow = fctx.flow
    tbl = S.CATALOG[flow.target]
    date_col = next((c.name for c in tbl.columns if c.name.endswith("_YMD")), tbl.pk[0])
    where = [Expr("{0} < p_base_ymd", (ColRef(flow.target, date_col, "t"),))]
    stat = next((c.name for c in tbl.columns if c.name.endswith("STAT_CD")), None)
    if stat:
        where.append(Expr("{0} = '99'", (ColRef(flow.target, stat, "t"),)))
    g.budget.take("DELETE_FROM")
    return Built(stmts=[Delete(target=flow.target, alias="t", where=where,
                               comment="보존기간 경과 데이터 삭제")],
                 params=[Param("p_base_ymd", "IN", "VARCHAR2")],
                 constructs=["DELETE_FROM"])


def sc_insert_join(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 1 - multi-table join, and the corpus's shared construct carrier.

    One INSERT statement can legitimately hold a CTE, a GROUP BY rollup, an
    analytic function and a legacy outer join at the same time, and real code
    does exactly that. Giving each construct its own dedicated statement instead
    would need far more INSERTs than the measured rate (1.52 per 1K lines)
    allows, so this scenario opportunistically absorbs whichever constructs are
    still behind their quota.
    """

    flow = fctx.flow
    old_style = (bool(flow.joins) and g.budget.want("OLD_OUTER_JOIN")
                 and g.rng.random() < 0.5)
    sel = build_from(g, fctx, old_style=old_style)

    cols = list(flow.mapping)
    use_group = g.budget.want("GROUP_BY") and g.rng.random() < 0.6
    # an analytic function over a grouped projection would need a second level,
    # so the two are mutually exclusive within one statement
    use_analytic = (not use_group and g.budget.want("ANALYTIC_OVER")
                    and g.rng.random() < 0.6)

    group_refs: list[ColRef] = []
    has_aggregate = False
    constructs = ["INSERT_INTO"]

    for c in cols:
        ref = fctx.parse(flow.mapping[c])
        if ref is not None and c in flow.quantity_columns:
            if use_group:
                sel.items.append((c, _aggregate(g, fctx, ref, is_numeric(flow, c))))
                has_aggregate = True
                continue
            if use_analytic:
                sel.items.append((c, _analytic(g, fctx, ref, is_numeric(flow, c))))
                continue
        expr = build_value(g, fctx, c, flow.mapping[c], tier=1)
        sel.items.append((c, expr))
        if isinstance(expr.refs[0] if expr.refs else None, ColRef):
            group_refs.append(expr.refs[0])

    if has_aggregate and group_refs:
        sel.group_by = group_refs
        g.budget.take("GROUP_BY")
        constructs.append("GROUP_BY")
    if use_analytic:
        constructs.append("ANALYTIC_OVER")
    if old_style:
        constructs.append("OLD_OUTER_JOIN")

    outer = sel
    if g.budget.want("WITH_CTE") and g.rng.random() < 0.5:
        outer = Select(tables=[TableRef(table="w_src", alias="w")],
                       ctes=[("w_src", sel)])
        for c in cols:
            outer.items.append((c, e_col(ColRef("w_src", c, "w"))))
        g.budget.take("WITH_CTE")
        constructs.append("WITH_CTE")

    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(target=flow.target, columns=cols,
                                     select=outer, comment=f"{flow.name} 조인 적재")],
                 constructs=constructs)


def sc_update_correlated(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 1 - UPDATE ... SET col = (correlated aggregate subquery)."""

    flow = fctx.flow
    tbl = S.CATALOG[flow.target]
    qty_cols = [c for c in flow.quantity_columns if tbl.has(c)]
    if not qty_cols:
        return sc_update_simple(g, fctx)
    src_alias = flow.base[1]
    src_table = fctx.table_of(src_alias)
    src = S.CATALOG[flow.base[0]]
    join_cols = [c for c in tbl.pk if src.has(c)][:2]
    sets: list[tuple[str, Expr]] = []
    for col in qty_cols[:2]:
        spec = flow.mapping.get(col, "")
        ref = fctx.parse(spec)
        if ref is None or ref.alias != src_alias:
            ref = ColRef(src_table, next(c.name for c in src.columns
                                         if c.dtype.startswith("NUMBER")), src_alias)
        inner = Select(
            items=[("SUM_QTY", Expr("SUM(NVL({0}, 0))", (ref,), AGGREGATE))],
            tables=[TableRef(table=src_table, alias=src_alias)],
            where=[cond("{0} = {1}", ColRef(src_table, jc, src_alias),
                        ColRef(flow.target, jc, "t")) for jc in join_cols],
        )
        sq = ScalarSubquery(inner)
        sets.append((col, Expr("NVL({0}, 0)", (sq,), TRANSFORM,
                               tuple(ColRef(src_table, jc, src_alias) for jc in join_cols))))
    if tbl.has("UPD_DTM"):
        sets.append(("UPD_DTM", e_lit("SYSDATE")))
    where = [Expr("{0} = p_wh_cd", (ColRef(flow.target, "WH_CD", "t"),))] if tbl.has("WH_CD") else []
    g.budget.take("UPDATE_SET")
    return Built(stmts=[Update(target=flow.target, alias="t", sets=sets, where=where,
                               comment="원천 집계값으로 수량 재계산")],
                 params=[Param("p_wh_cd", "IN", "SYNWMS.MST_WHOUSE.WH_CD%TYPE")] if where else [],
                 constructs=["UPDATE_SET"])


def sc_merge(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - MERGE producing both UPDATE and INSERT edges."""

    flow = fctx.flow
    using = build_from(g, fctx)
    cols = list(flow.mapping)
    for c in cols:
        using.items.append((c, build_value(g, fctx, c, flow.mapping[c], tier=2)))
    key_cols = [c for c in flow.key_columns if S.CATALOG[flow.target].has(c)] or [cols[0]]
    on = [cond("{0} = {1}", ColRef(flow.target, k, "t"), ColRef("q", k, "q")) for k in key_cols]
    upd = [(c, e_col(ColRef("q", c, "q"))) for c in cols if c not in key_cols][:6]
    ins_vals = [e_col(ColRef("q", c, "q")) for c in cols]
    g.budget.take("MERGE_INTO")
    return Built(stmts=[Merge(target=flow.target, alias="t", using=using, using_alias="q",
                              on=on, update_sets=upd, insert_columns=cols,
                              insert_values=ins_vals,
                              comment=f"{flow.name} UPSERT")],
                 constructs=["MERGE_INTO"])


def sc_cte_aggregate(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - WITH clause, aggregation, transitive lineage through the CTE."""

    flow = fctx.flow
    inner = build_from(g, fctx)
    cte_cols = list(flow.mapping)
    group_refs: list[ColRef] = []
    for c in cte_cols:
        expr = build_value(g, fctx, c, flow.mapping[c], tier=2,
                           allow_aggregate=c in flow.quantity_columns)
        inner.items.append((c, expr))
        if expr.kind != AGGREGATE and expr.refs:
            first = expr.refs[0]
            if isinstance(first, ColRef):
                group_refs.append(first)
    if any(e.kind == AGGREGATE for _, e in inner.items):
        inner.group_by = group_refs
        g.budget.take("GROUP_BY")
    outer = Select(tables=[TableRef(table="w_src", alias="w")])
    for c in cte_cols:
        outer.items.append((c, e_col(ColRef("w_src", c, "w"))))
    outer.ctes = [("w_src", inner)]
    g.budget.take("WITH_CTE")
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(target=flow.target, columns=cte_cols, select=outer,
                                     comment="CTE 경유 집계 적재")],
                 constructs=["WITH_CTE", "INSERT_INTO"])


def sc_aggregate_rollup(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - GROUP BY rollup with the aggregates in the outer projection.

    Aggregates nested inside a CTE come back out as VIA_CTE, so without a
    scenario that aggregates at the top level the AGGREGATE edge kind would be
    declared but never produced.
    """

    flow = fctx.flow
    sel = build_from(g, fctx)
    cols = list(flow.mapping)
    group_refs: list[ColRef] = []
    has_aggregate = False
    for c in cols:
        if c in flow.quantity_columns:
            ref = fctx.parse(flow.mapping[c])
            if ref is not None:
                sel.items.append((c, _aggregate(g, fctx, ref, is_numeric(flow, c))))
                has_aggregate = True
                continue
        expr = build_value(g, fctx, c, flow.mapping[c], tier=1)
        sel.items.append((c, expr))
        for r in expr.refs:
            if isinstance(r, ColRef):
                group_refs.append(r)
    if not has_aggregate:
        return sc_insert_join(g, fctx)
    sel.group_by = group_refs
    g.budget.take("GROUP_BY")
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(target=flow.target, columns=cols, select=sel,
                                     comment=f"{flow.name} 그룹 집계 적재")],
                 constructs=["GROUP_BY", "INSERT_INTO"])


def sc_analytic(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - analytic function; PARTITION BY / ORDER BY columns are ANALYTIC edges."""

    flow = fctx.flow
    sel = build_from(g, fctx)
    cols = list(flow.mapping)
    rank_col = next((c for c in cols if c.endswith(("_NO", "_CNT"))), None)
    for c in cols:
        if c == rank_col:
            part = fctx.parse(flow.mapping.get("WH_CD", "")) or fctx.code_ref()
            order = fctx.qty_ref()
            if part is not None and order is not None:
                g.budget.take("ANALYTIC_OVER")
                sel.items.append((c, Expr(
                    "ROW_NUMBER() OVER (PARTITION BY {0} ORDER BY {1} DESC)",
                    (part, order), ANALYTIC)))
                continue
        expr = build_value(g, fctx, c, flow.mapping[c], tier=2)
        if c in flow.quantity_columns and g.budget.want("ANALYTIC_OVER") and g.rng.random() < 0.5:
            ref = fctx.parse(flow.mapping[c])
            if ref is not None:
                expr = _analytic(g, fctx, ref, True)
        sel.items.append((c, expr))
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(target=flow.target, columns=cols, select=sel,
                                     comment="분석함수 기반 순위/누계 산출")],
                 constructs=["ANALYTIC_OVER", "INSERT_INTO"])


def sc_select_star(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - ``SELECT s.*`` into a column-identical mirror table.

    Only resolvable with the DDL catalog: without it the engine cannot know
    which target column each projected column lands in.
    """

    src = "SYNWMS.STK_ONHAND"
    tgt = "SYNARC.ARC_STK_ONHAND"
    sel = Select(
        items=[(None, Expr("{0}", (Star(src, "s"),), DIRECT))],
        tables=[TableRef(table=src, alias="s")],
        where=[cond("{0} > 0", ColRef(src, "ONHAND_QTY", "s"))],
    )
    g.budget.take("SELECT_STAR")
    g.budget.take("INSERT_INTO")
    stmts: list[Stmt] = [InsertSelect(target=tgt, columns=None, select=sel,
                                      comment="재고 스냅샷 전량 아카이브 (컬럼 전개 필요)")]

    # inline view with SELECT * feeding an explicit projection
    iv = Select(
        items=[(None, Expr("{0}", (Star("SYNWMS.STK_TRX", "x"),), DIRECT))],
        tables=[TableRef(table="SYNWMS.STK_TRX", alias="x")],
        where=[cond("{0} = p_base_ymd", ColRef("SYNWMS.STK_TRX", "TRX_YMD", "x"))],
    )
    outer = Select(tables=[TableRef(subquery=iv, alias="v")])
    for tgt_col, src_col in (("ARC_SEQ", None), ("TRX_SEQ", "TRX_SEQ"), ("WH_CD", "WH_CD"),
                             ("ITEM_CD", "ITEM_CD"), ("TRX_TP_CD", "TRX_TP_CD"),
                             ("TRX_QTY", "TRX_QTY"), ("TRX_YMD", "TRX_YMD"), ("ARC_DTM", None)):
        if src_col is None:
            outer.items.append((tgt_col, e_lit("SEQ_ARC.NEXTVAL" if tgt_col == "ARC_SEQ" else "SYSDATE")))
        else:
            outer.items.append((tgt_col, e_col(ColRef("v", src_col, "v"))))
    g.budget.take("SELECT_STAR")
    g.budget.take("INSERT_INTO")
    stmts.append(InsertSelect(
        target="SYNARC.ARC_STK_TRX",
        columns=["ARC_SEQ", "TRX_SEQ", "WH_CD", "ITEM_CD", "TRX_TP_CD", "TRX_QTY", "TRX_YMD", "ARC_DTM"],
        select=outer, comment="인라인 뷰 SELECT * 경유 아카이브"))
    return Built(stmts=stmts, params=[Param("p_base_ymd", "IN", "VARCHAR2")],
                 constructs=["SELECT_STAR", "INSERT_INTO"])


def sc_old_outer_join(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - Oracle legacy ``(+)`` outer join syntax."""

    flow = fctx.flow
    if not flow.joins or not g.budget.want("OLD_OUTER_JOIN"):
        return sc_insert_join(g, fctx)
    sel = build_from(g, fctx, old_style=True)
    cols = list(flow.mapping)
    for c in cols:
        sel.items.append((c, build_value(g, fctx, c, flow.mapping[c], tier=2)))
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(target=flow.target, columns=cols, select=sel,
                                     comment="구식 (+) 외부조인 적재")],
                 constructs=["OLD_OUTER_JOIN", "INSERT_INTO"])


def sc_select_into_values(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - variable-mediated lineage: SELECT INTO then INSERT ... VALUES."""

    flow = fctx.flow
    src_table = fctx.table_of(flow.base[1])
    src = S.CATALOG[flow.base[0]]
    qty = next((c.name for c in src.columns if "QTY" in c.name), None)
    key = src.pk[0]
    if qty is None:
        return sc_insert_join(g, fctx)

    sel = Select(
        items=[("SUM_QTY", Expr("NVL(SUM({0}), 0)", (ColRef(src_table, qty, "s"),), AGGREGATE)),
               ("MAX_KEY", Expr("MAX({0})", (ColRef(src_table, key, "s"),), AGGREGATE))],
        tables=[TableRef(table=src_table, alias="s")],
        where=[cond("{0} = p_wh_cd", ColRef(src_table, "WH_CD", "s"))] if src.has("WH_CD") else [],
    )
    into = SelectInto(targets=["v_sum_qty", "v_max_key"], select=sel,
                      comment="집계값을 변수로 수신")
    g.budget.take("SELECT_INTO")

    tbl = S.CATALOG[flow.target]
    tgt_qty = next((c for c in flow.quantity_columns if tbl.has(c)), None)
    columns: list[str] = []
    values: list[Expr] = []
    for c in list(flow.key_columns) or [tbl.pk[0]]:
        columns.append(c)
        values.append(e_lit("SEQ_ARC.NEXTVAL" if c.endswith("_SEQ") else "p_wh_cd"))
    if tgt_qty:
        columns.append(tgt_qty)
        values.append(Expr("NVL({0}, 0)", (Var("v_sum_qty"),), TRANSFORM))
    ins = InsertValues(target=flow.target, columns=columns, values=values,
                       comment="변수 경유 적재 (VIA_VARIABLE)")
    g.budget.take("INSERT_INTO")
    return Built(stmts=[into, ins],
                 decls=["v_sum_qty              NUMBER(15,3);",
                        f"v_max_key              {src.fq}.{key}%TYPE;"],
                 params=[Param("p_wh_cd", "IN", "SYNWMS.MST_WHOUSE.WH_CD%TYPE")],
                 constructs=["SELECT_INTO", "INSERT_INTO"])


def sc_db_link(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 2 - lineage escaping through a database link."""

    linked = FlowCtx(fctx.flow, g.rng, link="ERPLINK")
    sel = build_from(g, linked)
    cols = list(linked.flow.mapping)
    for c in cols:
        sel.items.append((c, build_value(g, linked, c, linked.flow.mapping[c], tier=1)))
    g.budget.take("DB_LINK")
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(target=linked.flow.target, columns=cols, select=sel,
                                     comment="원격 스키마(DB LINK) 원천 적재")],
                 constructs=["DB_LINK", "INSERT_INTO"])


def _target_key_where(flow: S.Flow, var_prefix: str) -> list[Expr]:
    """WHERE predicates pinning a target row by its key columns."""

    tbl = S.CATALOG[flow.target]
    out = []
    for k in (flow.key_columns or tbl.pk)[:2]:
        if tbl.has(k):
            out.append(Expr("{0} = " + f"{var_prefix}{k}", (ColRef(flow.target, k, "t"),)))
    return out


def sc_cursor_loop(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 3 - declared cursor + FOR loop.

    Two variants. The row-by-row INSERT is the obvious one; the accumulate
    variant (loop into a variable, then a single UPDATE) is both more common in
    legacy code and a better test, because the lineage only closes if the engine
    follows the value through the loop variable and out again.
    """

    flow = fctx.flow
    sel = build_from(g, fctx)
    cols = list(flow.mapping)
    for c in cols:
        sel.items.append((c, build_value(g, fctx, c, flow.mapping[c], tier=1)))
    cursor_name = f"c_{flow.name.lower()}"
    g.budget.take("CURSOR_DECL")

    qty_cols = [c for c in flow.quantity_columns if S.CATALOG[flow.target].has(c)]
    accumulate = bool(qty_cols) and g.rng.random() < 0.55
    extra_decls: list[str] = []
    constructs = ["CURSOR_DECL"]

    if accumulate:
        qty = qty_cols[0]
        body: list[Stmt] = [
            Assign("v_acc_qty",
                   Expr("NVL({0}, 0) + NVL({1}, 0)", (Var("v_acc_qty"), Var(f"rec.{qty}")),
                        TRANSFORM),
                   accumulate=True),
            Raw(lines=["v_cnt := v_cnt + 1;"]),
        ]
        after: list[Stmt] = [Update(
            target=flow.target, alias="t",
            sets=[(qty, Expr("NVL({0}, 0)", (Var("v_acc_qty"),), TRANSFORM))],
            where=_target_key_where(flow, "p_"),
            comment="루프 누계를 단일 UPDATE로 반영")]
        g.budget.take("UPDATE_SET")
        constructs.append("UPDATE_SET")
        extra_decls.append(f"{'v_acc_qty':<22} NUMBER(15,3) := 0;")
        params = [Param(f"p_{k}", "IN", f"{flow.target}.{k}%TYPE")
                  for k in (flow.key_columns or S.CATALOG[flow.target].pk)[:2]
                  if S.CATALOG[flow.target].has(k)]
    else:
        body_cols = cols[:8]
        body = [
            InsertValues(target=flow.target, columns=body_cols,
                         values=[Expr("{0}", (Var(f"rec.{c}"),), DIRECT) for c in body_cols],
                         comment="커서 레코드 기반 적재"),
            Raw(lines=["v_cnt := v_cnt + 1;"]),
        ]
        after = []
        g.budget.take("INSERT_INTO")
        constructs.append("INSERT_INTO")
        params = []

    loop = CursorLoop(record="rec", select=sel, cursor_name=cursor_name,
                      body=body, comment="커서 루프 처리")

    from .core import render_select as _rs
    blk = _rs(sel)
    body_lines = [f"  {line}" for line in blk.lines]
    body_lines[-1] += ";"
    decl_lines = [f"CURSOR {cursor_name} IS"] + body_lines
    return Built(stmts=[loop] + after, decls=decl_lines + extra_decls,
                 params=params, constructs=constructs)


def sc_bulk_collect(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 3 - BULK COLLECT into a collection, then a bulk apply."""

    flow = fctx.flow
    sel = build_from(g, fctx)
    cols = list(flow.mapping)[:8]
    for c in cols:
        sel.items.append((c, build_value(g, fctx, c, flow.mapping[c], tier=1)))
    bulk = SelectInto(targets=["t_rows"], select=sel, bulk=True,
                      comment="대량 조회 (BULK COLLECT)")
    g.budget.take("BULK_COLLECT")
    constructs = ["BULK_COLLECT"]

    qty_cols = [c for c in flow.quantity_columns if S.CATALOG[flow.target].has(c)]
    if qty_cols and g.rng.random() < 0.45:
        apply_stmt: Stmt = Update(
            target=flow.target, alias="t",
            sets=[(qty_cols[0], Expr("{0}", (Var(f"t_rows(i).{qty_cols[0]}"),), DIRECT))],
            where=[Expr("{0} = " + f"t_rows(i).{k}", (ColRef(flow.target, k, "t"),))
                   for k in (flow.key_columns or S.CATALOG[flow.target].pk)[:2]
                   if S.CATALOG[flow.target].has(k)],
            comment="컬렉션 원소 기준 일괄 갱신")
        g.budget.take("UPDATE_SET")
        constructs.append("UPDATE_SET")
    else:
        apply_stmt = InsertValues(
            target=flow.target, columns=cols,
            values=[Expr("{0}", (Var(f"t_rows(i).{c}"),), DIRECT) for c in cols],
            comment="컬렉션 원소 일괄 적재")
        g.budget.take("INSERT_INTO")
        constructs.append("INSERT_INTO")

    # FORALL is vanishingly rare in the measured asset (2 occurrences), so the
    # plain numeric FOR loop is the default carrier.
    if g.budget.want("FORALL"):
        g.budget.take("FORALL")
        loop: Stmt = ForAll(collection="t_rows", index="i", body=apply_stmt)
        constructs.append("FORALL")
    else:
        loop = ForLoop(index="i", bound="t_rows.COUNT", body=[apply_stmt])

    rec_fields = ",\n      ".join(
        f"{c:<16} {S.CATALOG[flow.target].column(c).dtype}" for c in cols)
    decls = [
        "TYPE t_row_rec IS RECORD (",
        f"      {rec_fields}",
        "    );",
        "TYPE t_row_tab IS TABLE OF t_row_rec INDEX BY PLS_INTEGER;",
        "t_rows                 t_row_tab;",
    ]
    # The BULK COLLECT statement binds t_rows(i).COLUMN; the apply statement
    # then resolves through those bindings (VIA_VARIABLE edges).
    return Built(stmts=[bulk, loop], decls=decls, constructs=constructs)


def sc_ref_cursor(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 3 - result set handed to the caller through SYS_REFCURSOR."""

    flow = fctx.flow
    sel = build_from(g, fctx)
    for c in list(flow.mapping)[:8]:
        sel.items.append((c, build_value(g, fctx, c, flow.mapping[c], tier=1)))
    # the SYS_REFCURSOR parameter is rendered twice: package spec and body
    # A distinct parameter name per flow: two ref-cursor scenarios landing in
    # one subprogram must not collapse into a single OUT parameter, or the
    # emitted count and the measured count drift apart.
    out_param = f"o_{flow.name.lower()}_cur"
    g.budget.take("REF_CURSOR", 2)
    return Built(stmts=[OpenRefCursor(out_param=out_param, select=sel,
                                      comment="호출자에게 결과셋 반환")],
                 params=[Param(out_param, "OUT", "SYS_REFCURSOR")],
                 constructs=["REF_CURSOR"])


def sc_connect_by(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 3 - hierarchical self-referencing query over the code master."""

    src = "SYNWMS.MST_CODE"
    sel = Select(
        items=[
            ("GRP_CD", e_col(ColRef(src, "GRP_CD", "c"))),
            ("CD", e_col(ColRef(src, "CD", "c"))),
            ("CD_NM", Expr("LPAD(' ', (LEVEL - 1) * 2) || {0}", (ColRef(src, "CD_NM", "c"),), TRANSFORM)),
            ("UP_CD", e_col(ColRef(src, "UP_CD", "c"))),
            ("SORT_NO", Expr("LEVEL", (), TRANSFORM)),
            ("USE_YN", e_col(ColRef(src, "USE_YN", "c"))),
        ],
        tables=[TableRef(table=src, alias="c")],
        where=[cond("{0} = 'Y'", ColRef(src, "USE_YN", "c"))],
        start_with=[cond("{0} IS NULL", ColRef(src, "UP_CD", "c"))],
        connect_by=[cond("PRIOR {0} = {1}", ColRef(src, "CD", "c"), ColRef(src, "UP_CD", "c"))],
    )
    g.budget.take("CONNECT_BY")
    if g.budget.want("REF_CURSOR") and g.rng.random() < 0.5:
        # hand the expanded hierarchy back to the caller instead of re-loading it
        g.budget.take("REF_CURSOR", 2)
        return Built(stmts=[OpenRefCursor(out_param="o_code_tree_cur", select=sel,
                                          comment="계층 전개 결과셋 반환")],
                     params=[Param("o_code_tree_cur", "OUT", "SYS_REFCURSOR")],
                     constructs=["CONNECT_BY", "REF_CURSOR"])
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(
        target="SYNWMS.MST_CODE", columns=["GRP_CD", "CD", "CD_NM", "UP_CD", "SORT_NO", "USE_YN"],
        select=sel, comment="계층 코드 전개 후 재적재")],
        constructs=["CONNECT_BY", "INSERT_INTO"])


def sc_dynamic_sql(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 3 - EXECUTE IMMEDIATE against a table name held in a variable."""

    flow = fctx.flow
    variant = g.rng.randrange(3)
    if variant == 0:
        lines = [
            "v_tab_nm := 'SYNWMS.' || p_tab_sfx;",
            "v_sql := 'UPDATE ' || v_tab_nm",
            "      || '   SET UPD_DTM = SYSDATE'",
            "      || ' WHERE WH_CD = :1'",
            "      || '   AND LAST_TRX_YMD < :2';",
        ]
        using = ["p_wh_cd", "p_base_ymd"]
    elif variant == 1:
        lines = [
            "v_tab_nm := 'SYNWMS.' || p_tab_sfx || '_' || SUBSTR(p_base_ymd, 1, 6);",
            "v_sql := 'BEGIN ' || v_tab_nm || '.SP_RUN(:1); END;';",
        ]
        using = ["p_wh_cd"]
    else:
        # Keep the constructed statement free of INSERT/SELECT * keywords: the
        # profile counter is textual, and a keyword inside a dynamic string
        # would be scored as a static occurrence of that construct.
        lines = [
            "v_tab_nm := 'SYNWMS.' || p_tab_sfx;",
            "v_sql := 'TRUNCATE TABLE ' || v_tab_nm || '_BAK';",
        ]
        using = []
    g.budget.take("EXEC_IMMEDIATE")
    return Built(
        stmts=[ExecImmediate(assign_lines=lines, target_hint=flow.target,
                             using=using,
                             comment="객체명이 런타임에 결정됨 - 정적 해석 불가")],
        decls=["v_tab_nm               VARCHAR2(61);"],
        params=[Param("p_tab_sfx", "IN", "VARCHAR2"),
                Param("p_wh_cd", "IN", "SYNWMS.MST_WHOUSE.WH_CD%TYPE"),
                Param("p_base_ymd", "IN", "VARCHAR2")],
        constructs=["EXEC_IMMEDIATE"],
    )


def sc_pivot(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 3 - PIVOT: rows become columns, the hardest shape for a parser."""

    src = "SYNWMS.STK_TRX"
    inner = Select(
        items=[
            ("BASE_YM", Expr("SUBSTR({0}, 1, 6)", (ColRef(src, "TRX_YMD", "t"),), TRANSFORM)),
            ("WH_CD", e_col(ColRef(src, "WH_CD", "t"))),
            ("ITEM_GRP_CD", e_col(ColRef("SYNWMS.MST_ITEM", "ITEM_GRP_CD", "i"))),
            ("TRX_TP_CD", e_col(ColRef(src, "TRX_TP_CD", "t"))),
            ("TRX_QTY", e_col(ColRef(src, "TRX_QTY", "t"))),
        ],
        tables=[
            TableRef(table=src, alias="t"),
            TableRef(table="SYNWMS.MST_ITEM", alias="i", join="JOIN",
                     on=(cond("{0} = {1}", ColRef("SYNWMS.MST_ITEM", "ITEM_CD", "i"),
                              ColRef(src, "ITEM_CD", "t")),)),
        ],
    )
    pivot_clause = "PIVOT (SUM(TRX_QTY) FOR TRX_TP_CD IN ('10' AS IN_QTY, '20' AS OUT_QTY))"
    outer = Select(
        items=[
            ("BASE_YM", e_col(ColRef("p", "BASE_YM", "p"))),
            ("WH_CD", e_col(ColRef("p", "WH_CD", "p"))),
            ("ITEM_GRP_CD", e_col(ColRef("p", "ITEM_GRP_CD", "p"))),
            ("IN_QTY", Expr("NVL({0}, 0)", (ColRef("p", "TRX_QTY", "p"),), TRANSFORM)),
            ("OUT_QTY", Expr("NVL({0}, 0)", (ColRef("p", "TRX_QTY", "p"),), TRANSFORM)),
        ],
        tables=[TableRef(subquery=inner, alias="p", pivot=pivot_clause)],
    )
    g.budget.take("PIVOT")
    g.budget.take("INSERT_INTO")
    return Built(stmts=[InsertSelect(
        target="SYNWMS.RPT_MONTHLY_TRX",
        columns=["BASE_YM", "WH_CD", "ITEM_GRP_CD", "IN_QTY", "OUT_QTY"],
        select=outer, comment="이동유형 PIVOT 집계")],
        constructs=["PIVOT", "INSERT_INTO"])


def sc_autonomous_log(g: Gen, fctx: FlowCtx) -> Built:
    """Tier 3 - autonomous transaction boundary."""

    ins = InsertValues(
        target="SYNARC.ARC_JOB_LOG",
        columns=["LOG_SEQ", "JOB_ID", "JOB_NM", "STEP_NO", "PROC_CNT", "STA_DTM"],
        values=[e_lit("SYNWMS.SEQ_JOB_LOG.NEXTVAL"), e_lit("g_job_id"), e_lit("p_step_nm"),
                e_lit("g_step_no"), Expr("{0}", (Var("v_cnt"),), DIRECT), e_lit("SYSDATE")],
        comment="자율 트랜잭션 로그 기록",
    )
    g.budget.take("AUTONOMOUS_TX")
    g.budget.take("INSERT_INTO")
    return Built(stmts=[ins, Raw(lines=["COMMIT;"])],
                 params=[Param("p_step_nm", "IN", "VARCHAR2")],
                 autonomous=True, constructs=["AUTONOMOUS_TX", "INSERT_INTO"])


@dataclass(frozen=True)
class Scenario:
    name: str
    tier: int
    build: object
    quota: str
    costs: tuple[str, ...] = ()

    @property
    def all_costs(self) -> tuple[str, ...]:
        return (self.quota,) + self.costs


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("insert_simple", 0, sc_insert_simple, "INSERT_INTO"),
    Scenario("update_simple", 0, sc_update_simple, "UPDATE_SET"),
    Scenario("delete_retention", 1, sc_delete, "DELETE_FROM"),
    Scenario("insert_join", 1, sc_insert_join, "INSERT_INTO"),
    Scenario("update_correlated", 1, sc_update_correlated, "UPDATE_SET"),
    Scenario("merge_upsert", 2, sc_merge, "MERGE_INTO"),
    Scenario("cte_aggregate", 2, sc_cte_aggregate, "WITH_CTE", ("INSERT_INTO",)),
    Scenario("analytic_rank", 2, sc_analytic, "ANALYTIC_OVER", ("INSERT_INTO",)),
    Scenario("aggregate_rollup", 2, sc_aggregate_rollup, "GROUP_BY", ("INSERT_INTO",)),
    Scenario("select_star", 2, sc_select_star, "SELECT_STAR", ("INSERT_INTO",)),
    Scenario("old_outer_join", 2, sc_old_outer_join, "OLD_OUTER_JOIN", ("INSERT_INTO",)),
    Scenario("select_into_values", 2, sc_select_into_values, "SELECT_INTO", ("INSERT_INTO",)),
    Scenario("db_link", 2, sc_db_link, "DB_LINK", ("INSERT_INTO",)),
    Scenario("cursor_loop", 3, sc_cursor_loop, "CURSOR_DECL"),
    Scenario("bulk_collect", 3, sc_bulk_collect, "BULK_COLLECT"),
    Scenario("ref_cursor", 3, sc_ref_cursor, "REF_CURSOR"),
    Scenario("connect_by", 3, sc_connect_by, "CONNECT_BY"),
    Scenario("dynamic_sql", 3, sc_dynamic_sql, "EXEC_IMMEDIATE"),
    Scenario("pivot_report", 3, sc_pivot, "PIVOT", ("INSERT_INTO",)),
    Scenario("autonomous_log", 3, sc_autonomous_log, "AUTONOMOUS_TX", ("INSERT_INTO",)),
)

SCENARIO_BY_NAME = {s.name: s for s in SCENARIOS}


def pick_scenario(g: Gen, tier: int) -> Scenario | None:
    """Pick a scenario, or ``None`` for a purely procedural subprogram.

    The headline construct drives the weight; side-effect constructs (almost
    every scenario also emits an INSERT) only dampen it. A hard minimum across
    all constructs would starve scarce constructs such as PIVOT or analytic
    functions, because their carrier scenarios also spend the common INSERT
    quota. Returning ``None`` when everything is saturated is what stops the
    generator from over-emitting DML: real packages contain plenty of
    subprograms that are pure control flow.
    """

    pool = [s for s in SCENARIOS if s.tier <= tier]
    weights = []
    for s in pool:
        w = (1.0 if s.tier == tier else 0.22) * g.budget.pressure(s.quota)
        for c in s.costs:
            w *= 0.15 + 0.85 * g.budget.pressure(c)
        weights.append(w)
    if sum(weights) < 0.01:
        return None
    return g.rng.choices(pool, weights=weights, k=1)[0]


# --- subprogram / package assembly --------------------------------------------


def build_subprogram(g: Gen, tier: int, index: int, line_budget: int,
                     used_names: set[str]) -> tuple[Subprogram, list[str]]:
    flow = g.rng.choice(S.FLOWS)
    fctx = FlowCtx(flow, g.rng)
    scenario = pick_scenario(g, tier)
    built: Built = scenario.build(g, fctx) if scenario is not None else Built()

    extra = []
    # A longer subprogram carries more statements, both in real code and here.
    # Scaling the attempt count with the line budget is also what lets Tier 3
    # reach the corpus-wide rate of its constructs from inside the 10% of lines
    # Tier 3 packages occupy - the extra attempts simply return None once a
    # quota is spent, so this cannot inflate the DML rates.
    # Tier 3 packages hold only ~10% of the corpus lines but must supply the
    # whole corpus-wide quota of the hard constructs, so they attempt many more
    # scenarios per subprogram. Attempts past a spent quota return None, so the
    # higher ceiling costs nothing in the other tiers' rates.
    rounds = (min(24, max(2, line_budget // 40)) if tier >= 3
              else min(6, max(1, line_budget // 120)))
    for _ in range(rounds):
        if line_budget <= 60:
            break
        second_ctx = FlowCtx(g.rng.choice(S.FLOWS), g.rng)
        second = pick_scenario(g, tier)
        if second is not None:
            extra_built: Built = second.build(g, second_ctx)  # type: ignore[operator]
            extra.append((second.name, extra_built))

    verb, verb_ko = g.rng.choice(VERBS)
    noun, noun_ko = g.rng.choice(NOUNS)
    domain, domain_ko = DOMAIN_BY_TARGET.get(flow.target, ("WMS", "업무"))
    has_out = any(p.mode != "IN" for p in built.params) or \
        any(q.mode != "IN" for _, b in extra for q in b.params)
    kind = "FUNCTION" if not has_out and g.rng.random() < 0.15 else "PROCEDURE"
    prefix = "FN" if kind == "FUNCTION" else "SP"
    name = f"{prefix}_{verb}_{domain}_{noun}"
    n = 1
    while name in used_names:
        n += 1
        name = f"{prefix}_{verb}_{domain}_{noun}_{n:02d}"
    used_names.add(name)

    params = list(built.params)
    decls = list(built.decls)
    stmts = list(built.stmts)
    scenario_names = [scenario.name] if scenario is not None else ["procedural_only"]
    autonomous = built.autonomous
    for sname, b in extra:
        scenario_names.append(sname)
        for p in b.params:
            if all(p.name != q.name for q in params):
                params.append(p)
        decls.extend(b.decls)
        stmts.extend(b.stmts)
        autonomous = autonomous or b.autonomous

    decls = decl_block(g, fctx, g.rng.randrange(3, 9)) + decls
    if kind == "FUNCTION":
        params = [p for p in params if p.mode == "IN"]
        return_type = "NUMBER"
    else:
        return_type = None
        if all(p.name != "p_proc_cnt" for p in params):
            params.append(Param("p_proc_cnt", "OUT", "NUMBER"))

    rendered = sum(len(_estimate(s)) for s in stmts)
    remaining = max(0, line_budget - rendered - len(decls) - 20)
    if remaining > 0:
        pos = g.rng.randrange(0, max(1, len(stmts)))
        stmts[pos:pos] = filler(g, fctx, remaining)
    if not stmts:
        stmts = filler(g, fctx, max(20, line_budget - len(decls) - 20))

    tail = ["COMMIT;"]
    if kind == "FUNCTION":
        tail.append("RETURN v_cnt;")
    else:
        tail.append("p_proc_cnt := v_cnt;")

    sub = Subprogram(
        name=name, kind=kind, params=params, return_type=return_type,
        decls=decls, stmts=stmts,
        comment=f"{domain_ko} {noun_ko} {verb_ko} 처리",
        autonomous=autonomous, tail=tail,
    )
    return sub, scenario_names


def _estimate(s: Stmt) -> list[str]:
    from .core import render_stmt
    return render_stmt(s).lines


def build_package(g: Gen, index: int, tier: int, target_lines: int) -> Package:
    domains = sorted({d for d, _ in DOMAIN_BY_TARGET.values()})
    domain = domains[index % len(domains)]
    name = f"PKG_{domain}_{index:03d}"
    pkg = Package(schema="SYNWMS", name=name, tier=tier,
                  comment=f"Tier {tier} 합성 패키지 - {domain} 영역 배치 처리")

    used: set[str] = set()
    produced = 40  # package header + spec + trailer overhead
    g.budget.note_lines(40)
    # Subprogram length is what fixes the procedures-per-package ratio: the
    # measured asset averages 3.05 procedures + 0.54 functions per package, so a
    # 1,500-line package needs ~420-line subprograms, not a dozen short ones.
    # Oversized packages grow by longer subprograms too, not only by more of
    # them, which is how the 38K-line outlier in the measured asset is shaped.
    mean_sub = max(150, min(1500, int(target_lines / 3.0)))
    while produced < target_lines and len(pkg.subprograms) < 120:
        remaining = target_lines - produced
        sub_budget = min(remaining, max(60, int(g.rng.gauss(mean_sub, mean_sub * 0.4))))
        sub, scenarios = build_subprogram(g, tier, len(pkg.subprograms), sub_budget, used)
        pkg.subprograms.append(sub)
        pkg.scenarios.extend(scenarios)
        grown = sum(len(_estimate(s)) for s in sub.stmts) + len(sub.decls) + 18
        produced += grown
        g.budget.note_lines(grown)
    return pkg


def sample_package_lines(rng: random.Random, profile: dict, count: int) -> list[int]:
    """Log-normal package sizes matching the measured mean and maximum."""

    scale = profile["scale"]
    mean = scale["avg_package_lines"]
    sigma = scale["package_lines_sigma"]
    mu = math.log(mean) - sigma * sigma / 2
    sizes = [max(120, int(rng.lognormvariate(mu, sigma))) for _ in range(count)]
    if count:
        sizes[rng.randrange(count)] = scale["max_package_lines"]
    total = sum(sizes)
    target = scale["lines"]
    if total:
        factor = target / total
        sizes = [max(120, int(s * factor)) for s in sizes]
    return sizes
