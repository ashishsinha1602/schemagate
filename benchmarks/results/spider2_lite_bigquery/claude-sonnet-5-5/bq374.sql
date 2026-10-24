WITH first_visits AS (
  SELECT fullVisitorId, MAX(totals.timeOnSite) AS time_on_site
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20160801' AND '20170430'
    AND totals.newVisits = 1
  GROUP BY fullVisitorId
),
purchasers AS (
  SELECT DISTINCT fullVisitorId
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20160801' AND '20170801'
    AND visitNumber > 1
    AND totals.transactions >= 1
)
SELECT
  SAFE_DIVIDE(
    COUNTIF(f.time_on_site > 300 AND p.fullVisitorId IS NOT NULL) * 100,
    COUNT(*)
  ) AS percentage
FROM first_visits f
LEFT JOIN purchasers p
  ON f.fullVisitorId = p.fullVisitorId