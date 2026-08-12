INSERT INTO SYNWMS.OUT_SHIP (
       WH_CD,
       ORD_NO,
       SHIP_SEQ,
       CUST_CD,
       ITEM_CD,
       SHIP_QTY
     )
SELECT p.WH_CD,
       p.ORD_NO,
       p.PICK_SEQ,
       h.CUST_CD,
       p.ITEM_CD,
       p.PICK_QTY
  FROM SYNWMS.OUT_PICK p
     , SYNWMS.OUT_ORDER_H h
 WHERE h.WH_CD(+) = p.WH_CD
   AND h.ORD_NO(+) = p.ORD_NO
   AND p.PICK_QTY > 0;
