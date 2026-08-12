-- ==========================================================================
-- 패키지 : SYNWMS.PKG_RPT_005
-- 설명   : Tier 2 합성 패키지 - RPT 영역 배치 처리
-- 난이도 : Tier 2
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_RPT_005 AS

  -- 출고 아카이브 배치 이관 처리
  FUNCTION FN_MOVE_ARC_BATCH (
    p_base_ymd IN VARCHAR2
  )
  RETURN NUMBER;

  -- 출고 인터페이스 전표 산출 처리
  PROCEDURE SP_CALC_IFC_ORDER (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  );

  -- 재고이동 전표 마감 처리
  PROCEDURE SP_CLOSE_STK_ORDER (
    p_proc_cnt OUT NUMBER
  );

END PKG_RPT_005;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_RPT_005 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_RPT_005';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- FN_MOVE_ARC_BATCH : 출고 아카이브 배치 이관 처리
  -- ----------------------------------------------------------------------
  FUNCTION FN_MOVE_ARC_BATCH (
    p_base_ymd IN VARCHAR2
  )
  RETURN NUMBER
  IS
    v_item_cd              SYNWMS.OUT_SHIP.ITEM_CD%TYPE;
    v_line_no              SYNWMS.OUT_SHIP.LINE_NO%TYPE;
    v_val_02               VARCHAR2(200);
    v_val_03               DATE;
    v_val_04               VARCHAR2(30);
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

    -- 마감 대상 조회
    g_step_no := g_step_no + 1;

    -- 후처리 플래그 설정
    IF v_cnt > 394 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    FOR i IN 1 .. 4 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 2427;
    END LOOP;

    -- 재처리 대상 판정
    FOR i IN 1 .. 4 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 250;
    END LOOP;

    -- 이관 대상 필터
    FOR i IN 1 .. 8 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 1186;
    END LOOP;

    v_tmp_05 := DECODE(SIGN(v_cnt - 2), 1, 'Y', 0, 'E', 'N');

    -- 구간 분할 처리
    v_tmp_03 := CASE WHEN v_cnt  > 789 THEN '20'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    IF v_err_cnt > 18 THEN
      RAISE_APPLICATION_ERROR(-20265, '집계 구간이 올바르지 않습니다.');
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 281 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    v_tmp_05 := CASE WHEN v_cnt  > 248 THEN '51'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 임계치 비교
    FOR i IN 1 .. 10 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 1130;
    END LOOP;

    -- 인터페이스 상태 갱신
    IF v_cnt > 384 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    FOR i IN 1 .. 3 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 5103;
    END LOOP;

    -- 집계 구간 산출
    FOR i IN 1 .. 10 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 8412;
    END LOOP;

    -- 인터페이스 상태 갱신
    g_step_no := g_step_no + 1;

    -- 임계치 비교
    IF v_cnt > 95 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 237 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 29 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 262 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 129 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 190 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 81 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 7;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    FOR i IN 1 .. 8 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 2839;
    END LOOP;

    IF v_err_cnt > 110 THEN
      RAISE_APPLICATION_ERROR(-20574, '선행 배치가 완료되지 않았습니다.');
    END IF;

    IF v_err_cnt > 39 THEN
      RAISE_APPLICATION_ERROR(-20493, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 256 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 336, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 9);

    -- 후처리 플래그 설정
    IF v_cnt > 97 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    FOR i IN 1 .. 8 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 4371;
    END LOOP;

    -- 임계치 비교
    IF v_cnt > 311 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 281 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 458 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 386 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

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

    -- 재고 스냅샷 전량 아카이브 (컬럼 전개 필요)
    INSERT INTO SYNARC.ARC_STK_ONHAND
    SELECT
           s.*
      FROM SYNWMS.STK_ONHAND s
     WHERE s.ONHAND_QTY > 0;

    -- 인라인 뷰 SELECT * 경유 아카이브
    INSERT INTO SYNARC.ARC_STK_TRX (
           ARC_SEQ,
           TRX_SEQ,
           WH_CD,
           ITEM_CD,
           TRX_TP_CD,
           TRX_QTY,
           TRX_YMD,
           ARC_DTM
         )
    SELECT
           SEQ_ARC.NEXTVAL AS ARC_SEQ,
           v.TRX_SEQ AS TRX_SEQ,
           v.WH_CD AS WH_CD,
           v.ITEM_CD AS ITEM_CD,
           v.TRX_TP_CD AS TRX_TP_CD,
           v.TRX_QTY AS TRX_QTY,
           v.TRX_YMD AS TRX_YMD,
           SYSDATE AS ARC_DTM
      FROM (
            SELECT
                   x.*
              FROM SYNWMS.STK_TRX x
             WHERE x.TRX_YMD = p_base_ymd
           ) v;

    COMMIT;
    RETURN v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'FN_MOVE_ARC_BATCH', SQLERRM);
      RAISE;
  END FN_MOVE_ARC_BATCH;

  -- ----------------------------------------------------------------------
  -- SP_CALC_IFC_ORDER : 출고 인터페이스 전표 산출 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CALC_IFC_ORDER (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_area_cd              SYNWMS.MST_CUST.AREA_CD%TYPE;
    v_grade_cd             SYNWMS.MST_CUST.GRADE_CD%TYPE;
    v_ship_wgt             SYNWMS.OUT_SHIP.SHIP_WGT%TYPE;
    v_ship_ymd             SYNWMS.OUT_SHIP.SHIP_YMD%TYPE;
    v_cust_cd              SYNWMS.OUT_SHIP.CUST_CD%TYPE;
    v_val_05               DATE;
    v_val_06               NUMBER(13,3);
    v_val_07               VARCHAR2(30);
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

    v_tmp_03 := TO_CHAR(SYSDATE - 203, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 24);

    v_tmp_01 := TO_CHAR(SYSDATE - 135, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 7);

    -- 후처리 플래그 설정
    IF v_cnt > 458 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 109, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 25);

    -- 마감 대상 조회
    v_tmp_01 := CASE WHEN v_cnt  > 557 THEN '51'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 구간 분할 처리
    v_tmp_01 := CASE WHEN v_cnt  > 768 THEN '16'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 마감 대상 조회
    v_tmp_03 := CASE WHEN v_cnt  > 594 THEN '14'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 선행 단계 완료 확인
    v_tmp_01 := CASE WHEN v_cnt  > 15 THEN '31'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 인터페이스 상태 갱신
    IF v_cnt > 2 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    FOR i IN 1 .. 11 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 7664;
    END LOOP;

    -- 집계 구간 산출
    g_step_no := g_step_no + 1;

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

    -- 재처리 대상 판정
    IF v_cnt > 413 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 13 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 55 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    g_step_no := g_step_no + 1;

    -- 대상 건수 확인
    IF v_cnt > 343 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 40 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 393 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    FOR i IN 1 .. 6 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 5256;
    END LOOP;

    v_tmp_05 := TO_CHAR(SYSDATE - 255, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 17);

    v_tmp_01 := TO_CHAR(SYSDATE - 145, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 2);

    -- 마감 대상 조회
    IF v_cnt > 144 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 379 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 133, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 38);

    -- 처리 시작
    IF v_cnt > 42 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 249 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    FOR i IN 1 .. 3 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 7197;
    END LOOP;

    -- 후처리 플래그 설정
    IF v_cnt > 122 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 55 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 19 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 408 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 155 THEN
      RAISE_APPLICATION_ERROR(-20075, '선행 배치가 완료되지 않았습니다.');
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 4 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 368 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    FOR i IN 1 .. 2 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 6068;
    END LOOP;

    -- 처리 종료
    IF v_cnt > 437 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 188 THEN
      RAISE_APPLICATION_ERROR(-20063, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 예외 건 분류
    IF v_cnt > 245 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 76 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 224 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 379 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    FOR i IN 1 .. 6 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 9741;
    END LOOP;

    -- 임계치 비교
    g_step_no := g_step_no + 1;

    IF v_err_cnt > 146 THEN
      RAISE_APPLICATION_ERROR(-20753, '선행 배치가 완료되지 않았습니다.');
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 17 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 333 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 381 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 339, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 24);

    IF v_err_cnt > 70 THEN
      RAISE_APPLICATION_ERROR(-20555, '집계 구간이 올바르지 않습니다.');
    END IF;

    -- 원천 집계값으로 수량 재계산
    UPDATE SYNIF.IF_ORDER_SND t
       SET t.SHIP_QTY = NVL((SELECT SUM(NVL(s.SHIP_QTY, 0)) AS SUM_QTY FROM SYNWMS.OUT_SHIP s), 0),
           t.SHIP_WGT = NVL((SELECT SUM(NVL(s.SHIP_WGT, 0)) AS SUM_QTY FROM SYNWMS.OUT_SHIP s), 0)
     WHERE t.WH_CD = p_wh_cd;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CALC_IFC_ORDER', SQLERRM);
      RAISE;
  END SP_CALC_IFC_ORDER;

  -- ----------------------------------------------------------------------
  -- SP_CLOSE_STK_ORDER : 재고이동 전표 마감 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CLOSE_STK_ORDER (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_wgt_tot              SYNWMS.STK_ONHAND.WGT_TOT%TYPE;
    v_val_01               NUMBER(13,3);
    v_val_02               VARCHAR2(200);
    v_val_03               VARCHAR2(30);
    v_val_04               VARCHAR2(200);
    v_val_05               NUMBER(13,3);
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

    -- TRX_FROM_STOCK UPSERT
    MERGE INTO SYNWMS.STK_TRX t
    USING (
          SELECT
                 SEQ_STK_TRX.NEXTVAL AS TRX_SEQ,
                 CASE WHEN s.LOC_CD = '10' THEN s.WH_CD ELSE ' ' END AS WH_CD,
                 NVL(TRIM(s.LOC_CD), '-') AS LOC_CD,
                 CASE WHEN r.LOC_CD = '10' THEN s.ITEM_CD ELSE ' ' END AS ITEM_CD,
                 s.LOT_NO AS LOT_NO,
                 '10' AS TRX_TP_CD,
                 ROUND(NVL(r.RCV_QTY, 0) * NVL(s.WGT_TOT, 1), 3) AS TRX_QTY,
                 s.ONHAND_QTY AS BEF_QTY,
                 s.ONHAND_QTY AS AFT_QTY,
                 ROUND(NVL(s.WGT_TOT, 0) * NVL(s.ALLOC_QTY, 1), 3) AS TRX_WGT,
                 NVL(TRIM(s.LAST_TRX_YMD), '-') AS TRX_YMD,
                 NVL(TRIM(r.ORD_NO), '-') AS REF_NO
            FROM SYNWMS.STK_ONHAND s
            LEFT JOIN SYNWMS.INB_RESULT r
              ON (r.WH_CD = s.WH_CD AND r.ITEM_CD = s.ITEM_CD AND r.LOT_NO = s.LOT_NO)
           WHERE s.ONHAND_QTY > 0
         ) q
        ON (t.TRX_SEQ = q.TRX_SEQ)
    WHEN MATCHED THEN
      UPDATE SET
        t.WH_CD     = q.WH_CD,
        t.LOC_CD    = q.LOC_CD,
        t.ITEM_CD   = q.ITEM_CD,
        t.LOT_NO    = q.LOT_NO,
        t.TRX_TP_CD = q.TRX_TP_CD,
        t.TRX_QTY   = q.TRX_QTY
    WHEN NOT MATCHED THEN
      INSERT (
           TRX_SEQ,
           WH_CD,
           LOC_CD,
           ITEM_CD,
           LOT_NO,
           TRX_TP_CD,
           TRX_QTY,
           BEF_QTY,
           AFT_QTY,
           TRX_WGT,
           TRX_YMD,
           REF_NO
         )
      VALUES (
           q.TRX_SEQ,
           q.WH_CD,
           q.LOC_CD,
           q.ITEM_CD,
           q.LOT_NO,
           q.TRX_TP_CD,
           q.TRX_QTY,
           q.BEF_QTY,
           q.AFT_QTY,
           q.TRX_WGT,
           q.TRX_YMD,
           q.REF_NO
         );

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CLOSE_STK_ORDER', SQLERRM);
      RAISE;
  END SP_CLOSE_STK_ORDER;

END PKG_RPT_005;
/
