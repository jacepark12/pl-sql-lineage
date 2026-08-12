INSERT INTO SYNWMS.RPT_MONTHLY_TRX (
       BASE_YM,
       WH_CD,
       IN_QTY,
       OUT_QTY
     )
SELECT p.BASE_YM,
       p.WH_CD,
       NVL(p.IN_QTY, 0),
       NVL(p.OUT_QTY, 0)
  FROM (
       SELECT SUBSTR(t.TRX_YMD, 1, 6) AS BASE_YM,
              t.WH_CD                 AS WH_CD,
              t.TRX_TP_CD             AS TRX_TP_CD,
              t.TRX_QTY               AS TRX_QTY
         FROM SYNWMS.STK_TRX t
       ) PIVOT (SUM(TRX_QTY) FOR TRX_TP_CD IN ('10' AS IN_QTY, '20' AS OUT_QTY)) p;
