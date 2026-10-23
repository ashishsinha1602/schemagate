WITH mc AS (
  SELECT c.MID, SUM(CASE WHEN p.Gender = 'Female' THEN 0 ELSE 1 END) AS nonf
  FROM M_Cast c
  LEFT JOIN Person p ON p.PID = c.PID
  GROUP BY c.MID
)
SELECT CAST(SUBSTR(m.year, -4) AS INTEGER) AS year,
       COUNT(*) AS total_movies,
       100.0 * SUM(CASE WHEN mc.nonf = 0 THEN 1 ELSE 0 END) / COUNT(*) AS pct_exclusively_female
FROM Movie m
LEFT JOIN mc ON mc.MID = m.MID
GROUP BY CAST(SUBSTR(m.year, -4) AS INTEGER)
ORDER BY year