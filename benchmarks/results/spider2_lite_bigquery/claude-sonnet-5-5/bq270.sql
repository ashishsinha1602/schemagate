SELECT
  FORMAT_DATE('%Y%m', PARSE_DATE('%Y%m%d', t.date)) AS month,
  COUNTIF(h.eCommerceAction.action_type = '2') AS num_product_view,
  COUNTIF(h.eCommerceAction.action_type = '3') AS num_addtocart,
  COUNTIF(h.eCommerceAction.action_type = '6') AS num_purchase,
  SAFE_DIVIDE(COUNTIF(h.eCommerceAction.action_type = '3'), COUNTIF(h.eCommerceAction.action_type = '2')) * 100 AS add_to_cart_rate,
  SAFE_DIVIDE(COUNTIF(h.eCommerceAction.action_type = '6'), COUNTIF(h.eCommerceAction.action_type = '2')) * 100 AS purchase_rate
FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*` AS t,
  UNNEST(t.hits) AS h,
  UNNEST(h.product) AS p
WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20170331'
  AND (p.isImpression IS NULL OR p.isImpression = FALSE)
GROUP BY month
ORDER BY month