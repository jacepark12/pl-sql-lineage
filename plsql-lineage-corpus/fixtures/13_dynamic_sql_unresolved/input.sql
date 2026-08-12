DECLARE
  v_tab_nm  VARCHAR2(61);
  v_sql     VARCHAR2(4000);
BEGIN
  v_tab_nm := 'SYNWMS.' || p_tab_sfx;
  v_sql := 'UPDATE ' || v_tab_nm
        || '   SET UPD_DTM = SYSDATE'
        || ' WHERE WH_CD = :1';
  EXECUTE IMMEDIATE v_sql USING p_wh_cd;
END;
/
