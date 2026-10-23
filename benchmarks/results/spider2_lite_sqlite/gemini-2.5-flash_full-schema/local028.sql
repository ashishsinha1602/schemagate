SELECT
  strftime('%m', o.order_purchase_timestamp) AS month,
  COUNT(CASE WHEN strftime('%Y', o.order_purchase_timestamp) = '2016' THEN o.order_id END) AS "2016",
  COUNT(CASE WHEN strftime('%Y', o.order_purchase_timestamp) = '2017' THEN o.order_id END) AS "2017",
  COUNT(CASE WHEN strftime('%Y', o.order_purchase_timestamp) = '2018' THEN o.order_id END) AS "2018"
FROM main.olist_orders AS o
WHERE o.order_status = 'delivered'
  AND strftime('%Y', o.order_purchase_timestamp) IN ('2016', '2017', '2018')
GROUP BY month
ORDER BY month