-- ==========================================================================
-- 패키지 : SYNWMS.PKG_RPT_005
-- 설명   : Tier 2 합성 패키지 - RPT 영역 배치 처리
-- 난이도 : Tier 2
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_RPT_005 AS

  -- 재고이동 스냅샷 동기화 처리
  PROCEDURE SP_SYNC_STK_SNAP (
    p_trx_seq  IN SYNWMS.STK_TRX.TRX_SEQ%TYPE,
    p_proc_cnt OUT NUMBER
  );

  -- 품목 기준정보 실적 마감 처리
  PROCEDURE SP_CLOSE_MST_RESULT (
    p_item_cd  IN SYNWMS.MST_ITEM.ITEM_CD%TYPE,
    p_proc_cnt OUT NUMBER
  );

  -- 재고 전표 점검 처리
  PROCEDURE SP_CHECK_STK_ORDER (
    p_proc_cnt OUT NUMBER
  );

  -- 업무 실적 정리 처리
  FUNCTION FN_CLEAN_WMS_RESULT (
    p_vend_cd IN SYNWMS.MST_VENDOR.VEND_CD%TYPE
  )
  RETURN NUMBER;

END PKG_RPT_005;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_RPT_005 AS

  g_job_id    VARCHAR2(30) := 'JOB_PKG_RPT_005';
  g_step_no   NUMBER(5)    := 0;

  -- ----------------------------------------------------------------------
  -- SP_SYNC_STK_SNAP : 재고이동 스냅샷 동기화 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_SYNC_STK_SNAP (
    p_trx_seq  IN SYNWMS.STK_TRX.TRX_SEQ%TYPE,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_rcv_ymd              SYNWMS.INB_RESULT.RCV_YMD%TYPE;
    v_rcv_seq              SYNWMS.INB_RESULT.RCV_SEQ%TYPE;
    v_avail_qty            SYNWMS.STK_ONHAND.AVAIL_QTY%TYPE;
    v_loc_cd               SYNWMS.INB_RESULT.LOC_CD%TYPE;
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

    v_tmp_01 := TO_CHAR(SYSDATE - 79, 'YYYYMMDD');
    v_tmp_04 := TRUNC(NVL(v_cnt, 0) / 20);

    -- 마감 대상 조회
    IF v_cnt > 50 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 13 THEN
      RAISE_APPLICATION_ERROR(-20088, '집계 구간이 올바르지 않습니다.');
    END IF;

    v_tmp_03 := TO_CHAR(SYSDATE - 264, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 27);

    -- 처리 시작
    v_tmp_03 := CASE WHEN v_cnt  > 265 THEN '75'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 상태 코드 갱신
    UPDATE SYNWMS.STK_TRX t
       SET t.REF_NO = '90'
     WHERE t.TRX_SEQ = p_trx_seq;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_SYNC_STK_SNAP', SQLERRM);
      RAISE;
  END SP_SYNC_STK_SNAP;

  -- ----------------------------------------------------------------------
  -- SP_CLOSE_MST_RESULT : 품목 기준정보 실적 마감 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CLOSE_MST_RESULT (
    p_item_cd  IN SYNWMS.MST_ITEM.ITEM_CD%TYPE,
    p_proc_cnt OUT NUMBER
  )
  IS
    v_box_qty              SYNIF.IF_ITEM_RCV.BOX_QTY%TYPE;
    v_val_01               VARCHAR2(30);
    v_val_02               DATE;
    v_val_03               NUMBER(13,3);
    v_val_04               NUMBER;
    v_val_05               VARCHAR2(200);
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

    v_tmp_01 := DECODE(SIGN(v_cnt - 27), 1, 'Y', 0, 'E', 'N');

    -- 선행 단계 완료 확인
    IF v_cnt > 445 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 103 THEN
      RAISE_APPLICATION_ERROR(-20158, '처리 대상이 임계치를 초과했습니다.');
    END IF;

    -- 처리 종료
    g_step_no := g_step_no + 1;

    v_tmp_03 := TO_CHAR(SYSDATE - 194, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 33);

    -- 예외 건 분류
    g_step_no := g_step_no + 1;

    -- 임계치 비교
    IF v_cnt > 33 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 1 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    v_tmp_05 := CASE WHEN v_cnt  > 409 THEN '89'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 구간 분할 처리
    IF v_cnt > 177 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 14 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 종료
    IF v_cnt > 389 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 3;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    IF v_cnt > 319 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    v_tmp_03 := CASE WHEN v_cnt  > 364 THEN '29'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 예외 건 분류
    IF v_cnt > 160 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 배치 단위 조정
    IF v_cnt > 325 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 재처리 대상 판정
    FOR i IN 1 .. 8 LOOP
      v_tmp_02 := NVL(v_tmp_02, 0) + i;
      EXIT WHEN v_tmp_02 > 5208;
    END LOOP;

    -- 누적 카운터 갱신
    IF v_cnt > 122 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 4;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    v_tmp_01 := TO_CHAR(SYSDATE - 298, 'YYYYMMDD');
    v_tmp_00 := TRUNC(NVL(v_cnt, 0) / 10);

    -- 처리 종료
    v_tmp_03 := CASE WHEN v_cnt  > 193 THEN '29'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 재처리 대상 판정
    IF v_cnt > 446 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 8;
    ELSIF v_err_cnt > 5 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    FOR i IN 1 .. 8 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 3119;
    END LOOP;

    -- 구간 분할 처리
    FOR i IN 1 .. 2 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 4484;
    END LOOP;

    -- 이관 대상 필터
    IF v_cnt > 73 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 13 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 처리 시작
    FOR i IN 1 .. 3 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 1018;
    END LOOP;

    -- 배치 단위 조정
    IF v_cnt > 127 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 예외 건 분류
    IF v_cnt > 312 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_04, 0) + 1;
    ELSIF v_err_cnt > 17 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 29 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 2;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 198 THEN
      RAISE_APPLICATION_ERROR(-20403, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 493 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 6;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 482 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 8;
    ELSIF v_err_cnt > 3 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 인터페이스 상태 갱신
    g_step_no := g_step_no + 1;

    -- 임계치 비교
    v_tmp_03 := CASE WHEN v_cnt  > 655 THEN '14'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 후처리 플래그 설정
    IF v_cnt > 387 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_04, 0) + 5;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    IF v_err_cnt > 153 THEN
      RAISE_APPLICATION_ERROR(-20796, '기준 정보가 존재하지 않습니다.');
    END IF;

    -- 임계치 비교
    IF v_cnt > 191 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_02, 0) + 6;
    ELSIF v_err_cnt > 18 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    g_step_no := g_step_no + 1;

    -- 선행 단계 완료 확인
    IF v_cnt > 384 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 7;
    ELSIF v_err_cnt > 12 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 후처리 플래그 설정
    IF v_cnt > 69 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_00, 0) + 8;
    ELSIF v_err_cnt > 6 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 상태 코드 갱신
    UPDATE SYNWMS.MST_ITEM t
       SET t.REG_DTM = SYSDATE
     WHERE t.ITEM_CD = p_item_cd;

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CLOSE_MST_RESULT', SQLERRM);
      RAISE;
  END SP_CLOSE_MST_RESULT;

  -- ----------------------------------------------------------------------
  -- SP_CHECK_STK_ORDER : 재고 전표 점검 처리
  -- ----------------------------------------------------------------------
  PROCEDURE SP_CHECK_STK_ORDER (
    p_proc_cnt OUT NUMBER
  )
  IS
    v_wh_cd                SYNWMS.INB_RESULT.WH_CD%TYPE;
    v_reg_dtm              SYNWMS.MST_ITEM.REG_DTM%TYPE;
    v_item_nm              SYNWMS.MST_ITEM.ITEM_NM%TYPE;
    v_ord_no               SYNWMS.INB_RESULT.ORD_NO%TYPE;
    v_val_04               VARCHAR2(30);
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
    g_step_no := g_step_no + 1;

    v_tmp_01 := TO_CHAR(SYSDATE - 365, 'YYYYMMDD');
    v_tmp_02 := TRUNC(NVL(v_cnt, 0) / 16);

    -- 후처리 플래그 설정
    FOR i IN 1 .. 10 LOOP
      v_tmp_00 := NVL(v_tmp_00, 0) + i;
      EXIT WHEN v_tmp_00 > 5332;
    END LOOP;

    -- 선행 단계 완료 확인
    IF v_cnt > 28 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 16 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 대상 건수 확인
    IF v_cnt > 378 AND v_tmp_03 IS NOT NULL THEN
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

    -- 배치 단위 조정
    v_tmp_05 := CASE WHEN v_cnt  > 532 THEN '44'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 대상 건수 확인
    v_tmp_01 := CASE WHEN v_cnt  > 416 THEN '62'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 인터페이스 상태 갱신
    IF v_cnt > 24 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_04 := NVL(v_tmp_02, 0) + 7;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    v_tmp_05 := CASE WHEN v_cnt  > 697 THEN '46'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 임계치 비교
    IF v_cnt > 423 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_00, 0) + 1;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 마감 대상 조회
    IF v_cnt > 236 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 15 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 임계치 비교
    IF v_cnt > 380 AND v_tmp_05 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 2;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 누적 카운터 갱신
    FOR i IN 1 .. 6 LOOP
      v_tmp_04 := NVL(v_tmp_04, 0) + i;
      EXIT WHEN v_tmp_04 > 3779;
    END LOOP;

    -- 구간 분할 처리
    IF v_cnt > 190 AND v_tmp_01 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 2 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 선행 단계 완료 확인
    v_tmp_03 := CASE WHEN v_cnt  > 768 THEN '48'
                    WHEN v_cnt  = 0 THEN '00'
                    WHEN v_err_cnt > 0 THEN '90'
                    ELSE '99'
               END;

    -- 집계 구간 산출
    IF v_cnt > 449 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_00 := NVL(v_tmp_02, 0) + 5;
    ELSIF v_err_cnt > 9 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

    -- 집계 구간 산출
    IF v_cnt > 490 AND v_tmp_03 IS NOT NULL THEN
      g_step_no := g_step_no + 1;
      v_tmp_02 := NVL(v_tmp_04, 0) + 6;
    ELSIF v_err_cnt > 11 THEN
      v_err_cnt := v_err_cnt + 1;
    ELSE
      g_step_no := g_step_no + 1;
    END IF;

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

    COMMIT;
    p_proc_cnt := v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'SP_CHECK_STK_ORDER', SQLERRM);
      RAISE;
  END SP_CHECK_STK_ORDER;

  -- ----------------------------------------------------------------------
  -- FN_CLEAN_WMS_RESULT : 업무 실적 정리 처리
  -- ----------------------------------------------------------------------
  FUNCTION FN_CLEAN_WMS_RESULT (
    p_vend_cd IN SYNWMS.MST_VENDOR.VEND_CD%TYPE
  )
  RETURN NUMBER
  IS
    v_grade_cd             SYNIF.IF_CUST_RCV.GRADE_CD%TYPE;
    v_rcv_dtm              SYNIF.IF_CUST_RCV.RCV_DTM%TYPE;
    v_val_02               VARCHAR2(30);
    v_val_03               VARCHAR2(30);
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

    -- CUST_MASTER_FROM_IF UPSERT
    MERGE INTO SYNWMS.MST_CUST t
    USING (
          SELECT
                 r.CUST_CD AS CUST_CD,
                 r.CUST_NM AS CUST_NM,
                 r.AREA_CD AS AREA_CD,
                 r.GRADE_CD AS GRADE_CD,
                 CASE WHEN r.USE_YN = '10' THEN r.USE_YN ELSE ' ' END AS USE_YN
            FROM SYNIF.IF_CUST_RCV r
           WHERE r.IF_STAT_CD = '10'
         ) q
        ON (t.CUST_CD = q.CUST_CD)
    WHEN MATCHED THEN
      UPDATE SET
        t.CUST_NM  = q.CUST_NM,
        t.AREA_CD  = q.AREA_CD,
        t.GRADE_CD = q.GRADE_CD,
        t.USE_YN   = q.USE_YN
    WHEN NOT MATCHED THEN
      INSERT (
           CUST_CD,
           CUST_NM,
           AREA_CD,
           GRADE_CD,
           USE_YN
         )
      VALUES (
           q.CUST_CD,
           q.CUST_NM,
           q.AREA_CD,
           q.GRADE_CD,
           q.USE_YN
         );

    -- 상태 코드 갱신
    UPDATE SYNWMS.MST_VENDOR t
       SET t.USE_YN = '90'
     WHERE t.VEND_CD = p_vend_cd;

    COMMIT;
    RETURN v_cnt;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      NULL;
    WHEN OTHERS THEN
      ROLLBACK;
      SYNWMS.PKG_COMMON.p_log_error(g_job_id, 'FN_CLEAN_WMS_RESULT', SQLERRM);
      RAISE;
  END FN_CLEAN_WMS_RESULT;

END PKG_RPT_005;
/
