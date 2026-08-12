-- ==========================================================================
-- 패키지 : SYNWMS.PKG_MST_003
-- 설명   : Tier 1 합성 패키지 - MST 영역 배치 처리
-- 난이도 : Tier 1
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_MST_003 AS

  -- 출고 아카이브 일마감 마감 처리
  PROCEDURE SP_CLOSE_ARC_DAILY (
    p_base_ymd IN VARCHAR2,
    p_proc_cnt OUT NUMBER
  );

  -- 일별 재고집계 스냅샷 생성 처리
  PROCEDURE SP_MAKE_RPT_SNAP (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  );

  -- 출고 아카이브 일마감 생성 처리
  PROCEDURE SP_MAKE_ARC_DAILY (
    p_proc_cnt OUT NUMBER
  );

  -- 일별 재고집계 재고 분할 처리
  PROCEDURE SP_SPLIT_RPT_STOCK (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  );

  -- 출고할당 이력 집계 처리
  FUNCTION FN_SUM_OUT_HIST (
    p_wh_cd IN SYNWMS.MST_WHOUSE.WH_CD%TYPE
  )
  RETURN NUMBER;

  -- 입고실적 전표 정리 처리
  FUNCTION FN_CLEAN_INB_ORDER
  RETURN NUMBER;

END PKG_MST_003;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_MST_003 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_MST_003';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_CLOSE_ARC_DAILY : 출고 아카이브 일마감 마감 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CLOSE_ARC_DAILY (
    p_base_ymd IN VARCHAR2,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_ship_seq             SYNWMS.OUT_SHIP.SHIP_SEQ%TYPE;
    v_val_01               VARCHAR2(30);
    v_val_02               NUMBER;
    v_val_03               VARCHAR2(30);
    v_val_04               DATE;
    v_val_05               VARCHAR2(200);
    v_val_06               NUMBER(13,3);
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

    -- 재처리 대상 판정
    IF v_cnt > 78 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 42, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 20);

    -- 임계치 비교
    IF v_cnt > 113 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    FOR i IN 1 .. 8 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 1427;
    END LOOP;

    -- 마감 대상 조회
    IF v_cnt > 155 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 493 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 56 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 151 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    FOR i IN 1 .. 3 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 8117;
    END LOOP;

    -- 구간 분할 처리
    IF v_cnt > 121 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 106 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 339 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 143 THEN
      RAISE_APPLICATION_ERROR(-20739, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 496 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 59, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 3);

    -- 배치 단위 조정
    IF v_cnt > 496 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 25 THEN
      RAISE_APPLICATION_ERROR(-20619, '선행 배치가 완료되지 않았습니다.');
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 295 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 203 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 195 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    IF v_cnt > 295 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 73 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 56 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 199 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 422 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 320 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    IF v_cnt > 422 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 345 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 278 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 87 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 229, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 6);

    -- 임계치 비교
    IF v_cnt > 134 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 266 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 249 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 139 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 162 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 46 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 363 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 219 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 3 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 10 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    FOR i IN 1 .. 4 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 6684;
    END LOOP;

    -- 후처리 플래그 설정
    IF v_cnt > 133 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 66 THEN
      RAISE_APPLICATION_ERROR(-20528, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 처리 시작
    g_step_no := g_step_no + 1;

    -- 구간 분할 처리
    FOR i IN 1 .. 10 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 9787;
    END LOOP;

    -- 이관 대상 필터
    IF v_cnt > 207 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 151 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 180 THEN
      RAISE_APPLICATION_ERROR(-20668, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 48 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 387 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 364, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 7);

    -- 집계 구간 산출
    FOR i IN 1 .. 10 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 5224;
    END LOOP;

    -- 재처리 대상 판정
    IF v_cnt > 284 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 471 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 3 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 103 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 75 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    FOR i IN 1 .. 7 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 8668;
    END LOOP;

    -- 보존기간 경과 데이터 삭제
    DELETE FROM SYNARC.ARC_OUT_SHIP t
     WHERE t.SHIP_YMD < p_base_ymd;

    -- TRX_FROM_STOCK 조인 적재
    INSERT INTO SYNWMS.STK_TRX (
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
    SELECT
           SEQ_STK_TRX.NEXTVAL AS TRX_SEQ,
           DECODE(r.WH_CD, 'Y', s.WH_CD, 'N', '*', s.WH_CD) AS WH_CD,
           NVL(TRIM(s.LOC_CD), '-') AS LOC_CD,
           CASE WHEN s.WH_CD = '10' THEN s.ITEM_CD ELSE ' ' END AS ITEM_CD,
           CASE WHEN s.LOC_CD = '10' THEN s.LOT_NO ELSE ' ' END AS LOT_NO,
           '10' AS TRX_TP_CD,
           SUM(r.RCV_QTY) OVER (PARTITION BY r.WH_CD ORDER BY r.RCV_QTY) AS TRX_QTY,
           SUM(s.ONHAND_QTY) OVER (PARTITION BY s.WH_CD ORDER BY s.ONHAND_QTY) AS BEF_QTY,
           SUM(s.ONHAND_QTY) OVER (PARTITION BY r.ITEM_CD ORDER BY s.ONHAND_QTY) AS AFT_QTY,
           SUM(s.WGT_TOT) OVER (PARTITION BY s.ITEM_CD ORDER BY s.WGT_TOT) AS TRX_WGT,
           NVL(TRIM(s.LAST_TRX_YMD), '-') AS TRX_YMD,
           NVL(TRIM(r.ORD_NO), '-') AS REF_NO
      FROM SYNWMS.STK_ONHAND s
         , SYNWMS.INB_RESULT r
     WHERE r.WH_CD(+) = s.WH_CD
       AND r.ITEM_CD(+) = s.ITEM_CD
       AND r.LOT_NO(+) = s.LOT_NO
       AND s.ONHAND_QTY > 0;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CLOSE_ARC_DAILY', SQLERRM);
      RAISE;
  END SP_CLOSE_ARC_DAILY;

  -- ----------------------------------------------------------------------
  -- SP_MAKE_RPT_SNAP : 일별 재고집계 스냅샷 생성 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MAKE_RPT_SNAP (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_lot_no               SYNWMS.STK_ONHAND.LOT_NO%TYPE;
    v_item_cd              SYNWMS.STK_TRX.ITEM_CD%TYPE;
    v_lot_no_02            SYNWMS.STK_TRX.LOT_NO%TYPE;
    r_row                  SYNWMS.RPT_DAILY_STK%ROWTYPE;
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
    FOR i IN 1 .. 6 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 9170;
    END LOOP;

    -- 대상 건수 확인
    v_tmp_01 := CASE WHEN v_cnt  > 407 THEN '41'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 누적 카운터 갱신
    IF v_cnt > 40 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 69 THEN
      RAISE_APPLICATION_ERROR(-20371, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 임계치 비교
    IF v_cnt > 276 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    IF v_cnt > 328 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 169, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 36);

    -- 구간 분할 처리
    IF v_cnt > 399 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    IF v_cnt > 4 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    FOR i IN 1 .. 6 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 6948;
    END LOOP;

    -- 후처리 플래그 설정
    v_tmp_05 := CASE WHEN v_cnt  > 416 THEN '39'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    IF v_err_cnt > 193 THEN
      RAISE_APPLICATION_ERROR(-20486, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 누적 카운터 갱신
    v_tmp_03 := CASE WHEN v_cnt  > 597 THEN '85'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 후처리 플래그 설정
    v_tmp_05 := CASE WHEN v_cnt  > 224 THEN '90'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 구간 분할 처리
    v_tmp_05 := CASE WHEN v_cnt  > 891 THEN '46'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 집계 구간 산출
    FOR i IN 1 .. 10 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 1130;
    END LOOP;

    -- 인터페이스 상태 갱신
    v_tmp_03 := CASE WHEN v_cnt  > 469 THEN '92'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 처리 시작
    FOR i IN 1 .. 2 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 3305;
    END LOOP;

    IF v_err_cnt > 158 THEN
      RAISE_APPLICATION_ERROR(-20714, '기준 정보가 존재하지 않습니다.');
    END IF;

    IF v_err_cnt > 85 THEN
      RAISE_APPLICATION_ERROR(-20059, '선행 배치가 완료되지 않았습니다.');
    END IF;

    v_tmp_03 := DECODE(SIGN(v_cnt - 16), 1, 'Y', 0, 'E', 'N');

    -- 재처리 대상 판정
    IF v_cnt > 166 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 171 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 원천 집계값으로 수량 재계산
    UPDATE SYNWMS.RPT_DAILY_STK t
       SET t.BGN_QTY = NVL((SELECT SUM(NVL(t.BEF_QTY, 0)) AS SUM_QTY FROM SYNWMS.STK_TRX t WHERE t.WH_CD = t.WH_CD AND t.ITEM_CD = t.ITEM_CD), 0),
           t.IN_QTY  = NVL((SELECT SUM(NVL(t.TRX_QTY, 0)) AS SUM_QTY FROM SYNWMS.STK_TRX t WHERE t.WH_CD = t.WH_CD AND t.ITEM_CD = t.ITEM_CD), 0)
     WHERE t.WH_CD = p_wh_cd;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MAKE_RPT_SNAP', SQLERRM);
      RAISE;
  END SP_MAKE_RPT_SNAP;

  -- ----------------------------------------------------------------------
  -- SP_MAKE_ARC_DAILY : 출고 아카이브 일마감 생성 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_MAKE_ARC_DAILY (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_ship_wgt             SYNWMS.OUT_SHIP.SHIP_WGT%TYPE;
    v_trk_no               SYNWMS.OUT_SHIP.TRK_NO%TYPE;
    v_area_cd              SYNWMS.MST_CUST.AREA_CD%TYPE;
    v_grade_cd             SYNWMS.MST_CUST.GRADE_CD%TYPE;
    r_row                  SYNARC.ARC_OUT_SHIP%ROWTYPE;
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

    -- 재처리 대상 판정
    IF v_cnt > 157 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 241 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 439 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 242 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 129, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 20);

    -- 마감 대상 조회
    FOR i IN 1 .. 2 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 4503;
    END LOOP;

    -- 집계 구간 산출
    IF v_cnt > 174 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 21 THEN
      RAISE_APPLICATION_ERROR(-20625, '집계 구간이 올바르지 않습니다.');
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 239 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 261 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 230 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 83 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    FOR i IN 1 .. 11 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 781;
    END LOOP;

    -- 집계 구간 산출
    IF v_cnt > 64 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 444 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 87 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 433 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 111 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 99, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 18);

    -- 구간 분할 처리
    IF v_cnt > 56 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 259 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 364, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 37);

    v_tmp_01 := TO_CHAR(SYSDATE - 292, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 35);

    -- 인터페이스 상태 갱신
    IF v_cnt > 225 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 179 THEN
      RAISE_APPLICATION_ERROR(-20943, '선행 배치가 완료되지 않았습니다.');
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 197 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 181 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 284 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 313 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 490 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    FOR i IN 1 .. 4 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 1105;
    END LOOP;

    -- ARCHIVE_SHIP 조인 적재
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
    SELECT /*+ LEADING(s) */
           SEQ_ARC.NEXTVAL AS ARC_SEQ,
           CASE WHEN s.CUST_CD = '10' THEN s.WH_CD ELSE ' ' END AS WH_CD,
           s.ORD_NO AS ORD_NO,
           NVL(s.SHIP_SEQ, 0) AS SHIP_SEQ,
           NVL(TRIM(s.ITEM_CD), '-') AS ITEM_CD,
           c.CUST_CD AS CUST_CD,
           CASE WHEN s.WH_CD = '10' THEN s.SHIP_QTY ELSE 0 END AS SHIP_QTY,
           NVL(TRIM(s.SHIP_YMD), '-') AS SHIP_YMD,
           SYSDATE AS ARC_DTM
      FROM SYNWMS.OUT_SHIP s
      LEFT JOIN SYNWMS.MST_CUST c
        ON (c.CUST_CD = s.CUST_CD)
     WHERE s.SHIP_YMD < TO_CHAR(SYSDATE - 180, 'YYYYMMDD');

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_MAKE_ARC_DAILY', SQLERRM);
      RAISE;
  END SP_MAKE_ARC_DAILY;

  -- ----------------------------------------------------------------------
  -- SP_SPLIT_RPT_STOCK : 일별 재고집계 재고 분할 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_SPLIT_RPT_STOCK (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_item_cd              SYNWMS.STK_ONHAND.ITEM_CD%TYPE;
    v_upd_dtm              SYNWMS.STK_ONHAND.UPD_DTM%TYPE;
    v_trx_tp_cd            SYNWMS.STK_TRX.TRX_TP_CD%TYPE;
    r_row                  SYNWMS.RPT_DAILY_STK%ROWTYPE;
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

    IF v_err_cnt > 16 THEN
      RAISE_APPLICATION_ERROR(-20332, '집계 구간이 올바르지 않습니다.');
    END IF;

    -- 예외 건 분류
    FOR i IN 1 .. 2 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 3369;
    END LOOP;

    -- 누적 카운터 갱신
    IF v_cnt > 335 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 262 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    v_tmp_05 := CASE WHEN v_cnt  > 161 THEN '72'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    v_tmp_01 := TO_CHAR(SYSDATE - 342, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 33);

    -- 임계치 비교
    FOR i IN 1 .. 6 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 366;
    END LOOP;

    v_tmp_03 := DECODE(SIGN(v_cnt - 12), 1, 'Y', 0, 'E', 'N');

    -- 처리 시작
    IF v_cnt > 224 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    g_step_no := g_step_no + 1;

    -- 예외 건 분류
    v_tmp_03 := CASE WHEN v_cnt  > 224 THEN '61'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 마감 대상 조회
    IF v_cnt > 58 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    v_tmp_03 := CASE WHEN v_cnt  > 365 THEN '88'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 후처리 플래그 설정
    v_tmp_03 := CASE WHEN v_cnt  > 44 THEN '48'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 처리 시작
    IF v_cnt > 58 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 324 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 191 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 51 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    g_step_no := g_step_no + 1;

    v_tmp_05 := TO_CHAR(SYSDATE - 117, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 4);

    -- 임계치 비교
    IF v_cnt > 133 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 474 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 218 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 9 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 144 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 237 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 410 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    FOR i IN 1 .. 11 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 6308;
    END LOOP;

    -- 구간 분할 처리
    IF v_cnt > 381 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 163 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 438 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 15 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 150 THEN
      RAISE_APPLICATION_ERROR(-20675, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 361 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 332 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 231 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 322 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    g_step_no := g_step_no + 1;

    -- 처리 시작
    IF v_cnt > 245 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 168 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 31 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    FOR i IN 1 .. 10 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 9029;
    END LOOP;

    IF v_err_cnt > 119 THEN
      RAISE_APPLICATION_ERROR(-20175, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 임계치 비교
    IF v_cnt > 278 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    FOR i IN 1 .. 9 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 801;
    END LOOP;

    -- 구간 분할 처리
    IF v_cnt > 364 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 4 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 184 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 426 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 347 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 183 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 26 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 154 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 100 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 175 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 168 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 137 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 313 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 63 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 238 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    IF v_cnt > 494 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    FOR i IN 1 .. 9 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 6026;
    END LOOP;

    -- 후처리 플래그 설정
    IF v_cnt > 74 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 28, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 7);

    -- 구간 분할 처리
    IF v_cnt > 138 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 65 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 438 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 158 THEN
      RAISE_APPLICATION_ERROR(-20142, '선행 배치가 완료되지 않았습니다.');
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 341, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 25);

    -- 선행 단계 완료 확인
    IF v_cnt > 322 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 78 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 131 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 172 THEN
      RAISE_APPLICATION_ERROR(-20435, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 434 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 84 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 311 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 1;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 원천 집계값으로 수량 재계산
    UPDATE SYNWMS.RPT_DAILY_STK t
       SET t.BGN_QTY = NVL((SELECT SUM(NVL(t.BEF_QTY, 0)) AS SUM_QTY FROM SYNWMS.STK_TRX t WHERE t.WH_CD = t.WH_CD AND t.ITEM_CD = t.ITEM_CD), 0),
           t.IN_QTY  = NVL((SELECT SUM(NVL(t.TRX_QTY, 0)) AS SUM_QTY FROM SYNWMS.STK_TRX t WHERE t.WH_CD = t.WH_CD AND t.ITEM_CD = t.ITEM_CD), 0)
     WHERE t.WH_CD = p_wh_cd;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_SPLIT_RPT_STOCK', SQLERRM);
      RAISE;
  END SP_SPLIT_RPT_STOCK;

  -- ----------------------------------------------------------------------
  -- FN_SUM_OUT_HIST : 출고할당 이력 집계 처리
  -- ----------------------------------------------------------------------
  FUNCTION FN_SUM_OUT_HIST (
    p_wh_cd IN SYNWMS.MST_WHOUSE.WH_CD%TYPE
  )
  RETURN NUMBER
  IS
    v_cust_cd              SYNWMS.OUT_ORDER_H.CUST_CD%TYPE;
    v_onhand_qty           SYNWMS.STK_ONHAND.ONHAND_QTY%TYPE;
    v_lot_no               SYNWMS.STK_ONHAND.LOT_NO%TYPE;
    v_ord_stat_cd          SYNWMS.OUT_ORDER_H.ORD_STAT_CD%TYPE;
    v_wh_cd                SYNWMS.OUT_ORDER_H.WH_CD%TYPE;
    v_ord_no               SYNWMS.OUT_ORDER_D.ORD_NO%TYPE;
    v_ord_qty              SYNWMS.OUT_ORDER_D.ORD_QTY%TYPE;
    v_line_stat_cd         SYNWMS.OUT_ORDER_D.LINE_STAT_CD%TYPE;
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

    -- 원천 집계값으로 수량 재계산
    UPDATE SYNWMS.OUT_ALLOC t
       SET t.ALLOC_QTY = NVL((SELECT SUM(NVL(d.ORD_QTY, 0)) AS SUM_QTY FROM SYNWMS.OUT_ORDER_D d WHERE d.WH_CD = t.WH_CD AND d.ORD_NO = t.ORD_NO), 0)
     WHERE t.WH_CD = p_wh_cd;

    -- 인터페이스 상태 갱신
    IF v_cnt > 169 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 288, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 20);

    -- 임계치 비교
    v_tmp_03 := CASE WHEN v_cnt  > 678 THEN '33'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 이관 대상 필터
    FOR i IN 1 .. 7 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 7523;
    END LOOP;

    -- 재처리 대상 판정
    IF v_cnt > 364 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 114, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 16);

    -- TRX_FROM_STOCK 조인 적재
    INSERT INTO SYNWMS.STK_TRX (
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
    SELECT
           SEQ_STK_TRX.NEXTVAL AS TRX_SEQ,
           NVL(TRIM(s.WH_CD), '-') AS WH_CD,
           s.LOC_CD AS LOC_CD,
           DECODE(r.ITEM_CD, 'Y', s.ITEM_CD, 'N', '*', s.ITEM_CD) AS ITEM_CD,
           NVL(TRIM(s.LOT_NO), '-') AS LOT_NO,
           '10' AS TRX_TP_CD,
           MAX(NVL(r.RCV_QTY, 0)) AS TRX_QTY,
           SUM(NVL(s.ONHAND_QTY, 0)) AS BEF_QTY,
           SUM(NVL(s.ONHAND_QTY, 0)) AS AFT_QTY,
           SUM(NVL(s.WGT_TOT, 0)) AS TRX_WGT,
           CASE WHEN s.ITEM_CD = '10' THEN s.LAST_TRX_YMD ELSE ' ' END AS TRX_YMD,
           CASE WHEN s.LOC_CD = '10' THEN r.ORD_NO ELSE ' ' END AS REF_NO
      FROM SYNWMS.STK_ONHAND s
      LEFT JOIN SYNWMS.INB_RESULT r
        ON (r.WH_CD = s.WH_CD AND r.ITEM_CD = s.ITEM_CD AND r.LOT_NO = s.LOT_NO)
     WHERE s.ONHAND_QTY > 0
     GROUP BY s.WH_CD, s.LOC_CD, s.ITEM_CD, s.LOT_NO, s.LAST_TRX_YMD, r.ORD_NO;

    COMMIT;
    RETURN v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'FN_SUM_OUT_HIST', SQLERRM);
      RAISE;
  END FN_SUM_OUT_HIST;

  -- ----------------------------------------------------------------------
  -- FN_CLEAN_INB_ORDER : 입고실적 전표 정리 처리
  -- ----------------------------------------------------------------------
  FUNCTION FN_CLEAN_INB_ORDER
  RETURN NUMBER
  IS
    v_ord_ymd              SYNWMS.INB_ORDER_H.ORD_YMD%TYPE;
    v_due_ymd              SYNWMS.INB_ORDER_D.DUE_YMD%TYPE;
    v_val_02               VARCHAR2(30);
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
    v_tmp_03 := CASE WHEN v_cnt  > 847 THEN '98'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 인터페이스 상태 갱신
    v_tmp_01 := CASE WHEN v_cnt  > 712 THEN '41'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 선행 단계 완료 확인
    v_tmp_01 := CASE WHEN v_cnt  > 412 THEN '93'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 배치 단위 조정
    g_step_no := g_step_no + 1;

    COMMIT;
    RETURN v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'FN_CLEAN_INB_ORDER', SQLERRM);
      RAISE;
  END FN_CLEAN_INB_ORDER;

END PKG_MST_003;
/
