WITH buyers AS (
  SELECT DISTINCT fullVisitorId
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` s,
    UNNEST(s.hits) h,
    UNNEST(h.product) p
  WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
    AND p.v2ProductName = 'Youtube Men’s Vintage Henley'
    AND p.productRevenue IS NOT NULL
)
SELECT
  p.v2ProductName AS product_name,
  SUM(p.productQuantity) AS total_quantity
FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` s,
  UNNEST(s.hits) h,
  UNNEST(h.product) p
WHERE _TABLE_SUFFIX BETWEEN '20170701' AND '20170731'
  AND s.fullVisitorId IN (SELECT fullVisitorId FROM buyers)
  AND p.v2ProductName <> 'Youtube Men’s Vintage Henley'
  AND p.productRevenue IS NOT NULL
GROUP BY product_name
ORDER BY total_quantity DESC
LIMIT 1