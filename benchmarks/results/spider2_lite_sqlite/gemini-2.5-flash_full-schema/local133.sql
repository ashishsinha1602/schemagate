WITH StyleScores AS (
  SELECT
    ms.StyleID,
    ms.StyleName,
    SUM(CASE mp.PreferenceSeq
      WHEN 1
      THEN 3
      WHEN 2
      THEN 2
      WHEN 3
      THEN 1
      ELSE 0
    END) AS TotalWeightedScore
  FROM main.Musical_Preferences AS mp
  JOIN main.Musical_Styles AS ms
    ON mp.StyleID = ms.StyleID
  GROUP BY
    ms.StyleID,
    ms.StyleName
)
SELECT
  ss.StyleID,
  ss.StyleName,
  ss.TotalWeightedScore,
  AVG(ss.TotalWeightedScore) OVER () AS AverageTotalWeightedScore,
  ABS(ss.TotalWeightedScore - AVG(ss.TotalWeightedScore) OVER ()) AS DifferenceFromAverage
FROM StyleScores AS ss