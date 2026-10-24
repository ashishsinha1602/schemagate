WITH movie_years AS MATERIALIZED (
  SELECT TRIM(MID) AS mid,
         CAST(SUBSTR(TRIM(year), -4) AS INTEGER) AS yr
  FROM Movie
  WHERE year IS NOT NULL
  GROUP BY TRIM(MID)
),
cast_movies AS MATERIALIZED (
  SELECT DISTINCT TRIM(PID) AS pid, TRIM(MID) AS mid
  FROM M_Cast
),
cast_years AS (
  SELECT DISTINCT c.pid, m.yr
  FROM cast_movies c
  JOIN movie_years m ON m.mid = c.mid
  WHERE m.yr > 0
),
gaps AS (
  SELECT pid,
         yr,
         LEAD(yr) OVER (PARTITION BY pid ORDER BY yr) AS next_yr
  FROM cast_years
)
SELECT COUNT(*) AS num_actors
FROM (
  SELECT pid
  FROM gaps
  GROUP BY pid
  HAVING MAX(CASE WHEN next_yr IS NOT NULL AND next_yr - yr - 1 > 3 THEN 1 ELSE 0 END) = 0
) t