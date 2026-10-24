WITH scores AS (
  SELECT StyleID,
         SUM(CASE PreferenceSeq WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END) AS TotalWeightedScore
  FROM Musical_Preferences
  GROUP BY StyleID
)
SELECT s.StyleID,
       ms.StyleName,
       s.TotalWeightedScore,
       ABS(s.TotalWeightedScore - (SELECT AVG(TotalWeightedScore) FROM scores)) AS AbsDiffFromAvg
FROM scores s
LEFT JOIN Musical_Styles ms ON ms.StyleID = s.StyleID
ORDER BY s.StyleID