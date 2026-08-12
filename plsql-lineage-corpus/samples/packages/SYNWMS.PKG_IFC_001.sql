-- ==========================================================================
-- 패키지 : SYNWMS.PKG_IFC_001
-- 설명   : Tier 3 합성 패키지 - IFC 영역 배치 처리
-- 난이도 : Tier 3
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_IFC_001 AS

  -- 입고실적 재고 이관 처리
  FUNCTION FN_MOVE_INB_STOCK (
    p_tab_sfx  IN VARCHAR2,
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_base_ymd IN VARCHAR2
  )
  RETURN NUMBER;

END PKG_IFC_001;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_IFC_001 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_IFC_001';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- FN_MOVE_INB_STOCK : 입고실적 재고 이관 처리
  -- ----------------------------------------------------------------------
  FUNCTION FN_MOVE_INB_STOCK (
    p_tab_sfx  IN VARCHAR2,
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_base_ymd IN VARCHAR2
  )
  RETURN NUMBER
  IS
    v_wh_cd                SYNWMS.INB_ORDER_D.WH_CD%TYPE;
    v_ord_no               SYNWMS.INB_ORDER_H.ORD_NO%TYPE;
    v_reg_id               SYNWMS.INB_ORDER_H.REG_ID%TYPE;
    v_line_stat_cd         SYNWMS.INB_ORDER_D.LINE_STAT_CD%TYPE;
    v_reg_dtm              SYNWMS.MST_ITEM.REG_DTM%TYPE;
    v_vend_cd              SYNWMS.INB_ORDER_H.VEND_CD%TYPE;
    r_row                  SYNWMS.INB_RESULT%ROWTYPE;
    v_tmp_00               NUMBER;
    v_tmp_01               VARCHAR2(30);
    v_tmp_02               NUMBER;
    v_tmp_03               VARCHAR2(30);
    v_tmp_04               NUMBER;
    v_tmp_05               VARCHAR2(30);
    v_cnt                  NUMBER := 0;
    v_err_cnt              NUMBER := 0;
    v_sql                  VARCHAR2(4000);
    v_tab_nm               VARCHAR2(61);
    TYPE t_row_rec IS RECORD (
          TRX_SEQ          NUMBER(12),
      WH_CD            VARCHAR2(10),
      LOC_CD           VARCHAR2(20),
      ITEM_CD          VARCHAR2(30),
      LOT_NO           VARCHAR2(30),
      TRX_TP_CD        VARCHAR2(2),
      TRX_QTY          NUMBER(13,3),
      BEF_QTY          NUMBER(13,3)
        );
    TYPE t_row_tab IS TABLE OF t_row_rec INDEX BY PLS_INTEGER;
    t_rows                 t_row_tab;
  BEGIN

    -- 객체명이 런타임에 결정됨 - 정적 해석 불가
    v_tab_nm := 'SYNWMS.' || p_tab_sfx;
    v_sql := 'TRUNCATE TABLE ' || v_tab_nm || '_BAK';
    EXECUTE IMMEDIATE v_sql;

    -- IF_SND_FROM_SHIP UPSERT
    MERGE INTO SYNIF.IF_ORDER_SND t
    USING (
          SELECT /*+ INDEX(s PK_OUT_SHIP) */
                 SEQ_IF_SND.NEXTVAL AS IF_SEQ,
                 CASE WHEN c.GRADE_CD = '10' THEN s.SHIP_YMD ELSE ' ' END AS IF_YMD,
                 CASE WHEN s.ITEM_CD = '10' THEN s.WH_CD ELSE ' ' END AS WH_CD,
                 CASE WHEN s.WH_CD = '10' THEN s.ORD_NO ELSE ' ' END AS ORD_NO,
                 DECODE(c.AREA_CD, 'Y', s.LINE_NO, 'N', 0, s.LINE_NO) AS LINE_NO,
                 NVL(TRIM(s.ITEM_CD), '-') AS ITEM_CD,
                 CASE WHEN c.CUST_CD = '10' THEN c.CUST_CD ELSE ' ' END AS CUST_CD,
                 CASE WHEN c.GRADE_CD = '10' THEN s.SHIP_QTY ELSE 0 END AS SHIP_QTY,
                 ROUND(NVL(s.SHIP_WGT, 0) * NVL(s.SHIP_WGT, 1), 3) AS SHIP_WGT,
                 NVL(TRIM(s.SHIP_YMD), '-') AS SHIP_YMD,
                 s.TRK_NO AS TRK_NO,
                 '10' AS IF_STAT_CD,
                 CASE WHEN c.CUST_CD IS NULL THEN SYSDATE ELSE SYSDATE END AS SND_DTM
            FROM SYNWMS.OUT_SHIP s
            LEFT JOIN SYNWMS.MST_CUST c
              ON (c.CUST_CD = s.CUST_CD)
           WHERE s.SHIP_QTY > 0
         ) q
        ON (t.IF_SEQ = q.IF_SEQ)
    WHEN MATCHED THEN
      UPDATE SET
        t.IF_YMD  = q.IF_YMD,
        t.WH_CD   = q.WH_CD,
        t.ORD_NO  = q.ORD_NO,
        t.LINE_NO = q.LINE_NO,
        t.ITEM_CD = q.ITEM_CD,
        t.CUST_CD = q.CUST_CD
    WHEN NOT MATCHED THEN
      INSERT (
           IF_SEQ,
           IF_YMD,
           WH_CD,
           ORD_NO,
           LINE_NO,
           ITEM_CD,
           CUST_CD,
           SHIP_QTY,
           SHIP_WGT,
           SHIP_YMD,
           TRK_NO,
           IF_STAT_CD,
           SND_DTM
         )
      VALUES (
           q.IF_SEQ,
           q.IF_YMD,
           q.WH_CD,
           q.ORD_NO,
           q.LINE_NO,
           q.ITEM_CD,
           q.CUST_CD,
           q.SHIP_QTY,
           q.SHIP_WGT,
           q.SHIP_YMD,
           q.TRK_NO,
           q.IF_STAT_CD,
           q.SND_DTM
         );

    -- CTE 경유 집계 적재
    INSERT INTO SYNWMS.OUT_ALLOC (
           WH_CD,
           ORD_NO,
           LINE_NO,
           ALLOC_SEQ,
           ITEM_CD,
           LOC_CD,
           LOT_NO,
           ALLOC_QTY,
           ALLOC_STAT_CD,
           ALLOC_DTM
         )
    WITH w_src AS (
            SELECT
                   CASE WHEN s.ITEM_CD = '10' THEN d.WH_CD ELSE ' ' END AS WH_CD,
                   NVL(TRIM(d.ORD_NO), '-') AS ORD_NO,
                   CASE WHEN h.CUST_CD = '10' THEN d.LINE_NO ELSE 0 END AS LINE_NO,
                   1 AS ALLOC_SEQ,
                   DECODE(d.LINE_STAT_CD, 'Y', d.ITEM_CD, 'N', '*', d.ITEM_CD) AS ITEM_CD,
                   s.LOC_CD AS LOC_CD,
                   CASE WHEN d.LINE_STAT_CD = '10' THEN s.LOT_NO ELSE ' ' END AS LOT_NO,
                   MAX(NVL(d.ORD_QTY, 0)) AS ALLOC_QTY,
                   '10' AS ALLOC_STAT_CD,
                   SYSDATE AS ALLOC_DTM
              FROM SYNWMS.OUT_ORDER_D d
              JOIN SYNWMS.STK_ONHAND s
                ON (s.WH_CD = d.WH_CD AND s.ITEM_CD = d.ITEM_CD)
              JOIN SYNWMS.OUT_ORDER_H h
                ON (h.WH_CD = d.WH_CD AND h.ORD_NO = d.ORD_NO)
             WHERE s.AVAIL_QTY > 0
               AND d.LINE_STAT_CD = '10'
             GROUP BY d.WH_CD, d.ORD_NO, d.LINE_NO, d.ITEM_CD, s.LOC_CD, s.LOT_NO
         )
    SELECT
           w.WH_CD AS WH_CD,
           w.ORD_NO AS ORD_NO,
           w.LINE_NO AS LINE_NO,
           w.ALLOC_SEQ AS ALLOC_SEQ,
           w.ITEM_CD AS ITEM_CD,
           w.LOC_CD AS LOC_CD,
           w.LOT_NO AS LOT_NO,
           w.ALLOC_QTY AS ALLOC_QTY,
           w.ALLOC_STAT_CD AS ALLOC_STAT_CD,
           w.ALLOC_DTM AS ALLOC_DTM
      FROM w_src w;

    -- 대량 조회 (BULK COLLECT)
    SELECT
           SEQ_STK_TRX.NEXTVAL AS TRX_SEQ,
           s.WH_CD AS WH_CD,
           NVL(TRIM(s.LOC_CD), '-') AS LOC_CD,
           s.ITEM_CD AS ITEM_CD,
           NVL(TRIM(s.LOT_NO), '-') AS LOT_NO,
           '10' AS TRX_TP_CD,
           NVL(r.RCV_QTY, 0) AS TRX_QTY,
           s.ONHAND_QTY AS BEF_QTY
      BULK COLLECT INTO t_rows
      FROM SYNWMS.STK_ONHAND s
      LEFT JOIN SYNWMS.INB_RESULT r
        ON (r.WH_CD = s.WH_CD AND r.ITEM_CD = s.ITEM_CD AND r.LOT_NO = s.LOT_NO)
     WHERE s.ONHAND_QTY > 0;

    FORALL i IN 1 .. t_rows.COUNT
      -- 컬렉션 원소 기준 일괄 갱신
      UPDATE SYNWMS.STK_TRX t
         SET t.TRX_QTY = t_rows(i).TRX_QTY
       WHERE t.TRX_SEQ = t_rows(i).TRX_SEQ;

    -- 계층 코드 전개 후 재적재
    INSERT INTO SYNWMS.MST_CODE (
           GRP_CD,
           CD,
           CD_NM,
           UP_CD,
           SORT_NO,
           USE_YN
         )
    SELECT
           c.GRP_CD AS GRP_CD,
           c.CD AS CD,
           LPAD(' ', (LEVEL - 1) * 2) || c.CD_NM AS CD_NM,
           c.UP_CD AS UP_CD,
           LEVEL AS SORT_NO,
           c.USE_YN AS USE_YN
      FROM SYNWMS.MST_CODE c
     WHERE c.USE_YN = 'Y'
     START WITH c.UP_CD IS NULL
     CONNECT BY PRIOR c.CD = c.UP_CD;

    COMMIT;
    RETURN v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'FN_MOVE_INB_STOCK', SQLERRM);
      RAISE;
  END FN_MOVE_INB_STOCK;

END PKG_IFC_001;
/
