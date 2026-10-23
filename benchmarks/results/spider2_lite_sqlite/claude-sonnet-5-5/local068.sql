WITH m AS (
  SELECT CAST(strftime('%Y', insert_date) AS INTEGER) AS yr,
         CAST(strftime('%m', insert_date) AS INTEGER) AS mo,
         COUNT(*) AS total
  FROM cities
  WHERE CAST(strftime('%Y', insert_date) AS INTEGER) BETWEEN 2021 AND 2023
    AND CAST(strftime('%m', insert_date) AS INTEGER) IN (4,5,6)
  GROUP BY yr, mo
),
r AS (
  SELECT yr, mo, total,
         SUM(total) OVER (PARTITION BY mo ORDER BY yr ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
  FROM m
),
g AS (
  SELECT yr, mo, total, running_total,
         LAG(total) OVER (PARTITION BY mo ORDER BY yr) AS prev_total,
         LAG(running_total) OVER (PARTITION BY mo ORDER BY yr) AS prev_running
  FROM r
)
SELECT yr AS year,
       CASE mo WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June' END AS month,
       total AS total_cities_added,
       running_total,
       ROUND(100.0 * (total - prev_total) / prev_total, 2) AS yoy_growth_total_pct,
       ROUND(100.0 * (running_total - prev_running) / prev_running, 2) AS yoy_growth_running_total_pct
FROM g
WHERE yr IN (2022, 2023)
ORDER BY yr, mo