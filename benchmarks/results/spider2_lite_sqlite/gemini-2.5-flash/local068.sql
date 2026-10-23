WITH monthly_counts AS (
  SELECT
    CAST(strftime('%Y', insert_date) AS INTEGER) AS year,
    CAST(strftime('%m', insert_date) AS INTEGER) AS month,
    COUNT(city_id) AS cities_added_monthly
  FROM main.cities
  WHERE
    CAST(strftime('%Y', insert_date) AS INTEGER) BETWEEN 2021 AND 2023
    AND CAST(strftime('%m', insert_date) AS INTEGER) IN (4, 5, 6)
  GROUP BY
    year,
    month
),
cumulative_totals_cte AS (
  SELECT
    year,
    month,
    cities_added_monthly,
    SUM(cities_added_monthly) OVER (PARTITION BY month ORDER BY year) AS cumulative_total
  FROM monthly_counts
),
lagged_data_cte AS (
  SELECT
    year,
    month,
    cities_added_monthly,
    cumulative_total,
    LAG(cities_added_monthly, 1) OVER (PARTITION BY month ORDER BY year) AS prev_year_monthly_count,
    LAG(cumulative_total, 1) OVER (PARTITION BY month ORDER BY year) AS prev_year_cumulative_total
  FROM cumulative_totals_cte
)
SELECT
  year,
  CASE month
    WHEN 4 THEN 'April'
    WHEN 5 THEN 'May'
    WHEN 6 THEN 'June'
  END AS month_name,
  cities_added_monthly AS total_cities_added_in_month,
  cumulative_total,
  CASE
    WHEN prev_year_monthly_count IS NULL OR prev_year_monthly_count = 0 THEN NULL
    ELSE (cities_added_monthly - prev_year_monthly_count) * 100.0 / prev_year_monthly_count
  END AS monthly_growth_percentage,
  CASE
    WHEN prev_year_cumulative_total IS NULL OR prev_year_cumulative_total = 0 THEN NULL
    ELSE (cumulative_total - prev_year_cumulative_total) * 100.0 / prev_year_cumulative_total
  END AS cumulative_growth_percentage
FROM lagged_data_cte
WHERE
  year IN (2022, 2023)
ORDER BY
  year,
  month