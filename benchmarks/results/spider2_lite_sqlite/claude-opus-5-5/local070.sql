WITH cn AS (
  SELECT city_id, city_name, date(insert_date) AS dt
  FROM main.cities
  WHERE country_code_2 = 'cn'
    AND date(insert_date) >= '2021-07-01'
    AND date(insert_date) <= '2021-07-31'
),
d AS (
  SELECT DISTINCT dt FROM cn
),
g AS (
  SELECT dt, julianday(dt) - ROW_NUMBER() OVER (ORDER BY dt) AS grp
  FROM d
),
s AS (
  SELECT grp, COUNT(*) AS len FROM g GROUP BY grp
),
sel AS (
  SELECT grp FROM s
  WHERE len = (SELECT MAX(len) FROM s) OR len = (SELECT MIN(len) FROM s)
),
c AS (
  SELECT dt, city_name,
         ROW_NUMBER() OVER (PARTITION BY dt ORDER BY city_id) AS rn
  FROM cn
)
SELECT g.dt AS date,
       UPPER(SUBSTR(c.city_name, 1, 1)) || LOWER(SUBSTR(c.city_name, 2)) AS city_name
FROM g
JOIN sel ON sel.grp = g.grp
JOIN c ON c.dt = g.dt AND c.rn = 1
ORDER BY g.dt