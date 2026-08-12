-- ==========================================================================
-- 패키지 : SYNWMS.PKG_MST_003
-- 설명   : Tier 1 합성 패키지 - MST 영역 배치 처리
-- 난이도 : Tier 1
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_MST_003 AS

  -- 출고 인터페이스 계획 동기화 처리
  FUNCTION FN_SYNC_IFC_PLAN (
    p_base_ymd IN VARCHAR2
  )
  RETURN NUMBER;

  -- 품목 기준정보 스냅샷 반영 처리
  PROCEDURE SP_APPLY_MST_SNAP (
    p_proc_cnt OUT NUMBER
  );

  -- 입고실적 이력 산출 처리
  PROCEDURE SP_CALC_INB_HIST (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  );

  -- 재고이동 실적 집계 처리
  PROCEDURE SP_SUM_STK_RESULT (
    p_proc_cnt OUT NUMBER
  );

END PKG_MST_003;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_MST_003 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_MST_003';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- FN_SYNC_IFC_PLAN : 출고 인터페이스 계획 동기화 처리
  -- ----------------------------------------------------------------------
  FUNCTION FN_SYNC_IFC_PLAN (
    p_base_ymd IN VARCHAR2
  )
  RETURN NUMBER
  IS
    v_ord_no               SYNWMS.OUT_SHIP.ORD_NO%TYPE;
    v_val_01               VARCHAR2(30);
    v_val_02               NUMBER(13,3);
    v_val_03               VARCHAR2(30);
    v_val_04               NUMBER(13,3);
    v_val_05               NUMBER;
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

    -- 처리 시작
    IF v_cnt > 351 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_05 := TO_CHAR(SYSDATE - 57, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 22);

    -- 임계치 비교
    v_tmp_01 := CASE WHEN v_cnt  > 806 THEN '82'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 처리 시작
    v_tmp_01 := CASE WHEN v_cnt  > 640 THEN '63'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    v_tmp_03 := TO_CHAR(SYSDATE - 320, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 29);

    -- 대상 건수 확인
    v_tmp_03 := CASE WHEN v_cnt  > 169 THEN '60'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 집계 구간 산출
    g_step_no := g_step_no + 1;

    v_tmp_03 := DECODE(SIGN(v_cnt - 7), 1, 'Y', 0, 'E', 'N');

    -- 구간 분할 처리
    IF v_cnt > 445 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 169 THEN
      RAISE_APPLICATION_ERROR(-20358, '선행 배치가 완료되지 않았습니다.');
    END IF;

    -- 예외 건 분류
    IF v_cnt > 438 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 184 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 5;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 313 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 8 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 165, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 32);

    -- 마감 대상 조회
    FOR i IN 1 .. 11 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 3235;
    END LOOP;

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

    -- 보존기간 경과 데이터 삭제
    DELETE FROM SYNIF.IF_ORDER_SND t
     WHERE t.IF_YMD < p_base_ymd
       AND t.IF_STAT_CD = '99';

    -- ARCHIVE_SHIP 단순 적재
    INSERT INTO SYNARC.ARC_OUT_SHIP (
           WH_CD,
           ORD_NO,
           SHIP_SEQ,
           ITEM_CD,
           SHIP_QTY,
           SHIP_YMD
         )
    SELECT
           s.WH_CD AS WH_CD,
           s.ORD_NO AS ORD_NO,
           s.SHIP_SEQ AS SHIP_SEQ,
           s.ITEM_CD AS ITEM_CD,
           s.SHIP_QTY AS SHIP_QTY,
           s.SHIP_YMD AS SHIP_YMD
      FROM SYNWMS.OUT_SHIP s;

    COMMIT;
    RETURN v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'FN_SYNC_IFC_PLAN', SQLERRM);
      RAISE;
  END FN_SYNC_IFC_PLAN;

  -- ----------------------------------------------------------------------
  -- SP_APPLY_MST_SNAP : 품목 기준정보 스냅샷 반영 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_APPLY_MST_SNAP (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_item_cd              SYNIF.IF_ITEM_RCV.ITEM_CD%TYPE;
    v_if_seq               SYNIF.IF_ITEM_RCV.IF_SEQ%TYPE;
    v_snd_sys_cd           SYNIF.IF_ITEM_RCV.SND_SYS_CD%TYPE;
    v_if_ymd               SYNIF.IF_ITEM_RCV.IF_YMD%TYPE;
    v_item_nm              SYNIF.IF_ITEM_RCV.ITEM_NM%TYPE;
    v_rcv_dtm              SYNIF.IF_ITEM_RCV.RCV_DTM%TYPE;
    v_unit_wgt             SYNIF.IF_ITEM_RCV.UNIT_WGT%TYPE;
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

    -- 이관 대상 필터
    FOR i IN 1 .. 10 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 1952;
    END LOOP;

    -- 예외 건 분류
    IF v_cnt > 461 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    v_tmp_03 := CASE WHEN v_cnt  > 661 THEN '76'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    IF v_err_cnt > 161 THEN
      RAISE_APPLICATION_ERROR(-20046, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    v_tmp_05 := DECODE(SIGN(v_cnt - 10), 1, 'Y', 0, 'E', 'N');

    -- 이관 대상 필터
    v_tmp_01 := CASE WHEN v_cnt  > 358 THEN '26'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 대상 건수 확인
    v_tmp_03 := CASE WHEN v_cnt  > 407 THEN '30'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 누적 카운터 갱신
    FOR i IN 1 .. 7 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 8636;
    END LOOP;

    -- 예외 건 분류
    IF v_cnt > 113 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 455 AND v_tmp_05 IS NOT NULL THEN
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

    -- 예외 건 분류
    v_tmp_05 := CASE WHEN v_cnt  > 109 THEN '30'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 구간 분할 처리
    g_step_no := g_step_no + 1;

    -- 예외 건 분류
    v_tmp_01 := CASE WHEN v_cnt  > 465 THEN '56'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 배치 단위 조정
    v_tmp_05 := CASE WHEN v_cnt  > 608 THEN '95'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 임계치 비교
    FOR i IN 1 .. 2 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 8858;
    END LOOP;

    -- 대상 건수 확인
    v_tmp_05 := CASE WHEN v_cnt  > 741 THEN '37'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    v_tmp_03 := TO_CHAR(SYSDATE - 107, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 14);

    -- 이관 대상 필터
    IF v_cnt > 461 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
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

    -- 이관 대상 필터
    IF v_cnt > 442 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    g_step_no := g_step_no + 1;

    -- 처리 종료
    IF v_cnt > 312 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    IF v_cnt > 475 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 7;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 21 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 이관 대상 필터
    FOR i IN 1 .. 4 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 1299;
    END LOOP;

    -- 구간 분할 처리
    IF v_cnt > 127 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 7;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 474 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    FOR i IN 1 .. 6 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 8242;
    END LOOP;

    -- 처리 종료
    g_step_no := g_step_no + 1;

    -- 구간 분할 처리
    IF v_cnt > 273 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
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

    -- 마감 대상 조회
    IF v_cnt > 358 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    IF v_cnt > 220 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 3;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 373 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 495 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 21 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 148 THEN
      RAISE_APPLICATION_ERROR(-20182, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 임계치 비교
    IF v_cnt > 127 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 117 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 10 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 350 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 72 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    IF v_cnt > 211 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    FOR i IN 1 .. 2 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 1791;
    END LOOP;

    -- 인터페이스 상태 갱신
    IF v_cnt > 499 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 7;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 33 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 255 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    IF v_cnt > 393 AND v_tmp_05 IS NOT NULL THEN
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

    -- 원천 집계값으로 수량 재계산
    UPDATE SYNWMS.MST_ITEM t
       SET t.UNIT_WGT = NVL((SELECT SUM(NVL(r.UNIT_WGT, 0)) AS SUM_QTY FROM SYNIF.IF_ITEM_RCV r WHERE r.ITEM_CD = t.ITEM_CD), 0),
           t.BOX_QTY  = NVL((SELECT SUM(NVL(r.BOX_QTY, 0)) AS SUM_QTY FROM SYNIF.IF_ITEM_RCV r WHERE r.ITEM_CD = t.ITEM_CD), 0),
           t.UPD_DTM  = SYSDATE;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_APPLY_MST_SNAP', SQLERRM);
      RAISE;
  END SP_APPLY_MST_SNAP;

  -- ----------------------------------------------------------------------
  -- SP_CALC_INB_HIST : 입고실적 이력 산출 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CALC_INB_HIST (
    p_wh_cd    IN SYNWMS.MST_WHOUSE.WH_CD%TYPE,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_item_grp_cd          SYNWMS.MST_ITEM.ITEM_GRP_CD%TYPE;
    v_unit_wgt             SYNWMS.MST_ITEM.UNIT_WGT%TYPE;
    v_ord_qty              SYNWMS.INB_ORDER_D.ORD_QTY%TYPE;
    v_ord_stat_cd          SYNWMS.INB_ORDER_H.ORD_STAT_CD%TYPE;
    v_item_nm              SYNWMS.MST_ITEM.ITEM_NM%TYPE;
    v_ord_ymd              SYNWMS.INB_ORDER_H.ORD_YMD%TYPE;
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
  BEGIN

    v_tmp_05 := TO_CHAR(SYSDATE - 99, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 18);

    -- 집계 구간 산출
    v_tmp_01 := CASE WHEN v_cnt  > 383 THEN '64'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 구간 분할 처리
    FOR i IN 1 .. 8 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 8417;
    END LOOP;

    -- 재처리 대상 판정
    IF v_cnt > 21 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    FOR i IN 1 .. 5 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 1919;
    END LOOP;

    -- 구간 분할 처리
    IF v_cnt > 220 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    v_tmp_03 := CASE WHEN v_cnt  > 799 THEN '98'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 이관 대상 필터
    g_step_no := g_step_no + 1;

    -- 누적 카운터 갱신
    v_tmp_03 := CASE WHEN v_cnt  > 243 THEN '63'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 예외 건 분류
    g_step_no := g_step_no + 1;

    v_tmp_05 := DECODE(SIGN(v_cnt - 32), 1, 'Y', 0, 'E', 'N');

    -- 예외 건 분류
    FOR i IN 1 .. 10 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 1287;
    END LOOP;

    -- 대상 건수 확인
    IF v_cnt > 425 AND v_tmp_03 IS NOT NULL THEN
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

    -- 선행 단계 완료 확인
    v_tmp_05 := CASE WHEN v_cnt  > 654 THEN '97'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 예외 건 분류
    IF v_cnt > 426 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 3;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    v_tmp_03 := CASE WHEN v_cnt  > 791 THEN '16'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 예외 건 분류
    IF v_cnt > 31 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    v_tmp_03 := CASE WHEN v_cnt  > 664 THEN '20'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 선행 단계 완료 확인
    IF v_cnt > 30 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    IF v_cnt > 379 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 19 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 구간 분할 처리
    FOR i IN 1 .. 3 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 8855;
    END LOOP;

    -- 누적 카운터 갱신
    v_tmp_05 := CASE WHEN v_cnt  > 788 THEN '59'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 예외 건 분류
    IF v_cnt > 134 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 7;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    FOR i IN 1 .. 7 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 630;
    END LOOP;

    -- 누적 카운터 갱신
    IF v_cnt > 470 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 4;
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

    -- 누적 카운터 갱신
    IF v_cnt > 410 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 7 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 255 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 94 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 270 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 4;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 435 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    IF v_cnt > 161 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 87 THEN
      RAISE_APPLICATION_ERROR(-20643, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 322 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 2;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 137 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 87 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 4;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 78 THEN
      RAISE_APPLICATION_ERROR(-20440, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 58 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 426 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 7;
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

    -- 원천 집계값으로 수량 재계산
    UPDATE SYNWMS.INB_RESULT t
       SET t.RCV_QTY = NVL((SELECT SUM(NVL(d.ORD_QTY, 0)) AS SUM_QTY FROM SYNWMS.INB_ORDER_D d WHERE d.WH_CD = t.WH_CD AND d.ORD_NO = t.ORD_NO), 0),
           t.RJT_QTY = NVL((SELECT SUM(NVL(d.LINE_NO, 0)) AS SUM_QTY FROM SYNWMS.INB_ORDER_D d WHERE d.WH_CD = t.WH_CD AND d.ORD_NO = t.ORD_NO), 0)
     WHERE t.WH_CD = p_wh_cd;

    -- INB_ORDER_FROM_IF 단순 적재
    INSERT INTO SYNWMS.INB_ORDER_D (
           WH_CD,
           ORD_NO,
           LINE_NO,
           ORD_QTY,
           DUE_YMD
         )
    SELECT
           r.WH_CD AS WH_CD,
           r.ORD_NO AS ORD_NO,
           r.LINE_NO AS LINE_NO,
           r.ORD_QTY AS ORD_QTY,
           r.DUE_YMD AS DUE_YMD
      FROM SYNIF.IF_ORDER_RCV r;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CALC_INB_HIST', SQLERRM);
      RAISE;
  END SP_CALC_INB_HIST;

  -- ----------------------------------------------------------------------
  -- SP_SUM_STK_RESULT : 재고이동 실적 집계 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_SUM_STK_RESULT (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_lot_no               SYNWMS.INB_RESULT.LOT_NO%TYPE;
    v_rcv_seq              SYNWMS.INB_RESULT.RCV_SEQ%TYPE;
    v_rcv_qty              SYNWMS.INB_RESULT.RCV_QTY%TYPE;
    v_rjt_qty              SYNWMS.INB_RESULT.RJT_QTY%TYPE;
    v_alloc_qty            SYNWMS.STK_ONHAND.ALLOC_QTY%TYPE;
    v_onhand_qty           SYNWMS.STK_ONHAND.ONHAND_QTY%TYPE;
    v_wh_cd                SYNWMS.INB_RESULT.WH_CD%TYPE;
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
  BEGIN

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
    SELECT /*+ LEADING(s) */
           SEQ_STK_TRX.NEXTVAL AS TRX_SEQ,
           NVL(TRIM(s.WH_CD), '-') AS WH_CD,
           s.LOC_CD AS LOC_CD,
           DECODE(r.WH_CD, 'Y', s.ITEM_CD, 'N', '*', s.ITEM_CD) AS ITEM_CD,
           CASE WHEN r.ITEM_CD = '10' THEN s.LOT_NO ELSE ' ' END AS LOT_NO,
           '10' AS TRX_TP_CD,
           CASE WHEN r.LOC_CD = '10' THEN r.RCV_QTY ELSE 0 END AS TRX_QTY,
           NVL(s.ONHAND_QTY, 0) AS BEF_QTY,
           CASE WHEN r.WH_CD = '10' THEN s.ONHAND_QTY ELSE 0 END AS AFT_QTY,
           CASE WHEN s.ITEM_CD = '10' THEN s.WGT_TOT ELSE 0 END AS TRX_WGT,
           s.LAST_TRX_YMD AS TRX_YMD,
           NVL(TRIM(r.ORD_NO), '-') AS REF_NO
      FROM SYNWMS.STK_ONHAND s
      LEFT JOIN SYNWMS.INB_RESULT r
        ON (r.WH_CD = s.WH_CD AND r.ITEM_CD = s.ITEM_CD AND r.LOT_NO = s.LOT_NO)
     WHERE s.ONHAND_QTY > 0;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_SUM_STK_RESULT', SQLERRM);
      RAISE;
  END SP_SUM_STK_RESULT;

END PKG_MST_003;
/
