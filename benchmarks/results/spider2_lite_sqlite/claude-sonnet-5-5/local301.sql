WITH s AS (
  SELECT calendar_year,
         SUM(CASE WHEN week_number BETWEEN 21 AND 24 THEN sales END) AS before_sales,
         SUM(CASE WHEN week_number BETWEEN 25 AND 28 THEN sales END) AS after_sales
  FROM cleaned_weekly_sales
  WHERE calendar_year IN (2018, 2019, 2020)
  GROUP BY calendar_year
)
SELECT calendar_year,
       before_sales,
       after_sales,
       ROUND(100.0 * (after_sales - before_sales) / before_sales, 2) AS pct_change
FROM s
ORDER BY calendar_year