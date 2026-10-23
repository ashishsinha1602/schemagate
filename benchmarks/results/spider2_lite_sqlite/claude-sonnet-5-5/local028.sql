SELECT
  substr(order_purchase_timestamp, 6, 2) AS month,
  SUM(CASE WHEN substr(order_purchase_timestamp, 1, 4) = '2016' THEN 1 ELSE 0 END) AS "2016",
  SUM(CASE WHEN substr(order_purchase_timestamp, 1, 4) = '2017' THEN 1 ELSE 0 END) AS "2017",
  SUM(CASE WHEN substr(order_purchase_timestamp, 1, 4) = '2018' THEN 1 ELSE 0 END) AS "2018"
FROM olist_orders
WHERE order_status = 'delivered'
  AND substr(order_purchase_timestamp, 1, 4) IN ('2016', '2017', '2018')
GROUP BY substr(order_purchase_timestamp, 6, 2)
ORDER BY month