WITH StyleWeightedPoints AS (
  SELECT
    mp.StyleID,
    ms.StyleName,
    CASE mp.PreferenceSeq
      WHEN 1 THEN 3
      WHEN 2 THEN 2
      WHEN 3 THEN 1
      ELSE 0
    END AS WeightedPoint
  FROM main.Musical_Preferences AS mp
  JOIN main.Musical_Styles AS ms
    ON mp.StyleID = ms.StyleID
),
StyleTotalScores AS (
  SELECT
    StyleID,
    StyleName,
    SUM(WeightedPoint) AS TotalWeightedScore
  FROM StyleWeightedPoints
  GROUP BY
    StyleID,
    StyleName
)
SELECT
  sts.StyleName,
  ABS(sts.TotalWeightedScore - AVG(sts.TotalWeightedScore) OVER ()) AS DifferenceFromAverage
FROM StyleTotalScores AS sts