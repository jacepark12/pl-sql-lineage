-- ==========================================================================
-- 패키지 : SYNWMS.PKG_STK_006
-- 설명   : Tier 2 합성 패키지 - STK 영역 배치 처리
-- 난이도 : Tier 2
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_STK_006 AS

  -- 재고이동 실적 생성 처리
  PROCEDURE SP_MAKE_STK_RESULT (
    p_proc_cnt OUT NUMBER
  );

  -- 재고이동 계획 생성 처리
  PROCEDURE SP_MAKE_STK_PLAN (
    p_proc_cnt OUT NUMBER
  );

  -- 재고 인터페이스 재고 반영 처리
  PROCEDURE SP_APPLY_IFC_STOCK (
    p_proc_cnt OUT NUMBER
  );

END PKG_STK_006;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_STK_006 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_STK_006';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_MAKE_STK_RESULT : 재고이동 실적 생성 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MAKE_STK_RESULT (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_val_00               NUMBER(13,3);
    v_val_01               NUMBER(13,3);
    v_val_02               NUMBER(13,3);
    v_val_03               VARCHAR2(200);
    v_val_04               NUMBER;
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

    -- 집계 구간 산출
    FOR i IN 1 .. 5 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 3125;
    END LOOP;

    IF v_err_cnt > 145 THEN
      RAISE_APPLICATION_ERROR(-20159, '선행 배치가 완료되지 않았습니다.');
    END IF;

    -- 임계치 비교
    IF v_cnt > 420 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    g_step_no := g_step_no + 1;

    -- 선행 단계 완료 확인
    g_step_no := g_step_no + 1;

    -- 집계 구간 산출
    IF v_cnt > 284 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 149 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 444 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 405 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    g_step_no := g_step_no + 1;

    -- 재처리 대상 판정
    IF v_cnt > 103 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 427 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 439 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 382, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 38);

    -- 예외 건 분류
    FOR i IN 1 .. 4 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 7148;
    END LOOP;

    -- 집계 구간 산출
    IF v_cnt > 295 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 304 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    FOR i IN 1 .. 8 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 2356;
    END LOOP;

    -- 후처리 플래그 설정
    FOR i IN 1 .. 9 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 8501;
    END LOOP;

    -- 처리 종료
    FOR i IN 1 .. 3 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 6527;
    END LOOP;

    -- 마감 대상 조회
    IF v_cnt > 407 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 320 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 426 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 121 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 7 THEN
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
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MAKE_STK_RESULT', SQLERRM);
      RAISE;
  END SP_MAKE_STK_RESULT;

  -- ----------------------------------------------------------------------
  -- SP_MAKE_STK_PLAN : 재고이동 계획 생성 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MAKE_STK_PLAN (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_val_00               VARCHAR2(200);
    v_val_01               VARCHAR2(30);
    v_val_02               VARCHAR2(30);
    v_val_03               VARCHAR2(200);
    v_val_04               VARCHAR2(200);
    v_val_05               NUMBER;
    v_val_06               VARCHAR2(200);
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

    -- 임계치 비교
    IF v_cnt > 321 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 257, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 12);

    v_tmp_01 := TO_CHAR(SYSDATE - 231, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 20);

    -- 대상 건수 확인
    IF v_cnt > 359 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    g_step_no := g_step_no + 1;

    -- 후처리 플래그 설정
    IF v_cnt > 364 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 327 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 250 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 170 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 255 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 36, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 13);

    -- 예외 건 분류
    IF v_cnt > 455 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 212 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 132 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 67 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 30 THEN
      RAISE_APPLICATION_ERROR(-20769, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 배치 단위 조정
    FOR i IN 1 .. 9 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 5137;
    END LOOP;

    -- 집계 구간 산출
    FOR i IN 1 .. 11 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 8344;
    END LOOP;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MAKE_STK_PLAN', SQLERRM);
      RAISE;
  END SP_MAKE_STK_PLAN;

  -- ----------------------------------------------------------------------
  -- SP_APPLY_IFC_STOCK : 재고 인터페이스 재고 반영 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_APPLY_IFC_STOCK (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_val_00               VARCHAR2(200);
    v_val_01               NUMBER;
    v_val_02               NUMBER;
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

    -- 인터페이스 상태 갱신
    IF v_cnt > 188 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 250 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 1 THEN
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
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_APPLY_IFC_STOCK', SQLERRM);
      RAISE;
  END SP_APPLY_IFC_STOCK;

END PKG_STK_006;
/
