WITH s AS (
  SELECT
    user_pseudo_id,
    (SELECT ep.value.int_value FROM UNNEST(event_params) AS ep WHERE ep.key = 'ga_session_id') AS ga_session_id,
    SUM(ecommerce.purchase_revenue_in_usd) AS session_revenue
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20201130'
    AND event_name = 'purchase'
    AND ecommerce.purchase_revenue_in_usd IS NOT NULL
  GROUP BY user_pseudo_id, ga_session_id
)
SELECT
  user_pseudo_id,
  AVG(session_revenue) AS avg_purchase_revenue_in_usd_per_session
FROM s
GROUP BY user_pseudo_id
HAVING COUNT(*) > 1