INSERT INTO SYNWMS.MST_CODE (
       GRP_CD,
       CD,
       CD_NM,
       UP_CD,
       SORT_NO
     )
SELECT c.GRP_CD,
       c.CD,
       LPAD(' ', (LEVEL - 1) * 2) || c.CD_NM,
       c.UP_CD,
       LEVEL
  FROM SYNWMS.MST_CODE c
 START WITH c.UP_CD IS NULL
 CONNECT BY PRIOR c.CD = c.UP_CD;
