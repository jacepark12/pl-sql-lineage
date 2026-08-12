-- ==========================================================================
-- 패키지 : SYNWMS.PKG_COMMON
-- 설명   : 배치 공통 유틸리티 (로그 기록, 기준일자 산출)
-- 난이도 : Tier 0
-- 주의   : 합성 코퍼스 자동 생성 파일. 실제 업무 로직이 아닙니다.
-- ==========================================================================

CREATE OR REPLACE PACKAGE SYNWMS.PKG_COMMON AS

  -- 오류 로그 기록
  PROCEDURE p_log_error (
    p_job_id  IN VARCHAR2,
    p_step_nm IN VARCHAR2,
    p_err_msg IN VARCHAR2
  );

  -- 기준일자 산출
  FUNCTION fn_base_ymd (
    p_offset IN NUMBER
  )
  RETURN VARCHAR2;

END PKG_COMMON;
/

CREATE OR REPLACE PACKAGE BODY SYNWMS.PKG_COMMON AS

  -- 로그는 본 트랜잭션과 분리해 기록한다.
  PROCEDURE p_log_error (
    p_job_id  IN VARCHAR2,
    p_step_nm IN VARCHAR2,
    p_err_msg IN VARCHAR2
  )
  IS
    PRAGMA AUTONOMOUS_TRANSACTION;
  BEGIN
    INSERT INTO SYNARC.ARC_JOB_LOG (
           LOG_SEQ,
           JOB_ID,
           JOB_NM,
           STEP_NO,
           ERR_MSG,
           STA_DTM
         )
    VALUES (
           SYNWMS.SEQ_JOB_LOG.NEXTVAL,
           p_job_id,
           p_step_nm,
           0,
           SUBSTR(p_err_msg, 1, 2000),
           SYSDATE
         );
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN
      ROLLBACK;
  END p_log_error;

  FUNCTION fn_base_ymd (
    p_offset IN NUMBER
  )
  RETURN VARCHAR2
  IS
  BEGIN
    RETURN TO_CHAR(TRUNC(SYSDATE) - NVL(p_offset, 0), 'YYYYMMDD');
  END fn_base_ymd;

END PKG_COMMON;
/
