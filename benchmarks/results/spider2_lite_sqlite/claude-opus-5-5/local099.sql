WITH yash AS (
  SELECT DISTINCT TRIM(PID) AS pid
  FROM Person
  WHERE TRIM(Name) = 'Yash Chopra'
),
ym AS (
  SELECT DISTINCT TRIM(MID) AS mid
  FROM M_Director
  WHERE TRIM(PID) IN (SELECT pid FROM yash)
),
yc AS (
  SELECT TRIM(c.PID) AS actor,
         COUNT(DISTINCT TRIM(c.MID)) AS n
  FROM M_Cast c
  WHERE TRIM(c.MID) IN (SELECT mid FROM ym)
  GROUP BY TRIM(c.PID)
),
ac AS (
  SELECT DISTINCT TRIM(c.PID) AS actor, TRIM(c.MID) AS mid
  FROM M_Cast c
  WHERE TRIM(c.PID) IN (SELECT actor FROM yc)
),
dm AS (
  SELECT DISTINCT TRIM(MID) AS mid, TRIM(PID) AS director
  FROM M_Director
  WHERE TRIM(PID) NOT IN (SELECT pid FROM yash)
),
other AS (
  SELECT ac.actor, dm.director, COUNT(*) AS n
  FROM ac
  JOIN dm ON ac.mid = dm.mid
  GROUP BY ac.actor, dm.director
),
om AS (
  SELECT actor, MAX(n) AS mx
  FROM other
  GROUP BY actor
)
SELECT COUNT(*) AS num_actors
FROM yc
LEFT JOIN om ON yc.actor = om.actor
WHERE yc.n > COALESCE(om.mx, 0)