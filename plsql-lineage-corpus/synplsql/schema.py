"""Virtual schema for the synthetic corpus.

Three schemas reproduce the cross-schema reference structure of a legacy WMS:

    SYNIF   interface  - inbound/outbound staging tables
    SYNWMS  business   - master, inbound, stock, outbound, report
    SYNARC  archive    - history retention and job logs

Every identifier here is invented for this generator. Nothing is derived from
any real system: only the *shape* of the structure (composite primary keys,
column names repeated across tables, multi-hop table chains) is reproduced,
because that shape is what a column-level lineage parser actually has to cope
with.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str
    comment: str


@dataclass(frozen=True)
class Table:
    schema: str
    name: str
    comment: str
    columns: tuple[Column, ...]
    pk: tuple[str, ...]

    @property
    def fq(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    def has(self, column: str) -> bool:
        return any(c.name == column for c in self.columns)

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"{self.fq}.{name}")


def _t(schema: str, name: str, comment: str, pk: tuple[str, ...], *cols: tuple[str, str, str]) -> Table:
    return Table(
        schema=schema,
        name=name,
        comment=comment,
        columns=tuple(Column(n, d, c) for n, d, c in cols),
        pk=pk,
    )


# --- shared column vocabulary -------------------------------------------------
# The same column names deliberately appear in many tables. A lineage engine
# that resolves columns by bare name instead of by alias will silently produce
# wrong edges on this corpus, which is exactly what we want to detect.

_WH = ("WH_CD", "VARCHAR2(10)", "창고코드")
_ITEM = ("ITEM_CD", "VARCHAR2(30)", "품목코드")
_LOT = ("LOT_NO", "VARCHAR2(30)", "로트번호")
_LOC = ("LOC_CD", "VARCHAR2(20)", "로케이션코드")
_ORD = ("ORD_NO", "VARCHAR2(20)", "전표번호")
_LINE = ("LINE_NO", "NUMBER(5)", "전표라인번호")
_CUST = ("CUST_CD", "VARCHAR2(20)", "거래처코드")
_REGD = ("REG_DTM", "DATE", "등록일시")
_UPDD = ("UPD_DTM", "DATE", "수정일시")


TABLES: tuple[Table, ...] = (
    # --- SYNIF: interface ----------------------------------------------------
    _t("SYNIF", "IF_ITEM_RCV", "품목 기준정보 수신 인터페이스", ("IF_SEQ",),
       ("IF_SEQ", "NUMBER(12)", "인터페이스순번"),
       ("IF_YMD", "VARCHAR2(8)", "인터페이스일자"),
       _ITEM,
       ("ITEM_NM", "VARCHAR2(200)", "품목명"),
       ("ITEM_GRP_CD", "VARCHAR2(10)", "품목그룹코드"),
       ("UNIT_CD", "VARCHAR2(10)", "단위코드"),
       ("UNIT_WGT", "NUMBER(13,3)", "단위중량"),
       ("BOX_QTY", "NUMBER(10)", "박스입수량"),
       ("USE_YN", "VARCHAR2(1)", "사용여부"),
       ("SND_SYS_CD", "VARCHAR2(10)", "송신시스템코드"),
       ("IF_STAT_CD", "VARCHAR2(2)", "인터페이스상태코드"),
       ("RCV_DTM", "DATE", "수신일시")),
    _t("SYNIF", "IF_ORDER_RCV", "입고예정 수신 인터페이스", ("IF_SEQ",),
       ("IF_SEQ", "NUMBER(12)", "인터페이스순번"),
       ("IF_YMD", "VARCHAR2(8)", "인터페이스일자"),
       _WH, _ORD, _LINE, _ITEM,
       ("ORD_QTY", "NUMBER(13,3)", "예정수량"),
       ("DUE_YMD", "VARCHAR2(8)", "납기일자"),
       ("VEND_CD", "VARCHAR2(20)", "공급사코드"),
       ("IF_STAT_CD", "VARCHAR2(2)", "인터페이스상태코드"),
       ("RCV_DTM", "DATE", "수신일시")),
    _t("SYNIF", "IF_ORDER_SND", "출고실적 송신 인터페이스", ("IF_SEQ",),
       ("IF_SEQ", "NUMBER(12)", "인터페이스순번"),
       ("IF_YMD", "VARCHAR2(8)", "인터페이스일자"),
       _WH, _ORD, _LINE, _ITEM, _CUST,
       ("SHIP_QTY", "NUMBER(13,3)", "출고수량"),
       ("SHIP_WGT", "NUMBER(13,3)", "출고중량"),
       ("SHIP_YMD", "VARCHAR2(8)", "출고일자"),
       ("TRK_NO", "VARCHAR2(30)", "송장번호"),
       ("IF_STAT_CD", "VARCHAR2(2)", "인터페이스상태코드"),
       ("SND_DTM", "DATE", "송신일시")),
    _t("SYNIF", "IF_STOCK_SND", "재고현황 송신 인터페이스", ("IF_SEQ",),
       ("IF_SEQ", "NUMBER(12)", "인터페이스순번"),
       ("IF_YMD", "VARCHAR2(8)", "인터페이스일자"),
       _WH, _ITEM,
       ("ONHAND_QTY", "NUMBER(13,3)", "재고수량"),
       ("ALLOC_QTY", "NUMBER(13,3)", "할당수량"),
       ("AVAIL_QTY", "NUMBER(13,3)", "가용수량"),
       ("SND_DTM", "DATE", "송신일시")),

    # --- SYNWMS: master ------------------------------------------------------
    _t("SYNWMS", "MST_ITEM", "품목 기준정보", ("ITEM_CD",),
       _ITEM,
       ("ITEM_NM", "VARCHAR2(200)", "품목명"),
       ("ITEM_GRP_CD", "VARCHAR2(10)", "품목그룹코드"),
       ("UNIT_CD", "VARCHAR2(10)", "단위코드"),
       ("UNIT_WGT", "NUMBER(13,3)", "단위중량"),
       ("BOX_QTY", "NUMBER(10)", "박스입수량"),
       ("SAFE_STK_QTY", "NUMBER(13,3)", "안전재고수량"),
       ("USE_YN", "VARCHAR2(1)", "사용여부"),
       _REGD, _UPDD),
    _t("SYNWMS", "MST_WHOUSE", "창고 기준정보", ("WH_CD",),
       _WH,
       ("WH_NM", "VARCHAR2(100)", "창고명"),
       ("AREA_CD", "VARCHAR2(10)", "권역코드"),
       ("USE_YN", "VARCHAR2(1)", "사용여부")),
    _t("SYNWMS", "MST_LOC", "로케이션 기준정보", ("WH_CD", "LOC_CD"),
       _WH, _LOC,
       ("ZONE_CD", "VARCHAR2(10)", "존코드"),
       ("LOC_TP_CD", "VARCHAR2(10)", "로케이션유형코드"),
       ("MAX_QTY", "NUMBER(13,3)", "최대적재수량"),
       ("USE_YN", "VARCHAR2(1)", "사용여부")),
    _t("SYNWMS", "MST_VENDOR", "공급사 기준정보", ("VEND_CD",),
       ("VEND_CD", "VARCHAR2(20)", "공급사코드"),
       ("VEND_NM", "VARCHAR2(100)", "공급사명"),
       ("BIZ_NO", "VARCHAR2(20)", "사업자번호"),
       ("USE_YN", "VARCHAR2(1)", "사용여부")),
    _t("SYNWMS", "MST_CUST", "거래처 기준정보", ("CUST_CD",),
       _CUST,
       ("CUST_NM", "VARCHAR2(100)", "거래처명"),
       ("AREA_CD", "VARCHAR2(10)", "권역코드"),
       ("GRADE_CD", "VARCHAR2(2)", "등급코드"),
       ("USE_YN", "VARCHAR2(1)", "사용여부")),
    _t("SYNWMS", "MST_CODE", "공통코드", ("GRP_CD", "CD"),
       ("GRP_CD", "VARCHAR2(20)", "코드그룹"),
       ("CD", "VARCHAR2(20)", "코드"),
       ("CD_NM", "VARCHAR2(100)", "코드명"),
       ("UP_CD", "VARCHAR2(20)", "상위코드"),
       ("SORT_NO", "NUMBER(5)", "정렬순서"),
       ("USE_YN", "VARCHAR2(1)", "사용여부")),

    # --- SYNWMS: inbound -----------------------------------------------------
    _t("SYNWMS", "INB_ORDER_H", "입고예정 헤더", ("WH_CD", "ORD_NO"),
       _WH, _ORD,
       ("ORD_YMD", "VARCHAR2(8)", "전표일자"),
       ("VEND_CD", "VARCHAR2(20)", "공급사코드"),
       ("ORD_STAT_CD", "VARCHAR2(2)", "전표상태코드"),
       ("REG_ID", "VARCHAR2(30)", "등록자"),
       _REGD),
    _t("SYNWMS", "INB_ORDER_D", "입고예정 상세", ("WH_CD", "ORD_NO", "LINE_NO"),
       _WH, _ORD, _LINE, _ITEM,
       ("ORD_QTY", "NUMBER(13,3)", "예정수량"),
       ("DUE_YMD", "VARCHAR2(8)", "납기일자"),
       ("LINE_STAT_CD", "VARCHAR2(2)", "라인상태코드"),
       _UPDD),
    _t("SYNWMS", "INB_RESULT", "입고실적", ("WH_CD", "ORD_NO", "LINE_NO", "RCV_SEQ"),
       _WH, _ORD, _LINE,
       ("RCV_SEQ", "NUMBER(5)", "입고순번"),
       _ITEM, _LOC, _LOT,
       ("RCV_QTY", "NUMBER(13,3)", "입고수량"),
       ("RJT_QTY", "NUMBER(13,3)", "불량수량"),
       ("RCV_WGT", "NUMBER(13,3)", "입고중량"),
       ("RCV_YMD", "VARCHAR2(8)", "입고일자"),
       ("WORK_ID", "VARCHAR2(30)", "작업자")),

    # --- SYNWMS: stock -------------------------------------------------------
    _t("SYNWMS", "STK_ONHAND", "재고", ("WH_CD", "LOC_CD", "ITEM_CD", "LOT_NO"),
       _WH, _LOC, _ITEM, _LOT,
       ("ONHAND_QTY", "NUMBER(13,3)", "재고수량"),
       ("ALLOC_QTY", "NUMBER(13,3)", "할당수량"),
       ("AVAIL_QTY", "NUMBER(13,3)", "가용수량"),
       ("WGT_TOT", "NUMBER(13,3)", "총중량"),
       ("LAST_TRX_YMD", "VARCHAR2(8)", "최종거래일자"),
       _UPDD),
    _t("SYNWMS", "STK_TRX", "재고이동이력", ("TRX_SEQ",),
       ("TRX_SEQ", "NUMBER(12)", "이동순번"),
       _WH, _LOC, _ITEM, _LOT,
       ("TRX_TP_CD", "VARCHAR2(2)", "이동유형코드"),
       ("TRX_QTY", "NUMBER(13,3)", "이동수량"),
       ("BEF_QTY", "NUMBER(13,3)", "이동전수량"),
       ("AFT_QTY", "NUMBER(13,3)", "이동후수량"),
       ("TRX_WGT", "NUMBER(13,3)", "이동중량"),
       ("TRX_YMD", "VARCHAR2(8)", "이동일자"),
       ("REF_NO", "VARCHAR2(20)", "참조전표번호")),
    _t("SYNWMS", "STK_ADJUST", "재고조정", ("WH_CD", "ADJ_NO", "LINE_NO"),
       _WH,
       ("ADJ_NO", "VARCHAR2(20)", "조정전표번호"),
       _LINE, _ITEM, _LOC, _LOT,
       ("ADJ_QTY", "NUMBER(13,3)", "조정수량"),
       ("RSN_CD", "VARCHAR2(10)", "조정사유코드"),
       ("ADJ_YMD", "VARCHAR2(8)", "조정일자")),

    # --- SYNWMS: outbound ----------------------------------------------------
    _t("SYNWMS", "OUT_ORDER_H", "출고지시 헤더", ("WH_CD", "ORD_NO"),
       _WH, _ORD,
       ("ORD_YMD", "VARCHAR2(8)", "전표일자"),
       _CUST,
       ("ORD_STAT_CD", "VARCHAR2(2)", "전표상태코드"),
       ("DUE_YMD", "VARCHAR2(8)", "출고요청일자")),
    _t("SYNWMS", "OUT_ORDER_D", "출고지시 상세", ("WH_CD", "ORD_NO", "LINE_NO"),
       _WH, _ORD, _LINE, _ITEM,
       ("ORD_QTY", "NUMBER(13,3)", "지시수량"),
       ("LINE_STAT_CD", "VARCHAR2(2)", "라인상태코드")),
    _t("SYNWMS", "OUT_ALLOC", "출고할당", ("WH_CD", "ORD_NO", "LINE_NO", "ALLOC_SEQ"),
       _WH, _ORD, _LINE,
       ("ALLOC_SEQ", "NUMBER(5)", "할당순번"),
       _ITEM, _LOC, _LOT,
       ("ALLOC_QTY", "NUMBER(13,3)", "할당수량"),
       ("ALLOC_STAT_CD", "VARCHAR2(2)", "할당상태코드"),
       ("ALLOC_DTM", "DATE", "할당일시")),
    _t("SYNWMS", "OUT_PICK", "피킹실적", ("WH_CD", "ORD_NO", "LINE_NO", "ALLOC_SEQ", "PICK_SEQ"),
       _WH, _ORD, _LINE,
       ("ALLOC_SEQ", "NUMBER(5)", "할당순번"),
       ("PICK_SEQ", "NUMBER(5)", "피킹순번"),
       _ITEM, _LOC, _LOT,
       ("PICK_QTY", "NUMBER(13,3)", "피킹수량"),
       ("WORK_ID", "VARCHAR2(30)", "작업자"),
       ("PICK_DTM", "DATE", "피킹일시")),
    _t("SYNWMS", "OUT_SHIP", "출고확정", ("WH_CD", "ORD_NO", "SHIP_SEQ"),
       _WH, _ORD,
       ("SHIP_SEQ", "NUMBER(5)", "출고순번"),
       _LINE, _CUST, _ITEM,
       ("SHIP_QTY", "NUMBER(13,3)", "출고수량"),
       ("SHIP_WGT", "NUMBER(13,3)", "출고중량"),
       ("TRK_NO", "VARCHAR2(30)", "송장번호"),
       ("SHIP_YMD", "VARCHAR2(8)", "출고일자")),

    # --- SYNWMS: report ------------------------------------------------------
    _t("SYNWMS", "RPT_DAILY_STK", "일자별 재고집계", ("BASE_YMD", "WH_CD", "ITEM_CD"),
       ("BASE_YMD", "VARCHAR2(8)", "기준일자"),
       _WH, _ITEM,
       ("BGN_QTY", "NUMBER(15,3)", "기초수량"),
       ("IN_QTY", "NUMBER(15,3)", "입고수량"),
       ("OUT_QTY", "NUMBER(15,3)", "출고수량"),
       ("ADJ_QTY", "NUMBER(15,3)", "조정수량"),
       ("END_QTY", "NUMBER(15,3)", "기말수량"),
       ("END_WGT", "NUMBER(15,3)", "기말중량"),
       ("RNK_NO", "NUMBER(8)", "순위")),
    _t("SYNWMS", "RPT_MONTHLY_TRX", "월별 거래집계", ("BASE_YM", "WH_CD", "ITEM_GRP_CD"),
       ("BASE_YM", "VARCHAR2(6)", "기준월"),
       _WH,
       ("ITEM_GRP_CD", "VARCHAR2(10)", "품목그룹코드"),
       ("IN_QTY", "NUMBER(15,3)", "입고수량"),
       ("OUT_QTY", "NUMBER(15,3)", "출고수량"),
       ("TRX_CNT", "NUMBER(10)", "거래건수"),
       ("AVG_QTY", "NUMBER(15,3)", "평균수량")),

    # --- SYNARC: archive -----------------------------------------------------
    _t("SYNARC", "ARC_STK_TRX", "재고이동 아카이브", ("ARC_SEQ",),
       ("ARC_SEQ", "NUMBER(12)", "아카이브순번"),
       ("TRX_SEQ", "NUMBER(12)", "이동순번"),
       _WH, _ITEM,
       ("TRX_TP_CD", "VARCHAR2(2)", "이동유형코드"),
       ("TRX_QTY", "NUMBER(13,3)", "이동수량"),
       ("TRX_YMD", "VARCHAR2(8)", "이동일자"),
       ("ARC_DTM", "DATE", "아카이브일시")),
    # Column-identical mirror of SYNWMS.STK_ONHAND so that "INSERT ... SELECT s.*"
    # is a legal, positionally-mapped statement (SELECT * expansion test).
    _t("SYNARC", "ARC_STK_ONHAND", "재고 스냅샷 아카이브", ("WH_CD", "LOC_CD", "ITEM_CD", "LOT_NO"),
       _WH, _LOC, _ITEM, _LOT,
       ("ONHAND_QTY", "NUMBER(13,3)", "재고수량"),
       ("ALLOC_QTY", "NUMBER(13,3)", "할당수량"),
       ("AVAIL_QTY", "NUMBER(13,3)", "가용수량"),
       ("WGT_TOT", "NUMBER(13,3)", "총중량"),
       ("LAST_TRX_YMD", "VARCHAR2(8)", "최종거래일자"),
       _UPDD),
    _t("SYNARC", "ARC_OUT_SHIP", "출고확정 아카이브", ("ARC_SEQ",),
       ("ARC_SEQ", "NUMBER(12)", "아카이브순번"),
       _WH, _ORD,
       ("SHIP_SEQ", "NUMBER(5)", "출고순번"),
       _ITEM, _CUST,
       ("SHIP_QTY", "NUMBER(13,3)", "출고수량"),
       ("SHIP_YMD", "VARCHAR2(8)", "출고일자"),
       ("ARC_DTM", "DATE", "아카이브일시")),
    _t("SYNARC", "ARC_JOB_LOG", "배치 작업 로그", ("LOG_SEQ",),
       ("LOG_SEQ", "NUMBER(12)", "로그순번"),
       ("JOB_ID", "VARCHAR2(30)", "작업식별자"),
       ("JOB_NM", "VARCHAR2(100)", "작업명"),
       ("STEP_NO", "NUMBER(5)", "단계번호"),
       ("PROC_CNT", "NUMBER(10)", "처리건수"),
       ("ERR_MSG", "VARCHAR2(2000)", "오류메시지"),
       ("STA_DTM", "DATE", "시작일시"),
       ("END_DTM", "DATE", "종료일시")),
)


CATALOG: dict[str, Table] = {t.fq: t for t in TABLES}


def table(fq: str) -> Table:
    return CATALOG[fq]


# --- intended lineage flows ---------------------------------------------------


@dataclass(frozen=True)
class Join:
    """A joined source table. `on` holds ("left.COL", "right.COL") pairs."""

    fq: str
    alias: str
    on: tuple[tuple[str, str], ...]
    outer: bool = False


@dataclass(frozen=True)
class Flow:
    """One target table fed from one or more source tables.

    `mapping` maps a target column to either an "alias.COLUMN" source reference
    or a literal expression wrapped in Lit(...) form (a bare string starting
    with "'" or a digit is treated as a literal by the scenario builder).
    """

    name: str
    target: str
    base: tuple[str, str]
    mapping: dict[str, str]
    joins: tuple[Join, ...] = ()
    filters: tuple[tuple[str, str, str], ...] = ()
    key_columns: tuple[str, ...] = ()
    quantity_columns: tuple[str, ...] = ()
    tier_floor: int = 0

    @property
    def alias_map(self) -> dict[str, str]:
        m = {self.base[1]: self.base[0]}
        for j in self.joins:
            m[j.alias] = j.fq
        return m


FLOWS: tuple[Flow, ...] = (
    Flow(
        name="ITEM_MASTER_FROM_IF",
        target="SYNWMS.MST_ITEM",
        base=("SYNIF.IF_ITEM_RCV", "r"),
        mapping={
            "ITEM_CD": "r.ITEM_CD",
            "ITEM_NM": "r.ITEM_NM",
            "ITEM_GRP_CD": "r.ITEM_GRP_CD",
            "UNIT_CD": "r.UNIT_CD",
            "UNIT_WGT": "r.UNIT_WGT",
            "BOX_QTY": "r.BOX_QTY",
            "USE_YN": "r.USE_YN",
            "REG_DTM": "SYSDATE",
        },
        filters=(("r.IF_STAT_CD", "=", "'10'"), ("r.SND_SYS_CD", "=", "'ERP'")),
        key_columns=("ITEM_CD",),
        quantity_columns=("UNIT_WGT", "BOX_QTY"),
    ),
    Flow(
        name="INB_ORDER_FROM_IF",
        target="SYNWMS.INB_ORDER_D",
        base=("SYNIF.IF_ORDER_RCV", "r"),
        joins=(
            Join("SYNWMS.MST_ITEM", "i", (("i.ITEM_CD", "r.ITEM_CD"),), outer=True),
        ),
        mapping={
            "WH_CD": "r.WH_CD",
            "ORD_NO": "r.ORD_NO",
            "LINE_NO": "r.LINE_NO",
            "ITEM_CD": "i.ITEM_CD",
            "ORD_QTY": "r.ORD_QTY",
            "DUE_YMD": "r.DUE_YMD",
            "LINE_STAT_CD": "'10'",
            "UPD_DTM": "SYSDATE",
        },
        filters=(("r.IF_STAT_CD", "=", "'10'"),),
        key_columns=("WH_CD", "ORD_NO", "LINE_NO"),
        quantity_columns=("ORD_QTY",),
    ),
    Flow(
        name="INB_RESULT_FROM_ORDER",
        target="SYNWMS.INB_RESULT",
        base=("SYNWMS.INB_ORDER_D", "d"),
        joins=(
            Join("SYNWMS.INB_ORDER_H", "h", (("h.WH_CD", "d.WH_CD"), ("h.ORD_NO", "d.ORD_NO"))),
            Join("SYNWMS.MST_ITEM", "i", (("i.ITEM_CD", "d.ITEM_CD"),), outer=True),
        ),
        mapping={
            "WH_CD": "d.WH_CD",
            "ORD_NO": "d.ORD_NO",
            "LINE_NO": "d.LINE_NO",
            "RCV_SEQ": "1",
            "ITEM_CD": "d.ITEM_CD",
            "LOC_CD": "'RCV-DOCK'",
            "LOT_NO": "d.DUE_YMD",
            "RCV_QTY": "d.ORD_QTY",
            "RJT_QTY": "0",
            "RCV_WGT": "i.UNIT_WGT",
            "RCV_YMD": "h.ORD_YMD",
            "WORK_ID": "h.REG_ID",
        },
        filters=(("d.LINE_STAT_CD", "=", "'10'"), ("h.ORD_STAT_CD", "<>", "'99'")),
        key_columns=("WH_CD", "ORD_NO", "LINE_NO", "RCV_SEQ"),
        quantity_columns=("RCV_QTY", "RJT_QTY", "RCV_WGT"),
    ),
    Flow(
        name="STOCK_FROM_INB_RESULT",
        target="SYNWMS.STK_ONHAND",
        base=("SYNWMS.INB_RESULT", "r"),
        joins=(
            Join("SYNWMS.MST_ITEM", "i", (("i.ITEM_CD", "r.ITEM_CD"),)),
            Join("SYNWMS.MST_LOC", "l", (("l.WH_CD", "r.WH_CD"), ("l.LOC_CD", "r.LOC_CD")), outer=True),
        ),
        mapping={
            "WH_CD": "r.WH_CD",
            "LOC_CD": "r.LOC_CD",
            "ITEM_CD": "r.ITEM_CD",
            "LOT_NO": "r.LOT_NO",
            "ONHAND_QTY": "r.RCV_QTY",
            "ALLOC_QTY": "0",
            "AVAIL_QTY": "r.RCV_QTY",
            "WGT_TOT": "i.UNIT_WGT",
            "LAST_TRX_YMD": "r.RCV_YMD",
            "UPD_DTM": "SYSDATE",
        },
        filters=(("r.RCV_QTY", ">", "0"), ("i.USE_YN", "=", "'Y'")),
        key_columns=("WH_CD", "LOC_CD", "ITEM_CD", "LOT_NO"),
        quantity_columns=("ONHAND_QTY", "AVAIL_QTY", "WGT_TOT"),
    ),
    Flow(
        name="TRX_FROM_STOCK",
        target="SYNWMS.STK_TRX",
        base=("SYNWMS.STK_ONHAND", "s"),
        joins=(
            Join("SYNWMS.INB_RESULT", "r",
                 (("r.WH_CD", "s.WH_CD"), ("r.ITEM_CD", "s.ITEM_CD"), ("r.LOT_NO", "s.LOT_NO")), outer=True),
        ),
        mapping={
            "TRX_SEQ": "SEQ_STK_TRX.NEXTVAL",
            "WH_CD": "s.WH_CD",
            "LOC_CD": "s.LOC_CD",
            "ITEM_CD": "s.ITEM_CD",
            "LOT_NO": "s.LOT_NO",
            "TRX_TP_CD": "'10'",
            "TRX_QTY": "r.RCV_QTY",
            "BEF_QTY": "s.ONHAND_QTY",
            "AFT_QTY": "s.ONHAND_QTY",
            "TRX_WGT": "s.WGT_TOT",
            "TRX_YMD": "s.LAST_TRX_YMD",
            "REF_NO": "r.ORD_NO",
        },
        filters=(("s.ONHAND_QTY", ">", "0"),),
        key_columns=("TRX_SEQ",),
        quantity_columns=("TRX_QTY", "BEF_QTY", "AFT_QTY", "TRX_WGT"),
    ),
    Flow(
        name="ALLOC_FROM_OUT_ORDER",
        target="SYNWMS.OUT_ALLOC",
        base=("SYNWMS.OUT_ORDER_D", "d"),
        joins=(
            Join("SYNWMS.STK_ONHAND", "s",
                 (("s.WH_CD", "d.WH_CD"), ("s.ITEM_CD", "d.ITEM_CD"))),
            Join("SYNWMS.OUT_ORDER_H", "h", (("h.WH_CD", "d.WH_CD"), ("h.ORD_NO", "d.ORD_NO"))),
        ),
        mapping={
            "WH_CD": "d.WH_CD",
            "ORD_NO": "d.ORD_NO",
            "LINE_NO": "d.LINE_NO",
            "ALLOC_SEQ": "1",
            "ITEM_CD": "d.ITEM_CD",
            "LOC_CD": "s.LOC_CD",
            "LOT_NO": "s.LOT_NO",
            "ALLOC_QTY": "d.ORD_QTY",
            "ALLOC_STAT_CD": "'10'",
            "ALLOC_DTM": "SYSDATE",
        },
        filters=(("s.AVAIL_QTY", ">", "0"), ("d.LINE_STAT_CD", "=", "'10'")),
        key_columns=("WH_CD", "ORD_NO", "LINE_NO", "ALLOC_SEQ"),
        quantity_columns=("ALLOC_QTY",),
    ),
    Flow(
        name="PICK_FROM_ALLOC",
        target="SYNWMS.OUT_PICK",
        base=("SYNWMS.OUT_ALLOC", "a"),
        joins=(
            Join("SYNWMS.MST_LOC", "l", (("l.WH_CD", "a.WH_CD"), ("l.LOC_CD", "a.LOC_CD")), outer=True),
        ),
        mapping={
            "WH_CD": "a.WH_CD",
            "ORD_NO": "a.ORD_NO",
            "LINE_NO": "a.LINE_NO",
            "ALLOC_SEQ": "a.ALLOC_SEQ",
            "PICK_SEQ": "1",
            "ITEM_CD": "a.ITEM_CD",
            "LOC_CD": "a.LOC_CD",
            "LOT_NO": "a.LOT_NO",
            "PICK_QTY": "a.ALLOC_QTY",
            "WORK_ID": "'BATCH'",
            "PICK_DTM": "SYSDATE",
        },
        filters=(("a.ALLOC_STAT_CD", "=", "'10'"),),
        key_columns=("WH_CD", "ORD_NO", "LINE_NO", "ALLOC_SEQ", "PICK_SEQ"),
        quantity_columns=("PICK_QTY",),
    ),
    Flow(
        name="SHIP_FROM_PICK",
        target="SYNWMS.OUT_SHIP",
        base=("SYNWMS.OUT_PICK", "p"),
        joins=(
            Join("SYNWMS.OUT_ORDER_H", "h", (("h.WH_CD", "p.WH_CD"), ("h.ORD_NO", "p.ORD_NO"))),
            Join("SYNWMS.MST_ITEM", "i", (("i.ITEM_CD", "p.ITEM_CD"),), outer=True),
        ),
        mapping={
            "WH_CD": "p.WH_CD",
            "ORD_NO": "p.ORD_NO",
            "SHIP_SEQ": "p.PICK_SEQ",
            "LINE_NO": "p.LINE_NO",
            "CUST_CD": "h.CUST_CD",
            "ITEM_CD": "p.ITEM_CD",
            "SHIP_QTY": "p.PICK_QTY",
            "SHIP_WGT": "i.UNIT_WGT",
            "TRK_NO": "h.ORD_NO",
            "SHIP_YMD": "h.ORD_YMD",
        },
        filters=(("p.PICK_QTY", ">", "0"),),
        key_columns=("WH_CD", "ORD_NO", "SHIP_SEQ"),
        quantity_columns=("SHIP_QTY", "SHIP_WGT"),
    ),
    Flow(
        name="IF_SND_FROM_SHIP",
        target="SYNIF.IF_ORDER_SND",
        base=("SYNWMS.OUT_SHIP", "s"),
        joins=(
            Join("SYNWMS.MST_CUST", "c", (("c.CUST_CD", "s.CUST_CD"),), outer=True),
        ),
        mapping={
            "IF_SEQ": "SEQ_IF_SND.NEXTVAL",
            "IF_YMD": "s.SHIP_YMD",
            "WH_CD": "s.WH_CD",
            "ORD_NO": "s.ORD_NO",
            "LINE_NO": "s.LINE_NO",
            "ITEM_CD": "s.ITEM_CD",
            "CUST_CD": "c.CUST_CD",
            "SHIP_QTY": "s.SHIP_QTY",
            "SHIP_WGT": "s.SHIP_WGT",
            "SHIP_YMD": "s.SHIP_YMD",
            "TRK_NO": "s.TRK_NO",
            "IF_STAT_CD": "'10'",
            "SND_DTM": "SYSDATE",
        },
        filters=(("s.SHIP_QTY", ">", "0"),),
        key_columns=("IF_SEQ",),
        quantity_columns=("SHIP_QTY", "SHIP_WGT"),
    ),
    Flow(
        name="DAILY_STOCK_REPORT",
        target="SYNWMS.RPT_DAILY_STK",
        base=("SYNWMS.STK_TRX", "t"),
        joins=(
            Join("SYNWMS.STK_ONHAND", "s",
                 (("s.WH_CD", "t.WH_CD"), ("s.ITEM_CD", "t.ITEM_CD"), ("s.LOT_NO", "t.LOT_NO")), outer=True),
        ),
        mapping={
            "BASE_YMD": "t.TRX_YMD",
            "WH_CD": "t.WH_CD",
            "ITEM_CD": "t.ITEM_CD",
            "BGN_QTY": "t.BEF_QTY",
            "IN_QTY": "t.TRX_QTY",
            "OUT_QTY": "t.TRX_QTY",
            "ADJ_QTY": "0",
            "END_QTY": "t.AFT_QTY",
            "END_WGT": "s.WGT_TOT",
            "RNK_NO": "1",
        },
        filters=(("t.TRX_TP_CD", "IN", "('10', '20')"),),
        key_columns=("BASE_YMD", "WH_CD", "ITEM_CD"),
        quantity_columns=("BGN_QTY", "IN_QTY", "OUT_QTY", "END_QTY", "END_WGT"),
    ),
    Flow(
        name="MONTHLY_TRX_REPORT",
        target="SYNWMS.RPT_MONTHLY_TRX",
        base=("SYNWMS.STK_TRX", "t"),
        joins=(
            Join("SYNWMS.MST_ITEM", "i", (("i.ITEM_CD", "t.ITEM_CD"),)),
        ),
        mapping={
            "BASE_YM": "t.TRX_YMD",
            "WH_CD": "t.WH_CD",
            "ITEM_GRP_CD": "i.ITEM_GRP_CD",
            "IN_QTY": "t.TRX_QTY",
            "OUT_QTY": "t.TRX_QTY",
            "TRX_CNT": "t.TRX_SEQ",
            "AVG_QTY": "t.TRX_QTY",
        },
        filters=(("i.USE_YN", "=", "'Y'"),),
        key_columns=("BASE_YM", "WH_CD", "ITEM_GRP_CD"),
        quantity_columns=("IN_QTY", "OUT_QTY", "AVG_QTY"),
    ),
    Flow(
        name="STOCK_SND_FROM_STOCK",
        target="SYNIF.IF_STOCK_SND",
        base=("SYNWMS.STK_ONHAND", "s"),
        joins=(
            Join("SYNWMS.MST_WHOUSE", "w", (("w.WH_CD", "s.WH_CD"),), outer=True),
        ),
        mapping={
            "IF_SEQ": "SEQ_IF_SND.NEXTVAL",
            "IF_YMD": "s.LAST_TRX_YMD",
            "WH_CD": "s.WH_CD",
            "ITEM_CD": "s.ITEM_CD",
            "ONHAND_QTY": "s.ONHAND_QTY",
            "ALLOC_QTY": "s.ALLOC_QTY",
            "AVAIL_QTY": "s.AVAIL_QTY",
            "SND_DTM": "SYSDATE",
        },
        filters=(("w.USE_YN", "=", "'Y'"),),
        key_columns=("IF_SEQ",),
        quantity_columns=("ONHAND_QTY", "ALLOC_QTY", "AVAIL_QTY"),
    ),
    Flow(
        name="ARCHIVE_TRX",
        target="SYNARC.ARC_STK_TRX",
        base=("SYNWMS.STK_TRX", "t"),
        mapping={
            "ARC_SEQ": "SEQ_ARC.NEXTVAL",
            "TRX_SEQ": "t.TRX_SEQ",
            "WH_CD": "t.WH_CD",
            "ITEM_CD": "t.ITEM_CD",
            "TRX_TP_CD": "t.TRX_TP_CD",
            "TRX_QTY": "t.TRX_QTY",
            "TRX_YMD": "t.TRX_YMD",
            "ARC_DTM": "SYSDATE",
        },
        filters=(("t.TRX_YMD", "<", "TO_CHAR(SYSDATE - 365, 'YYYYMMDD')"),),
        key_columns=("ARC_SEQ",),
        quantity_columns=("TRX_QTY",),
    ),
    Flow(
        name="ARCHIVE_SHIP",
        target="SYNARC.ARC_OUT_SHIP",
        base=("SYNWMS.OUT_SHIP", "s"),
        joins=(
            Join("SYNWMS.MST_CUST", "c", (("c.CUST_CD", "s.CUST_CD"),), outer=True),
        ),
        mapping={
            "ARC_SEQ": "SEQ_ARC.NEXTVAL",
            "WH_CD": "s.WH_CD",
            "ORD_NO": "s.ORD_NO",
            "SHIP_SEQ": "s.SHIP_SEQ",
            "ITEM_CD": "s.ITEM_CD",
            "CUST_CD": "c.CUST_CD",
            "SHIP_QTY": "s.SHIP_QTY",
            "SHIP_YMD": "s.SHIP_YMD",
            "ARC_DTM": "SYSDATE",
        },
        filters=(("s.SHIP_YMD", "<", "TO_CHAR(SYSDATE - 180, 'YYYYMMDD')"),),
        key_columns=("ARC_SEQ",),
        quantity_columns=("SHIP_QTY",),
    ),
    Flow(
        name="STOCK_ADJUSTMENT",
        target="SYNWMS.STK_ONHAND",
        base=("SYNWMS.STK_ADJUST", "j"),
        joins=(
            Join("SYNWMS.MST_ITEM", "i", (("i.ITEM_CD", "j.ITEM_CD"),), outer=True),
        ),
        mapping={
            "WH_CD": "j.WH_CD",
            "LOC_CD": "j.LOC_CD",
            "ITEM_CD": "j.ITEM_CD",
            "LOT_NO": "j.LOT_NO",
            "ONHAND_QTY": "j.ADJ_QTY",
            "ALLOC_QTY": "0",
            "AVAIL_QTY": "j.ADJ_QTY",
            "WGT_TOT": "i.UNIT_WGT",
            "LAST_TRX_YMD": "j.ADJ_YMD",
            "UPD_DTM": "SYSDATE",
        },
        filters=(("j.RSN_CD", "<>", "'CANCEL'"),),
        key_columns=("WH_CD", "LOC_CD", "ITEM_CD", "LOT_NO"),
        quantity_columns=("ONHAND_QTY", "AVAIL_QTY"),
    ),
)


FLOW_BY_NAME: dict[str, Flow] = {f.name: f for f in FLOWS}


# Sequences referenced by the flows above; emitted into the DDL catalog so the
# generated corpus is self-consistent.
SEQUENCES: tuple[str, ...] = ("SEQ_STK_TRX", "SEQ_IF_SND", "SEQ_ARC", "SEQ_JOB_LOG")


def render_ddl() -> str:
    """Render the full DDL catalog: tables, primary keys, comments, sequences."""

    out: list[str] = []
    out.append("-- 합성 코퍼스 DDL 카탈로그")
    out.append("-- 이 파일은 생성기에 의해 자동 생성됩니다. 직접 수정하지 마십시오.")
    out.append("--")
    out.append("-- SELECT * / alias.* 전개와 컬럼 타입 앵커(%TYPE) 해석을 검증하려면")
    out.append("-- 리니지 엔진이 이 카탈로그를 함께 읽어야 합니다.")
    out.append("")

    for schema in ("SYNIF", "SYNWMS", "SYNARC"):
        out.append(f"-- ============================================================")
        out.append(f"-- SCHEMA {schema}")
        out.append(f"-- ============================================================")
        out.append("")
        for t in TABLES:
            if t.schema != schema:
                continue
            width = max(len(c.name) for c in t.columns) + 2
            out.append(f"CREATE TABLE {t.fq} (")
            body = []
            for c in t.columns:
                null = " NOT NULL" if c.name in t.pk else ""
                body.append(f"  {c.name.ljust(width)}{c.dtype}{null}")
            pk_name = f"PK_{t.name}"
            body.append(f"  CONSTRAINT {pk_name} PRIMARY KEY ({', '.join(t.pk)})")
            out.append(",\n".join(body))
            out.append(");")
            out.append("")
            out.append(f"COMMENT ON TABLE {t.fq} IS '{t.comment}';")
            for c in t.columns:
                out.append(f"COMMENT ON COLUMN {t.fq}.{c.name} IS '{c.comment}';")
            out.append("")

    out.append("-- ============================================================")
    out.append("-- SEQUENCES")
    out.append("-- ============================================================")
    out.append("")
    for s in SEQUENCES:
        out.append(f"CREATE SEQUENCE SYNWMS.{s} START WITH 1 INCREMENT BY 1 NOCACHE;")
    out.append("")
    return "\n".join(out)
