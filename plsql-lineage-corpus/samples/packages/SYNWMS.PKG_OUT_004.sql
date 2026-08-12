-- ==========================================================================
-- 패키지 : SYNWMS.PKG_OUT_004
-- 설명   : Tier 3 합성 패키지 - OUT 영역 배치 처리
-- 난이도 : Tier 3
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_OUT_004 AS

  -- 월별 거래집계 전표 송신 처리
  PROCEDURE SP_SEND_RPT_ORDER (
    o_monthly_trx_report_cur OUT SYS_REFCURSOR,
    o_if_snd_from_ship_cur   OUT SYS_REFCURSOR,
    p_tab_sfx                IN VARCHAR2,
    p_wh_cd                  IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_base_ymd               IN VARCHAR2,
    p_WH_CD                  IN SYNWMS.STK_ONHAND.WH_CD%TYPE,
    p_LOC_CD                 IN SYNWMS.STK_ONHAND.LOC_CD%TYPE,
    p_proc_cnt               OUT NUMBER
  );

  -- 품목 기준정보 계획 송신 처리
  PROCEDURE SP_SEND_MST_PLAN (
    p_proc_cnt OUT NUMBER
  );

END PKG_OUT_004;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_OUT_004 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_OUT_004';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_SEND_RPT_ORDER : 월별 거래집계 전표 송신 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_SEND_RPT_ORDER (
    o_monthly_trx_report_cur OUT SYS_REFCURSOR,
    o_if_snd_from_ship_cur   OUT SYS_REFCURSOR,
    p_tab_sfx                IN VARCHAR2,
    p_wh_cd                  IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_base_ymd               IN VARCHAR2,
    p_WH_CD                  IN SYNWMS.STK_ONHAND.WH_CD%TYPE,
    p_LOC_CD                 IN SYNWMS.STK_ONHAND.LOC_CD%TYPE,
    p_proc_cnt               OUT NUMBER
  )
  IS
    v_trx_seq              SYNWMS.STK_TRX.TRX_SEQ%TYPE;
    v_val_01               DATE;
    v_val_02               NUMBER;
    v_val_03               NUMBER;
    v_val_04               VARCHAR2(200);
    v_val_05               NUMBER(13,3);
    v_val_06               NUMBER;
    v_val_07               VARCHAR2(200);
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
    CURSOR c_stock_adjustment IS
      SELECT
             NVL(TRIM(j.WH_CD), '-') AS WH_CD,
             NVL(TRIM(j.LOC_CD), '-') AS LOC_CD,
             j.ITEM_CD AS ITEM_CD,
             j.LOT_NO AS LOT_NO,
             NVL(j.ADJ_QTY, 0) AS ONHAND_QTY,
             0 AS ALLOC_QTY,
             ROUND(NVL(j.ADJ_QTY, 0) * NVL(i.BOX_QTY, 1), 3) AS AVAIL_QTY,
             NVL(i.UNIT_WGT, 0) AS WGT_TOT,
             NVL(TRIM(j.ADJ_YMD), '-') AS LAST_TRX_YMD,
             SYSDATE AS UPD_DTM
        FROM SYNWMS.STK_ADJUST j
        LEFT JOIN SYNWMS.MST_ITEM i
          ON (i.ITEM_CD = j.ITEM_CD)
       WHERE j.RSN_CD <> 'CANCEL';
    v_acc_qty              NUMBER(15,3) := 0;
    v_sum_qty              NUMBER(15,3);
    v_max_key              SYNWMS.OUT_SHIP.WH_CD%TYPE;
  BEGIN

    -- 호출자에게 결과셋 반환
    OPEN o_monthly_trx_report_cur FOR
    SELECT /*+ LEADING(t) */
           t.TRX_YMD AS BASE_YM,
           CASE WHEN i.ITEM_GRP_CD = '10' THEN t.WH_CD ELSE ' ' END AS WH_CD,
           i.ITEM_GRP_CD AS ITEM_GRP_CD,
           CASE WHEN t.LOC_CD = '10' THEN t.TRX_QTY ELSE 0 END AS IN_QTY,
           CASE WHEN i.UNIT_CD IN ('10', '20') THEN t.TRX_QTY
                     WHEN i.UNIT_CD = '30'          THEN t.AFT_QTY
                     ELSE 0
                END AS OUT_QTY,
           CASE WHEN t.WH_CD IN ('10', '20') THEN t.TRX_SEQ
                     WHEN t.WH_CD = '30'          THEN i.BOX_QTY
                     ELSE 0
                END AS TRX_CNT,
           NVL(t.TRX_QTY, 0) AS AVG_QTY
      FROM SYNWMS.STK_TRX t
      JOIN SYNWMS.MST_ITEM i
        ON (i.ITEM_CD = t.ITEM_CD)
     WHERE i.USE_YN = 'Y';

    -- 호출자에게 결과셋 반환
    OPEN o_if_snd_from_ship_cur FOR
    SELECT
           SEQ_IF_SND.NEXTVAL AS IF_SEQ,
           s.SHIP_YMD AS IF_YMD,
           NVL(TRIM(s.WH_CD), '-') AS WH_CD,
           s.ORD_NO AS ORD_NO,
           NVL(s.LINE_NO, 0) AS LINE_NO,
           NVL(TRIM(s.ITEM_CD), '-') AS ITEM_CD,
           NVL(TRIM(c.CUST_CD), '-') AS CUST_CD,
           ROUND(NVL(s.SHIP_QTY, 0) * NVL(s.SHIP_WGT, 1), 3) AS SHIP_QTY
      FROM SYNWMS.OUT_SHIP s
      LEFT JOIN SYNWMS.MST_CUST c
        ON (c.CUST_CD = s.CUST_CD)
     WHERE s.SHIP_QTY > 0;

    -- 객체명이 런타임에 결정됨 - 정적 해석 불가
    v_tab_nm := 'SYNWMS.' || p_tab_sfx || '_' || SUBSTR(p_base_ymd, 1, 6);
    v_sql := 'BEGIN ' || v_tab_nm || '.SP_RUN(:1); END;';
    EXECUTE IMMEDIATE v_sql USING p_wh_cd;

    -- 커서 루프 처리
    FOR rec IN c_stock_adjustment LOOP
      v_acc_qty := NVL(v_acc_qty, 0) + NVL(rec.ONHAND_QTY, 0);

      v_cnt := v_cnt + 1;
    END LOOP;

    -- 루프 누계를 단일 UPDATE로 반영
    UPDATE SYNWMS.STK_ONHAND t
       SET t.ONHAND_QTY = NVL(v_acc_qty, 0)
     WHERE t.WH_CD = p_WH_CD
       AND t.LOC_CD = p_LOC_CD;

    -- 원격 스키마(DB LINK) 원천 적재
    INSERT INTO SYNARC.ARC_OUT_SHIP (
           ARC_SEQ,
           WH_CD,
           ORD_NO,
           SHIP_SEQ,
           ITEM_CD,
           CUST_CD,
           SHIP_QTY,
           SHIP_YMD,
           ARC_DTM
         )
    SELECT
           SEQ_ARC.NEXTVAL AS ARC_SEQ,
           NVL(TRIM(s.WH_CD), '-') AS WH_CD,
           NVL(TRIM(s.ORD_NO), '-') AS ORD_NO,
           NVL(s.SHIP_SEQ, 0) AS SHIP_SEQ,
           NVL(TRIM(s.ITEM_CD), '-') AS ITEM_CD,
           NVL(TRIM(c.CUST_CD), '-') AS CUST_CD,
           NVL(s.SHIP_QTY, 0) AS SHIP_QTY,
           NVL(TRIM(s.SHIP_YMD), '-') AS SHIP_YMD,
           SYSDATE AS ARC_DTM
      FROM SYNWMS.OUT_SHIP@ERPLINK s
      LEFT JOIN SYNWMS.MST_CUST c
        ON (c.CUST_CD = s.CUST_CD)
     WHERE s.SHIP_YMD < TO_CHAR(SYSDATE - 180, 'YYYYMMDD');

    -- 대상 건수 확인
    IF v_cnt > 482 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 462 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 85 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 152 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 461 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    FOR i IN 1 .. 11 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 5449;
    END LOOP;

    -- 배치 단위 조정
    g_step_no := g_step_no + 1;

    -- 후처리 플래그 설정
    IF v_cnt > 283 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계값을 변수로 수신
    SELECT
           NVL(SUM(s.SHIP_QTY), 0) AS SUM_QTY,
           MAX(s.WH_CD) AS MAX_KEY
      INTO v_sum_qty, v_max_key
      FROM SYNWMS.OUT_SHIP s
     WHERE s.WH_CD = p_wh_cd;

    -- 변수 경유 적재 (VIA_VARIABLE)
    INSERT INTO SYNIF.IF_ORDER_SND (
           IF_SEQ,
           SHIP_QTY
         )
    VALUES (
           SEQ_ARC.NEXTVAL,
           NVL(v_sum_qty, 0)
         );

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_SEND_RPT_ORDER', SQLERRM);
      RAISE;
  END SP_SEND_RPT_ORDER;

  -- ----------------------------------------------------------------------
  -- SP_SEND_MST_PLAN : 품목 기준정보 계획 송신 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_SEND_MST_PLAN (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_item_nm              SYNIF.IF_ITEM_RCV.ITEM_NM%TYPE;
    v_box_qty              SYNIF.IF_ITEM_RCV.BOX_QTY%TYPE;
    v_val_02               NUMBER(13,3);
    v_val_03               DATE;
    v_val_04               VARCHAR2(30);
    v_val_05               NUMBER(13,3);
    v_val_06               NUMBER;
    v_tmp_00               NUMBER;
    v_tmp_01               VARCHAR2(30);
    v_tmp_02               NUMBER;
    v_tmp_03               VARCHAR2(30);
    v_tmp_04               NUMBER;
    v_tmp_05               VARCHAR2(30);
    v_cnt                  NUMBER := 0;
    v_err_cnt              NUMBER := 0;
    v_sql                  VARCHAR2(4000);
  BEGIN

    -- ITEM_MASTER_FROM_IF UPSERT
    MERGE INTO SYNWMS.MST_ITEM t
    USING (
          SELECT /*+ FULL(r) PARALLEL(r 4) */
                 CASE WHEN r.UNIT_CD = '10' THEN r.ITEM_CD ELSE ' ' END AS ITEM_CD,
                 r.ITEM_NM AS ITEM_NM,
                 CASE WHEN r.UNIT_CD = '10' THEN r.ITEM_GRP_CD ELSE ' ' END AS ITEM_GRP_CD,
                 NVL(TRIM(r.UNIT_CD), '-') AS UNIT_CD,
                 r.UNIT_WGT AS UNIT_WGT,
                 NVL(r.BOX_QTY, 0) AS BOX_QTY,
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
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_SEND_MST_PLAN', SQLERRM);
      RAISE;
  END SP_SEND_MST_PLAN;

END PKG_OUT_004;
/
