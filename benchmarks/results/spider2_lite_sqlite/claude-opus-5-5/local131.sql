SELECT ms.StyleID, ms.StyleName,
       SUM(CASE WHEN mp.PreferenceSeq = 1 THEN 1 ELSE 0 END) AS FirstPreferenceCount,
       SUM(CASE WHEN mp.PreferenceSeq = 2 THEN 1 ELSE 0 END) AS SecondPreferenceCount,
       SUM(CASE WHEN mp.PreferenceSeq = 3 THEN 1 ELSE 0 END) AS ThirdPreferenceCount
FROM Musical_Styles ms
JOIN Musical_Preferences mp ON mp.StyleID = ms.StyleID
GROUP BY ms.StyleID, ms.StyleName
ORDER BY ms.StyleID