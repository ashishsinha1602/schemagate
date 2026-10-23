WITH yc AS (
  SELECT PID FROM Person WHERE TRIM(Name) = 'Yash Chopra'
),
pairs AS (
  SELECT c.PID AS actor, d.PID AS director, COUNT(DISTINCT c.MID) AS n
  FROM M_Cast c
  JOIN M_Director d ON c.MID = d.MID
  GROUP BY c.PID, d.PID
),
ycc AS (
  SELECT actor, SUM(n) AS n
  FROM pairs
  WHERE director IN (SELECT PID FROM yc)
  GROUP BY actor
),
oth AS (
  SELECT actor, MAX(n) AS m
  FROM pairs
  WHERE director NOT IN (SELECT PID FROM yc)
  GROUP BY actor
)
SELECT COUNT(*) AS actor_count
FROM ycc
LEFT JOIN oth ON ycc.actor = oth.actor
WHERE ycc.n > COALESCE(oth.m, 0)