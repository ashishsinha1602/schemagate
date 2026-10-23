WITH store_order_counts AS (
  SELECT
    store_id,
    COUNT(order_id) AS total_orders
  FROM main.orders
  GROUP BY
    store_id
), top_store_info AS (
  SELECT
    soc.store_id,
    s.store_name,
    soc.total_orders
  FROM store_order_counts AS soc
  JOIN main.stores AS s
    ON soc.store_id = s.store_id
  ORDER BY
    soc.total_orders DESC
  LIMIT 1
)
SELECT
  tsi.store_id,
  tsi.store_name,
  CAST(SUM(CASE WHEN d.delivery_status = 'DELIVERED' THEN 1 ELSE 0 END) AS REAL) / tsi.total_orders AS delivered_ratio
FROM top_store_info AS tsi
JOIN main.orders AS o
  ON tsi.store_id = o.store_id
LEFT JOIN main.deliveries AS d
  ON o.delivery_order_id = d.delivery_order_id
GROUP BY
  tsi.store_id,
  tsi.store_name,
  tsi.total_orders