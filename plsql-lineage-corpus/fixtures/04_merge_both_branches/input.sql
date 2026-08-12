MERGE INTO SYNWMS.STK_ONHAND t
USING (
      SELECT r.WH_CD    AS WH_CD,
             r.LOC_CD   AS LOC_CD,
             r.ITEM_CD  AS ITEM_CD,
             r.LOT_NO   AS LOT_NO,
             r.RCV_QTY  AS ONHAND_QTY
        FROM SYNWMS.INB_RESULT r
       WHERE r.RCV_QTY > 0
     ) q
    ON (t.WH_CD = q.WH_CD AND t.ITEM_CD = q.ITEM_CD)
WHEN MATCHED THEN
  UPDATE SET
    t.ONHAND_QTY = t.ONHAND_QTY + q.ONHAND_QTY
WHEN NOT MATCHED THEN
  INSERT (
       WH_CD,
       LOC_CD,
       ITEM_CD,
       LOT_NO,
       ONHAND_QTY
     )
  VALUES (
       q.WH_CD,
       q.LOC_CD,
       q.ITEM_CD,
       q.LOT_NO,
       q.ONHAND_QTY
     );
