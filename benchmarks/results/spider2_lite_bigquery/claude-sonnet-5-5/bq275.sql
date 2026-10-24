WITH s AS (
  SELECT
    fullVisitorId,
    date,
    visitStartTime,
    device.deviceCategory AS deviceCategory,
    totals.transactionRevenue AS transactionRevenue
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`
  WHERE _TABLE_SUFFIX BETWEEN '20160801' AND '20170801'
),
first_visit AS (
  SELECT fullVisitorId, MIN(date) AS first_visit_date
  FROM s
  GROUP BY fullVisitorId
),
first_tx AS (
  SELECT
    fullVisitorId,
    ARRAY_AGG(STRUCT(date, deviceCategory) ORDER BY date, visitStartTime LIMIT 1)[OFFSET(0)] AS tx
  FROM s
  WHERE transactionRevenue IS NOT NULL
  GROUP BY fullVisitorId
)
SELECT DISTINCT t.fullVisitorId
FROM first_tx t
JOIN first_visit v ON v.fullVisitorId = t.fullVisitorId
WHERE t.tx.deviceCategory = 'mobile'
  AND t.tx.date > v.first_visit_date