WITH base AS (
  SELECT
    trafficSource.source AS source,
    SUBSTR(date, 1, 6) AS month,
    totals.totalTransactionRevenue AS revenue
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20171231'
),
top_source AS (
  SELECT source
  FROM base
  GROUP BY source
  ORDER BY SUM(revenue) DESC
  LIMIT 1
),
monthly AS (
  SELECT source, month, SUM(revenue) AS monthly_revenue
  FROM base
  WHERE source IN (SELECT source FROM top_source)
  GROUP BY source, month
)
SELECT
  source,
  ROUND((MAX(monthly_revenue) - MIN(monthly_revenue)) / 1000000, 2) AS difference_in_millions
FROM monthly
GROUP BY source