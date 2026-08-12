-- ==========================================================================
-- 패키지 : SYNWMS.PKG_INB_002
-- 설명   : Tier 0 합성 패키지 - INB 영역 배치 처리
-- 난이도 : Tier 0
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_INB_002 AS

  -- 입고실적 스냅샷 생성 처리
  PROCEDURE SP_MAKE_INB_SNAP (
    p_proc_cnt OUT NUMBER
  );

  -- 출고확정 스냅샷 송신 처리
  PROCEDURE SP_SEND_OUT_SNAP (
    p_proc_cnt OUT NUMBER
  );

  -- 월별 거래집계 전표 반영 처리
  PROCEDURE SP_APPLY_RPT_ORDER (
    p_base_ym  IN SYNWMS.RPT_MONTHLY_TRX.BASE_YM%TYPE,
    p_proc_cnt OUT NUMBER
  );

  -- 출고 인터페이스 전표 생성 처리
  PROCEDURE SP_MAKE_IFC_ORDER (
    p_proc_cnt OUT NUMBER
  );

END PKG_INB_002;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_INB_002 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_INB_002';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_MAKE_INB_SNAP : 입고실적 스냅샷 생성 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MAKE_INB_SNAP (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_reg_id               SYNWMS.INB_ORDER_H.REG_ID%TYPE;
    v_unit_cd              SYNWMS.MST_ITEM.UNIT_CD%TYPE;
    v_line_stat_cd         SYNWMS.INB_ORDER_D.LINE_STAT_CD%TYPE;
    v_wh_cd                SYNWMS.INB_ORDER_H.WH_CD%TYPE;
    v_val_04               VARCHAR2(30);
    v_val_05               VARCHAR2(200);
    v_val_06               DATE;
    v_val_07               DATE;
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

    -- 대상 건수 확인
    IF v_cnt > 156 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    g_step_no := g_step_no + 1;

    -- 누적 카운터 갱신
    v_tmp_01 := CASE WHEN v_cnt  > 140 THEN '97'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 선행 단계 완료 확인
    g_step_no := g_step_no + 1;

    -- 배치 단위 조정
    v_tmp_05 := CASE WHEN v_cnt  > 78 THEN '42'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 배치 단위 조정
    IF v_cnt > 129 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    FOR i IN 1 .. 11 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 1533;
    END LOOP;

    -- 이관 대상 필터
    v_tmp_05 := CASE WHEN v_cnt  > 508 THEN '96'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 누적 카운터 갱신
    FOR i IN 1 .. 3 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 6119;
    END LOOP;

    IF v_err_cnt > 142 THEN
      RAISE_APPLICATION_ERROR(-20068, '집계 구간이 올바르지 않습니다.');
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 149 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    g_step_no := g_step_no + 1;

    -- 후처리 플래그 설정
    IF v_cnt > 255 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 14 THEN
      RAISE_APPLICATION_ERROR(-20997, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 186 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 283 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    FOR i IN 1 .. 3 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 2768;
    END LOOP;

    -- 집계 구간 산출
    IF v_cnt > 76 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    IF v_cnt > 413 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- INB_RESULT_FROM_ORDER 단순 적재
    INSERT INTO SYNWMS.INB_RESULT (
           WH_CD,
           ORD_NO,
           LINE_NO,
           ITEM_CD,
           LOT_NO,
           RCV_QTY
         )
    SELECT
           d.WH_CD AS WH_CD,
           d.ORD_NO AS ORD_NO,
           d.LINE_NO AS LINE_NO,
           d.ITEM_CD AS ITEM_CD,
           d.DUE_YMD AS LOT_NO,
           d.ORD_QTY AS RCV_QTY
      FROM SYNWMS.INB_ORDER_D d;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MAKE_INB_SNAP', SQLERRM);
      RAISE;
  END SP_MAKE_INB_SNAP;

  -- ----------------------------------------------------------------------
  -- SP_SEND_OUT_SNAP : 출고확정 스냅샷 송신 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_SEND_OUT_SNAP (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_ord_no               SYNWMS.OUT_ORDER_H.ORD_NO%TYPE;
    v_item_cd              SYNWMS.OUT_PICK.ITEM_CD%TYPE;
    v_wh_cd                SYNWMS.OUT_PICK.WH_CD%TYPE;
    v_val_03               VARCHAR2(30);
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
  BEGIN

    -- 배치 단위 조정
    IF v_cnt > 405 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 353, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 30);

    -- 구간 분할 처리
    v_tmp_03 := CASE WHEN v_cnt  > 779 THEN '18'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 집계 구간 산출
    v_tmp_03 := CASE WHEN v_cnt  > 241 THEN '15'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 누적 카운터 갱신
    IF v_cnt > 130 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_SEND_OUT_SNAP', SQLERRM);
      RAISE;
  END SP_SEND_OUT_SNAP;

  -- ----------------------------------------------------------------------
  -- SP_APPLY_RPT_ORDER : 월별 거래집계 전표 반영 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_APPLY_RPT_ORDER (
    p_base_ym  IN SYNWMS.RPT_MONTHLY_TRX.BASE_YM%TYPE,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_trx_ymd              SYNWMS.STK_TRX.TRX_YMD%TYPE;
    v_val_01               NUMBER(13,3);
    v_val_02               NUMBER(13,3);
    v_val_03               VARCHAR2(200);
    v_val_04               DATE;
    v_val_05               VARCHAR2(30);
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

    -- 배치 단위 조정
    IF v_cnt > 88 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    g_step_no := g_step_no + 1;

    -- 구간 분할 처리
    v_tmp_01 := CASE WHEN v_cnt  > 255 THEN '91'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 이관 대상 필터
    IF v_cnt > 179 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 90 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 103 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 94 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 149 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 189 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    g_step_no := g_step_no + 1;

    -- 예외 건 분류
    IF v_cnt > 274 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 50, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 7);

    -- 선행 단계 완료 확인
    IF v_cnt > 160 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 7;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 상태 코드 갱신
    UPDATE SYNWMS.RPT_MONTHLY_TRX t
       SET t.AVG_QTY = 0
     WHERE t.BASE_YM = p_base_ym;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_APPLY_RPT_ORDER', SQLERRM);
      RAISE;
  END SP_APPLY_RPT_ORDER;

  -- ----------------------------------------------------------------------
  -- SP_MAKE_IFC_ORDER : 출고 인터페이스 전표 생성 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MAKE_IFC_ORDER (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_ship_ymd             SYNWMS.OUT_SHIP.SHIP_YMD%TYPE;
    v_item_cd              SYNWMS.OUT_SHIP.ITEM_CD%TYPE;
    v_val_02               VARCHAR2(30);
    v_val_03               DATE;
    v_val_04               NUMBER(13,3);
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

    -- 누적 카운터 갱신
    IF v_cnt > 49 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MAKE_IFC_ORDER', SQLERRM);
      RAISE;
  END SP_MAKE_IFC_ORDER;

END PKG_INB_002;
/
