-- ==========================================================================
-- 패키지 : SYNWMS.PKG_IFC_001
-- 설명   : Tier 3 합성 패키지 - IFC 영역 배치 처리
-- 난이도 : Tier 3
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_IFC_001 AS

  -- 입고실적 실적 산출 처리
  PROCEDURE SP_CALC_INB_RESULT (
    p_tab_sfx         IN VARCHAR2,
    p_wh_cd           IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_base_ymd        IN VARCHAR2,
    p_IF_SEQ          IN SYNIF.IF_ORDER_SND.IF_SEQ%TYPE,
    o_archive_trx_cur OUT SYS_REFCURSOR,
    p_proc_cnt        OUT NUMBER
  );

END PKG_IFC_001;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_IFC_001 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_IFC_001';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_CALC_INB_RESULT : 입고실적 실적 산출 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CALC_INB_RESULT (
    p_tab_sfx         IN VARCHAR2,
    p_wh_cd           IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_base_ymd        IN VARCHAR2,
    p_IF_SEQ          IN SYNIF.IF_ORDER_SND.IF_SEQ%TYPE,
    o_archive_trx_cur OUT SYS_REFCURSOR,
    p_proc_cnt        OUT NUMBER
  )
  IS
    v_unit_cd              SYNWMS.MST_ITEM.UNIT_CD%TYPE;
    v_wh_cd                SYNWMS.INB_ORDER_D.WH_CD%TYPE;
    v_ord_no               SYNWMS.INB_ORDER_H.ORD_NO%TYPE;
    v_line_stat_cd         SYNWMS.INB_ORDER_D.LINE_STAT_CD%TYPE;
    v_due_ymd              SYNWMS.INB_ORDER_D.DUE_YMD%TYPE;
    v_line_no              SYNWMS.INB_ORDER_D.LINE_NO%TYPE;
    v_reg_dtm              SYNWMS.INB_ORDER_H.REG_DTM%TYPE;
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
          WH_CD            VARCHAR2(10),
      LOC_CD           VARCHAR2(20),
      ITEM_CD          VARCHAR2(30),
      LOT_NO           VARCHAR2(30),
      ONHAND_QTY       NUMBER(13,3),
      ALLOC_QTY        NUMBER(13,3),
      AVAIL_QTY        NUMBER(13,3),
      WGT_TOT          NUMBER(13,3)
        );
    TYPE t_row_tab IS TABLE OF t_row_rec INDEX BY PLS_INTEGER;
    t_rows                 t_row_tab;
    CURSOR c_if_snd_from_ship IS
      SELECT
             SEQ_IF_SND.NEXTVAL AS IF_SEQ,
             CASE WHEN s.ITEM_CD = '10' THEN s.SHIP_YMD ELSE ' ' END AS IF_YMD,
             CASE WHEN c.AREA_CD = '10' THEN s.WH_CD ELSE ' ' END AS WH_CD,
             CASE WHEN s.ITEM_CD = '10' THEN s.ORD_NO ELSE ' ' END AS ORD_NO,
             s.LINE_NO AS LINE_NO,
             CASE WHEN c.GRADE_CD = '10' THEN s.ITEM_CD ELSE ' ' END AS ITEM_CD,
             NVL(TRIM(c.CUST_CD), '-') AS CUST_CD,
             ROUND(NVL(s.SHIP_QTY, 0) * NVL(s.SHIP_WGT, 1), 3) AS SHIP_QTY,
             CASE WHEN c.USE_YN IN ('10', '20') THEN s.SHIP_WGT
                       WHEN c.USE_YN = '30'          THEN s.SHIP_WGT
                       ELSE 0
                  END AS SHIP_WGT,
             NVL(TRIM(s.SHIP_YMD), '-') AS SHIP_YMD,
             CASE WHEN s.CUST_CD = '10' THEN s.TRK_NO ELSE ' ' END AS TRK_NO,
             '10' AS IF_STAT_CD,
             SYSDATE AS SND_DTM
        FROM SYNWMS.OUT_SHIP s
        LEFT JOIN SYNWMS.MST_CUST c
          ON (c.CUST_CD = s.CUST_CD)
       WHERE s.SHIP_QTY > 0;
    v_acc_qty              NUMBER(15,3) := 0;
  BEGIN

    -- 객체명이 런타임에 결정됨 - 정적 해석 불가
    v_tab_nm := 'SYNWMS.' || p_tab_sfx;
    v_sql := 'TRUNCATE TABLE ' || v_tab_nm || '_BAK';
    EXECUTE IMMEDIATE v_sql;

    -- 대량 조회 (BULK COLLECT)
    SELECT /*+ INDEX(r PK_INB_RESULT) */
           CASE WHEN l.USE_YN = '10' THEN r.WH_CD ELSE ' ' END AS WH_CD,
           CASE WHEN i.UNIT_CD = '10' THEN r.LOC_CD ELSE ' ' END AS LOC_CD,
           CASE WHEN r.ITEM_CD = '10' THEN r.ITEM_CD ELSE ' ' END AS ITEM_CD,
           DECODE(l.ZONE_CD, 'Y', r.LOT_NO, 'N', '*', r.LOT_NO) AS LOT_NO,
           NVL(r.RCV_QTY, 0) AS ONHAND_QTY,
           0 AS ALLOC_QTY,
           DECODE(l.LOC_CD, 'Y', r.RCV_QTY, 'N', 0, r.RCV_QTY) AS AVAIL_QTY,
           i.UNIT_WGT AS WGT_TOT
      BULK COLLECT INTO t_rows
      FROM SYNWMS.INB_RESULT r
      JOIN SYNWMS.MST_ITEM i
        ON (i.ITEM_CD = r.ITEM_CD)
      LEFT JOIN SYNWMS.MST_LOC l
        ON (l.WH_CD = r.WH_CD AND l.LOC_CD = r.LOC_CD)
     WHERE r.RCV_QTY > 0
       AND i.USE_YN = 'Y';

    FORALL i IN 1 .. t_rows.COUNT
      -- 컬렉션 원소 기준 일괄 갱신
      UPDATE SYNWMS.STK_ONHAND t
         SET t.ONHAND_QTY = t_rows(i).ONHAND_QTY
       WHERE t.WH_CD = t_rows(i).WH_CD
         AND t.LOC_CD = t_rows(i).LOC_CD;

    -- 커서 루프 처리
    FOR rec IN c_if_snd_from_ship LOOP
      v_acc_qty := NVL(v_acc_qty, 0) + NVL(rec.SHIP_QTY, 0);

      v_cnt := v_cnt + 1;
    END LOOP;

    -- 배치 단위 조정
    IF v_cnt > 39 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    g_step_no := g_step_no + 1;

    v_tmp_05 := TO_CHAR(SYSDATE - 81, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 11);

    -- 후처리 플래그 설정
    FOR i IN 1 .. 7 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 2750;
    END LOOP;

    -- 처리 시작
    IF v_cnt > 299 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 493 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 루프 누계를 단일 UPDATE로 반영
    UPDATE SYNIF.IF_ORDER_SND t
       SET t.SHIP_QTY = NVL(v_acc_qty, 0)
     WHERE t.IF_SEQ = p_IF_SEQ;

    -- 호출자에게 결과셋 반환
    OPEN o_archive_trx_cur FOR
    SELECT
           SEQ_ARC.NEXTVAL AS ARC_SEQ,
           ROUND(NVL(t.TRX_SEQ, 0) * NVL(t.AFT_QTY, 1), 3) AS TRX_SEQ,
           t.WH_CD AS WH_CD,
           NVL(TRIM(t.ITEM_CD), '-') AS ITEM_CD,
           t.TRX_TP_CD AS TRX_TP_CD,
           t.TRX_QTY AS TRX_QTY,
           NVL(TRIM(t.TRX_YMD), '-') AS TRX_YMD,
           SYSDATE AS ARC_DTM
      FROM SYNWMS.STK_TRX t
     WHERE t.TRX_YMD < TO_CHAR(SYSDATE - 365, 'YYYYMMDD');

    -- VENDOR_MASTER_FROM_IF 단순 적재
    INSERT INTO SYNWMS.MST_VENDOR (
           VEND_CD,
           VEND_NM,
           BIZ_NO,
           USE_YN
         )
    SELECT
           r.VEND_CD AS VEND_CD,
           r.VEND_NM AS VEND_NM,
           r.BIZ_NO AS BIZ_NO,
           r.USE_YN AS USE_YN
      FROM SYNIF.IF_VENDOR_RCV r;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CALC_INB_RESULT', SQLERRM);
      RAISE;
  END SP_CALC_INB_RESULT;

END PKG_IFC_001;
/
