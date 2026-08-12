DECLARE
  TYPE t_row_rec IS RECORD (
    WH_CD     VARCHAR2(10),
    ITEM_CD   VARCHAR2(30),
    SHIP_QTY  NUMBER(13,3)
  );
  TYPE t_row_tab IS TABLE OF t_row_rec INDEX BY PLS_INTEGER;
  t_rows  t_row_tab;
BEGIN
  SELECT s.WH_CD    AS WH_CD,
         s.ITEM_CD  AS ITEM_CD,
         s.SHIP_QTY AS SHIP_QTY
    BULK COLLECT INTO t_rows
    FROM SYNWMS.OUT_SHIP s;

  FORALL i IN 1 .. t_rows.COUNT
    INSERT INTO SYNARC.ARC_OUT_SHIP (
           ARC_SEQ,
           WH_CD,
           ITEM_CD,
           SHIP_QTY
         )
    VALUES (
           SEQ_ARC.NEXTVAL,
           t_rows(i).WH_CD,
           t_rows(i).ITEM_CD,
           t_rows(i).SHIP_QTY
         );
END;
/
