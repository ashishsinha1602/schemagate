WITH d AS (
  SELECT DISTINCT country_code_2, date(insert_date) AS dt
  FROM cities
  WHERE insert_date >= '2022-06-01' AND insert_date < '2022-07-01'
    AND country_code_2 IS NOT NULL
),
g AS (
  SELECT country_code_2, dt,
         julianday(dt) - ROW_NUMBER() OVER (PARTITION BY country_code_2 ORDER BY dt) AS grp
  FROM d
),
s AS (
  SELECT country_code_2, COUNT(*) AS len
  FROM g
  GROUP BY country_code_2, grp
)
SELECT DISTINCT country_code_2
FROM s
WHERE len = (SELECT MAX(len) FROM s)