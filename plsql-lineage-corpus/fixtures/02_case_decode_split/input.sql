INSERT INTO SYNWMS.STK_ONHAND (
       WH_CD,
       LOC_CD,
       ITEM_CD,
       LOT_NO,
       ONHAND_QTY,
       AVAIL_QTY
     )
SELECT r.WH_CD,
       r.LOC_CD,
       r.ITEM_CD,
       r.LOT_NO,
       CASE WHEN r.RCV_YMD IS NULL THEN 0 ELSE r.RCV_QTY END,
       DECODE(r.WORK_ID, 'BATCH', r.RCV_QTY, 0)
  FROM SYNWMS.INB_RESULT r;
