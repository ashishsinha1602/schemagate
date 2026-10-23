SELECT ms.StyleID, ms.StyleName,
  COALESCE(SUM(CASE WHEN mp.PreferenceSeq = 1 THEN 1 ELSE 0 END), 0) AS FirstPreference,
  COALESCE(SUM(CASE WHEN mp.PreferenceSeq = 2 THEN 1 ELSE 0 END), 0) AS SecondPreference,
  COALESCE(SUM(CASE WHEN mp.PreferenceSeq = 3 THEN 1 ELSE 0 END), 0) AS ThirdPreference
FROM Musical_Styles ms
LEFT JOIN Musical_Preferences mp ON mp.StyleID = ms.StyleID
GROUP BY ms.StyleID, ms.StyleName
ORDER BY ms.StyleID