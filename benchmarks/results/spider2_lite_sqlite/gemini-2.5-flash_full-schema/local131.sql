SELECT
  MS.StyleName,
  SUM(CASE WHEN MP.PreferenceSeq = 1 THEN 1 ELSE 0 END) AS FirstPreferenceCount,
  SUM(CASE WHEN MP.PreferenceSeq = 2 THEN 1 ELSE 0 END) AS SecondPreferenceCount,
  SUM(CASE WHEN MP.PreferenceSeq = 3 THEN 1 ELSE 0 END) AS ThirdPreferenceCount
FROM main.Musical_Styles AS MS
JOIN main.Musical_Preferences AS MP
  ON MS.StyleID = MP.StyleID
WHERE
  MP.PreferenceSeq IN (1, 2, 3)
GROUP BY
  MS.StyleName