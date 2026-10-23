WITH d AS (
  SELECT date(insert_date) AS dt, MIN(city_name) AS cn
  FROM cities
  WHERE lower(country_code_2) = 'cn'
    AND date(insert_date) BETWEEN '2021-07-01' AND '2021-07-31'
  GROUP BY date(insert_date)
),
g AS (
  SELECT dt, cn, julianday(dt) - ROW_NUMBER() OVER (ORDER BY dt) AS grp
  FROM d
),
s AS (
  SELECT dt, cn, grp, COUNT(*) OVER (PARTITION BY grp) AS len
  FROM g
)
SELECT dt AS date, upper(substr(cn, 1, 1)) || lower(substr(cn, 2)) AS city_name
FROM s
WHERE len = (SELECT MAX(len) FROM s)
   OR len = (SELECT MIN(len) FROM s)
ORDER BY dt