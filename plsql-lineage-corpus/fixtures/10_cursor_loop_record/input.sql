DECLARE
  CURSOR c_rcv IS
    SELECT r.WH_CD    AS WH_CD,
           r.ITEM_CD  AS ITEM_CD,
           r.RCV_QTY  AS RCV_QTY
      FROM SYNWMS.INB_RESULT r
     WHERE r.RCV_QTY > 0;
BEGIN
  FOR rec IN c_rcv LOOP
    INSERT INTO SYNWMS.STK_TRX (
           TRX_SEQ,
           WH_CD,
           ITEM_CD,
           TRX_QTY
         )
    VALUES (
           SEQ_STK_TRX.NEXTVAL,
           rec.WH_CD,
           rec.ITEM_CD,
           rec.RCV_QTY
         );
  END LOOP;
END;
/
