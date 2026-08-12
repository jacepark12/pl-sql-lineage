-- ==========================================================================
-- 패키지 : SYNWMS.PKG_STK_006
-- 설명   : Tier 2 합성 패키지 - STK 영역 배치 처리
-- 난이도 : Tier 2
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_STK_006 AS

  -- 품목 기준정보 실적 병합 처리
  PROCEDURE SP_MERGE_MST_RESULT (
    p_proc_cnt OUT NUMBER
  );

  -- 재고 일마감 점검 처리
  PROCEDURE SP_CHECK_STK_DAILY (
    p_proc_cnt OUT NUMBER
  );

  -- 업무 전표 마감 처리
  FUNCTION FN_CLOSE_WMS_ORDER
  RETURN NUMBER;

END PKG_STK_006;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_STK_006 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_STK_006';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_MERGE_MST_RESULT : 품목 기준정보 실적 병합 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MERGE_MST_RESULT (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_val_00               NUMBER;
    v_val_01               VARCHAR2(30);
    v_val_02               NUMBER;
    v_val_03               DATE;
    v_val_04               DATE;
    v_val_05               NUMBER(13,3);
    v_val_06               DATE;
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

    -- 후처리 플래그 설정
    IF v_cnt > 297 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 493 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 178 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 298, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 21);

    -- 누적 카운터 갱신
    IF v_cnt > 240 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    FOR i IN 1 .. 2 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 4873;
    END LOOP;

    -- 임계치 비교
    IF v_cnt > 311 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 285, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 13);

    -- 구간 분할 처리
    IF v_cnt > 255 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 10 THEN
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
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MERGE_MST_RESULT', SQLERRM);
      RAISE;
  END SP_MERGE_MST_RESULT;

  -- ----------------------------------------------------------------------
  -- SP_CHECK_STK_DAILY : 재고 일마감 점검 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CHECK_STK_DAILY (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_val_00               VARCHAR2(200);
    v_val_01               DATE;
    v_val_02               NUMBER(13,3);
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

    -- 마감 대상 조회
    IF v_cnt > 409 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 46 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 483 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 118 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 387 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 476 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 254, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 33);

    -- 집계 구간 산출
    IF v_cnt > 329 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 277 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 7;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 187 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 116 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 110, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 29);

    IF v_err_cnt > 44 THEN
      RAISE_APPLICATION_ERROR(-20192, '집계 구간이 올바르지 않습니다.');
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 293 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 148 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 284 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 134, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 21);

    IF v_err_cnt > 98 THEN
      RAISE_APPLICATION_ERROR(-20354, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 394 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 264, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 26);

    -- 인터페이스 상태 갱신
    IF v_cnt > 75 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 465 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 19 THEN
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
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CHECK_STK_DAILY', SQLERRM);
      RAISE;
  END SP_CHECK_STK_DAILY;

  -- ----------------------------------------------------------------------
  -- FN_CLOSE_WMS_ORDER : 업무 전표 마감 처리
  -- ----------------------------------------------------------------------
  FUNCTION FN_CLOSE_WMS_ORDER
  RETURN NUMBER
  IS
    v_val_00               VARCHAR2(200);
    v_val_01               NUMBER;
    v_val_02               DATE;
    v_val_03               NUMBER(13,3);
    v_val_04               NUMBER(13,3);
    v_val_05               VARCHAR2(200);
    v_val_06               VARCHAR2(30);
    v_val_07               NUMBER(13,3);
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

    v_tmp_03 := TO_CHAR(SYSDATE - 124, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 16);

    COMMIT;
    RETURN v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'FN_CLOSE_WMS_ORDER', SQLERRM);
      RAISE;
  END FN_CLOSE_WMS_ORDER;

END PKG_STK_006;
/
