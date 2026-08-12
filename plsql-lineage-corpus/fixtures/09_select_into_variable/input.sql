DECLARE
  v_sum_qty  NUMBER(15,3);
BEGIN
  SELECT NVL(SUM(s.ONHAND_QTY), 0)
    INTO v_sum_qty
    FROM SYNWMS.STK_ONHAND s
   WHERE s.WH_CD = 'WH01';

  INSERT INTO SYNIF.IF_STOCK_SND (
         IF_SEQ,
         WH_CD,
         ONHAND_QTY
       )
  VALUES (
         SEQ_IF_SND.NEXTVAL,
         'WH01',
         v_sum_qty
       );
END;
/
