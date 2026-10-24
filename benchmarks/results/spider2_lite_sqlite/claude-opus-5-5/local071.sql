WITH d AS (
  SELECT DISTINCT country_code_2, date(insert_date) AS dt
  FROM main.cities
  WHERE date(insert_date) BETWEEN '2022-06-01' AND '2022-06-30'
),
g AS (
  SELECT country_code_2, dt,
         julianday(dt) - ROW_NUMBER() OVER (PARTITION BY country_code_2 ORDER BY dt) AS grp
  FROM d
),
s AS (
  SELECT country_code_2, grp, COUNT(*) AS streak
  FROM g
  GROUP BY country_code_2, grp
),
m AS (
  SELECT country_code_2, MAX(streak) AS max_streak
  FROM s
  GROUP BY country_code_2
)
SELECT country_code_2
FROM m
WHERE max_streak = (SELECT MAX(max_streak) FROM m)
ORDER BY country_code_2