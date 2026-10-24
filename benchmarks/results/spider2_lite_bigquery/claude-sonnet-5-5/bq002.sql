WITH base AS (
  SELECT
    trafficSource.source AS source,
    PARSE_DATE('%Y%m%d', date) AS d,
    p.productRevenue AS rev
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`,
    UNNEST(hits) AS h,
    UNNEST(h.product) AS p
  WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20170630'
    AND p.productRevenue IS NOT NULL
),
top_source AS (
  SELECT source, SUM(rev) AS total_rev
  FROM base
  GROUP BY source
  ORDER BY total_rev DESC
  LIMIT 1
),
daily AS (
  SELECT d AS period, SUM(rev) AS r
  FROM base
  WHERE source = (SELECT source FROM top_source)
  GROUP BY period
),
weekly AS (
  SELECT DATE_TRUNC(d, WEEK) AS period, SUM(rev) AS r
  FROM base
  WHERE source = (SELECT source FROM top_source)
  GROUP BY period
),
monthly AS (
  SELECT DATE_TRUNC(d, MONTH) AS period, SUM(rev) AS r
  FROM base
  WHERE source = (SELECT source FROM top_source)
  GROUP BY period
)
SELECT
  (SELECT source FROM top_source) AS source,
  (SELECT MAX(r) FROM daily) / 1000000 AS max_daily_revenue_millions,
  (SELECT MAX(r) FROM weekly) / 1000000 AS max_weekly_revenue_millions,
  (SELECT MAX(r) FROM monthly) / 1000000 AS max_monthly_revenue_millions