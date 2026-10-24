WITH srk AS (
  SELECT TRIM(PID) AS PID
  FROM Person
  WHERE Name LIKE '%Shahrukh Khan%'
),
srk_movies AS (
  SELECT DISTINCT TRIM(c.MID) AS MID
  FROM M_Cast c
  JOIN srk s ON TRIM(c.PID) = s.PID
),
lvl1 AS (
  SELECT DISTINCT TRIM(c.PID) AS PID
  FROM M_Cast c
  JOIN srk_movies m ON TRIM(c.MID) = m.MID
  WHERE TRIM(c.PID) NOT IN (SELECT PID FROM srk)
),
lvl1_movies AS (
  SELECT DISTINCT TRIM(c.MID) AS MID
  FROM M_Cast c
  JOIN lvl1 l ON TRIM(c.PID) = l.PID
),
lvl2 AS (
  SELECT DISTINCT TRIM(c.PID) AS PID
  FROM M_Cast c
  JOIN lvl1_movies m ON TRIM(c.MID) = m.MID
  WHERE TRIM(c.PID) NOT IN (SELECT PID FROM lvl1)
    AND TRIM(c.PID) NOT IN (SELECT PID FROM srk)
)
SELECT COUNT(*) AS shahrukh_number_2_actors
FROM lvl2