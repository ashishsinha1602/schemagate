WITH monthly AS (
  SELECT CAST(strftime('%Y', insert_date) AS INTEGER) AS year,
         CAST(strftime('%m', insert_date) AS INTEGER) AS month_num,
         COUNT(*) AS total_cities
  FROM main.cities
  WHERE CAST(strftime('%Y', insert_date) AS INTEGER) BETWEEN 2021 AND 2023
    AND CAST(strftime('%m', insert_date) AS INTEGER) IN (4, 5, 6)
  GROUP BY year, month_num
),
running AS (
  SELECT year, month_num, total_cities,
         SUM(total_cities) OVER (PARTITION BY month_num ORDER BY year
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
  FROM monthly
),
growth AS (
  SELECT year, month_num, total_cities, running_total,
         LAG(total_cities) OVER (PARTITION BY month_num ORDER BY year) AS prev_total,
         LAG(running_total) OVER (PARTITION BY month_num ORDER BY year) AS prev_running
  FROM running
)
SELECT year,
       CASE month_num WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June' END AS month,
       total_cities,
       running_total,
       ROUND((total_cities - prev_total) * 100.0 / prev_total, 2) AS total_growth_pct,
       ROUND((running_total - prev_running) * 100.0 / prev_running, 2) AS running_growth_pct
FROM growth
WHERE year IN (2022, 2023)
ORDER BY year, month_num