INSERT INTO SYNWMS.INB_RESULT (
       WH_CD,
       ORD_NO,
       LINE_NO,
       RCV_SEQ,
       ITEM_CD,
       RCV_QTY,
       RCV_WGT
     )
SELECT d.WH_CD,
       d.ORD_NO,
       d.LINE_NO,
       1,
       i.ITEM_CD,
       d.ORD_QTY,
       i.UNIT_WGT
  FROM SYNWMS.INB_ORDER_D d
  JOIN SYNWMS.INB_ORDER_H h
    ON (h.WH_CD = d.WH_CD AND h.ORD_NO = d.ORD_NO)
  JOIN SYNWMS.MST_ITEM i
    ON (i.ITEM_CD = d.ITEM_CD)
 WHERE h.ORD_STAT_CD <> '99';
