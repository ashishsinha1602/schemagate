WITH scores AS (
  SELECT mp.StyleID,
         ms.StyleName,
         SUM(CASE mp.PreferenceSeq WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END) AS TotalScore
  FROM Musical_Preferences mp
  JOIN Musical_Styles ms ON ms.StyleID = mp.StyleID
  GROUP BY mp.StyleID, ms.StyleName
)
SELECT StyleID,
       StyleName,
       TotalScore,
       ABS(TotalScore - (SELECT AVG(TotalScore * 1.0) FROM scores)) AS AbsDiffFromAvg
FROM scores
ORDER BY StyleID