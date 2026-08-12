WITH w_trx AS (
       SELECT t.WH_CD     AS WH_CD,
              t.ITEM_CD   AS ITEM_CD,
              SUM(t.TRX_QTY) AS QTY
         FROM SYNWMS.STK_TRX t
        WHERE t.TRX_TP_CD = '10'
        GROUP BY t.WH_CD, t.ITEM_CD
     )
INSERT INTO SYNWMS.RPT_DAILY_STK (
       BASE_YMD,
       WH_CD,
       ITEM_CD,
       IN_QTY
     )
SELECT '20260812',
       w.WH_CD,
       w.ITEM_CD,
       w.QTY
  FROM w_trx w;
