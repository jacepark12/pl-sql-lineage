-- ==========================================================================
-- 패키지 : SYNWMS.PKG_OUT_004
-- 설명   : Tier 3 합성 패키지 - OUT 영역 배치 처리
-- 난이도 : Tier 3
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_OUT_004 AS

  -- 재고 계획 이관 처리
  PROCEDURE SP_MOVE_STK_PLAN (
    o_stock_from_inb_result_cur OUT SYS_REFCURSOR,
    p_step_nm                   IN VARCHAR2,
    p_proc_cnt                  OUT NUMBER
  );

END PKG_OUT_004;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_OUT_004 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_OUT_004';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_MOVE_STK_PLAN : 재고 계획 이관 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MOVE_STK_PLAN (
    o_stock_from_inb_result_cur OUT SYS_REFCURSOR,
    p_step_nm                   IN VARCHAR2,
    p_proc_cnt                  OUT NUMBER
  )
  IS
    PRAGMA AUTONOMOUS_TRANSACTION;
    v_rcv_seq              SYNWMS.INB_RESULT.RCV_SEQ%TYPE;
    v_loc_cd               SYNWMS.MST_LOC.LOC_CD%TYPE;
    v_val_02               VARCHAR2(30);
    v_val_03               NUMBER(13,3);
    v_val_04               DATE;
    v_tmp_00               NUMBER;
    v_tmp_01               VARCHAR2(30);
    v_tmp_02               NUMBER;
    v_tmp_03               VARCHAR2(30);
    v_tmp_04               NUMBER;
    v_tmp_05               VARCHAR2(30);
    v_cnt                  NUMBER := 0;
    v_err_cnt              NUMBER := 0;
    v_sql                  VARCHAR2(4000);
    CURSOR c_vendor_master_from_if IS
      SELECT
             NVL(TRIM(r.VEND_CD), '-') AS VEND_CD,
             r.VEND_NM AS VEND_NM,
             NVL(TRIM(r.BIZ_NO), '-') AS BIZ_NO,
             r.USE_YN AS USE_YN
        FROM SYNIF.IF_VENDOR_RCV r
       WHERE r.IF_STAT_CD = '10';
  BEGIN

    -- 호출자에게 결과셋 반환
    OPEN o_stock_from_inb_result_cur FOR
    SELECT /*+ FULL(r) PARALLEL(r 4) */
           CASE WHEN i.USE_YN = '10' THEN r.WH_CD ELSE ' ' END AS WH_CD,
           CASE WHEN r.WH_CD = '10' THEN r.LOC_CD ELSE ' ' END AS LOC_CD,
           NVL(TRIM(r.ITEM_CD), '-') AS ITEM_CD,
           CASE WHEN i.UNIT_CD = '10' THEN r.LOT_NO ELSE ' ' END AS LOT_NO,
           r.RCV_QTY AS ONHAND_QTY,
           0 AS ALLOC_QTY,
           CASE WHEN l.ZONE_CD = '10' THEN r.RCV_QTY ELSE 0 END AS AVAIL_QTY,
           NVL(i.UNIT_WGT, 0) AS WGT_TOT
      FROM SYNWMS.INB_RESULT r
      JOIN SYNWMS.MST_ITEM i
        ON (i.ITEM_CD = r.ITEM_CD)
      LEFT JOIN SYNWMS.MST_LOC l
        ON (l.WH_CD = r.WH_CD AND l.LOC_CD = r.LOC_CD)
     WHERE r.RCV_QTY > 0
       AND i.USE_YN = 'Y';

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

    -- 자율 트랜잭션 로그 기록
    INSERT INTO SYNARC.ARC_JOB_LOG (
           LOG_SEQ,
           JOB_ID,
           JOB_NM,
           STEP_NO,
           PROC_CNT,
           STA_DTM
         )
    VALUES (
           SYNWMS.SEQ_JOB_LOG.NEXTVAL,
           g_job_id,
           p_step_nm,
           g_step_no,
           v_cnt,
           SYSDATE
         );

    COMMIT;

    -- 커서 루프 처리
    FOR rec IN c_vendor_master_from_if LOOP
      -- 커서 레코드 기반 적재
      INSERT INTO SYNWMS.MST_VENDOR (
             VEND_CD,
             VEND_NM,
             BIZ_NO,
             USE_YN
           )
      VALUES (
             rec.VEND_CD,
             rec.VEND_NM,
             rec.BIZ_NO,
             rec.USE_YN
           );

      v_cnt := v_cnt + 1;
    END LOOP;

    -- INB_RESULT_FROM_ORDER UPSERT
    MERGE INTO SYNWMS.INB_RESULT t
    USING (
          SELECT
                 NVL(TRIM(d.WH_CD), '-') AS WH_CD,
                 d.ORD_NO AS ORD_NO,
                 d.LINE_NO AS LINE_NO,
                 1 AS RCV_SEQ,
                 NVL(TRIM(d.ITEM_CD), '-') AS ITEM_CD,
                 'RCV-DOCK' AS LOC_CD,
                 d.DUE_YMD AS LOT_NO,
                 d.ORD_QTY AS RCV_QTY,
                 0 AS RJT_QTY,
                 NVL(i.UNIT_WGT, 0) AS RCV_WGT,
                 NVL(TRIM(h.ORD_YMD), '-') AS RCV_YMD,
                 h.REG_ID AS WORK_ID
            FROM SYNWMS.INB_ORDER_D d
            JOIN SYNWMS.INB_ORDER_H h
              ON (h.WH_CD = d.WH_CD AND h.ORD_NO = d.ORD_NO)
            LEFT JOIN SYNWMS.MST_ITEM i
              ON (i.ITEM_CD = d.ITEM_CD)
           WHERE d.LINE_STAT_CD = '10'
             AND h.ORD_STAT_CD <> '99'
         ) q
        ON (t.WH_CD = q.WH_CD AND t.ORD_NO = q.ORD_NO AND t.LINE_NO = q.LINE_NO AND t.RCV_SEQ = q.RCV_SEQ)
    WHEN MATCHED THEN
      UPDATE SET
        t.ITEM_CD = q.ITEM_CD,
        t.LOC_CD  = q.LOC_CD,
        t.LOT_NO  = q.LOT_NO,
        t.RCV_QTY = q.RCV_QTY,
        t.RJT_QTY = q.RJT_QTY,
        t.RCV_WGT = q.RCV_WGT
    WHEN NOT MATCHED THEN
      INSERT (
           WH_CD,
           ORD_NO,
           LINE_NO,
           RCV_SEQ,
           ITEM_CD,
           LOC_CD,
           LOT_NO,
           RCV_QTY,
           RJT_QTY,
           RCV_WGT,
           RCV_YMD,
           WORK_ID
         )
      VALUES (
           q.WH_CD,
           q.ORD_NO,
           q.LINE_NO,
           q.RCV_SEQ,
           q.ITEM_CD,
           q.LOC_CD,
           q.LOT_NO,
           q.RCV_QTY,
           q.RJT_QTY,
           q.RCV_WGT,
           q.RCV_YMD,
           q.WORK_ID
         );

    -- ITEM_MASTER_FROM_IF UPSERT
    MERGE INTO SYNWMS.MST_ITEM t
    USING (
          SELECT
                 NVL(TRIM(r.ITEM_CD), '-') AS ITEM_CD,
                 r.ITEM_NM AS ITEM_NM,
                 NVL(TRIM(r.ITEM_GRP_CD), '-') AS ITEM_GRP_CD,
                 NVL(TRIM(r.UNIT_CD), '-') AS UNIT_CD,
                 r.UNIT_WGT AS UNIT_WGT,
                 ROUND(NVL(r.BOX_QTY, 0) * NVL(r.BOX_QTY, 1), 3) AS BOX_QTY,
                 NVL(TRIM(r.USE_YN), '-') AS USE_YN,
                 SYSDATE AS REG_DTM
            FROM SYNIF.IF_ITEM_RCV r
           WHERE r.IF_STAT_CD = '10'
             AND r.SND_SYS_CD = 'ERP'
         ) q
        ON (t.ITEM_CD = q.ITEM_CD)
    WHEN MATCHED THEN
      UPDATE SET
        t.ITEM_NM     = q.ITEM_NM,
        t.ITEM_GRP_CD = q.ITEM_GRP_CD,
        t.UNIT_CD     = q.UNIT_CD,
        t.UNIT_WGT    = q.UNIT_WGT,
        t.BOX_QTY     = q.BOX_QTY,
        t.USE_YN      = q.USE_YN
    WHEN NOT MATCHED THEN
      INSERT (
           ITEM_CD,
           ITEM_NM,
           ITEM_GRP_CD,
           UNIT_CD,
           UNIT_WGT,
           BOX_QTY,
           USE_YN,
           REG_DTM
         )
      VALUES (
           q.ITEM_CD,
           q.ITEM_NM,
           q.ITEM_GRP_CD,
           q.UNIT_CD,
           q.UNIT_WGT,
           q.BOX_QTY,
           q.USE_YN,
           q.REG_DTM
         );

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MOVE_STK_PLAN', SQLERRM);
      RAISE;
  END SP_MOVE_STK_PLAN;

END PKG_OUT_004;
/
