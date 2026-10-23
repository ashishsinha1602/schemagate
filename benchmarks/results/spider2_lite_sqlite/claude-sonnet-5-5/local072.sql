WITH d AS (
  SELECT DISTINCT country_code_2 AS cc, date(insert_date) AS dt
  FROM cities
  WHERE date(insert_date) BETWEEN '2022-01-01' AND '2022-01-31'
),
c AS (
  SELECT cc FROM d GROUP BY cc HAVING COUNT(*) = 9
),
r AS (
  SELECT d.cc, d.dt,
         date(d.dt, '-' || (ROW_NUMBER() OVER (PARTITION BY d.cc ORDER BY d.dt)) || ' day') AS grp
  FROM d JOIN c ON c.cc = d.cc
),
s AS (
  SELECT cc, MIN(dt) AS start_dt, MAX(dt) AS end_dt, COUNT(*) AS len
  FROM r
  GROUP BY cc, grp
),
best AS (
  SELECT * FROM s ORDER BY len DESC LIMIT 1
)
SELECT best.cc AS country_code_2,
       best.start_dt,
       best.end_dt,
       best.len AS consecutive_days,
       COUNT(*) AS total_entries,
       SUM(CASE WHEN ci.capital = 1 THEN 1 ELSE 0 END) AS capital_entries,
       SUM(CASE WHEN ci.capital = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS capital_proportion
FROM best
JOIN cities ci ON ci.country_code_2 = best.cc
  AND date(ci.insert_date) BETWEEN best.start_dt AND best.end_dt
GROUP BY best.cc, best.start_dt, best.end_dt, best.len