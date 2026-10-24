WITH base AS (
  SELECT region, platform, age_band, demographic, customer_type, sales,
         CASE WHEN week_number BETWEEN 13 AND 24 THEN 'before'
              WHEN week_number BETWEEN 25 AND 36 THEN 'after' END AS period
  FROM cleaned_weekly_sales
  WHERE calendar_year = 2020 AND week_number BETWEEN 13 AND 36
),
unpivoted AS (
  SELECT 'region' AS attribute_type, region AS attribute_value, period, sales FROM base
  UNION ALL
  SELECT 'platform', platform, period, sales FROM base
  UNION ALL
  SELECT 'age_band', age_band, period, sales FROM base
  UNION ALL
  SELECT 'demographic', demographic, period, sales FROM base
  UNION ALL
  SELECT 'customer_type', customer_type, period, sales FROM base
),
per_value AS (
  SELECT attribute_type, attribute_value,
         SUM(CASE WHEN period = 'before' THEN sales ELSE 0 END) AS before_sales,
         SUM(CASE WHEN period = 'after' THEN sales ELSE 0 END) AS after_sales
  FROM unpivoted
  GROUP BY attribute_type, attribute_value
),
per_type AS (
  SELECT attribute_type,
         AVG((after_sales - before_sales) * 100.0 / NULLIF(before_sales, 0)) AS avg_pct_change
  FROM per_value
  GROUP BY attribute_type
)
SELECT attribute_type, avg_pct_change
FROM per_type
ORDER BY avg_pct_change ASC
LIMIT 1