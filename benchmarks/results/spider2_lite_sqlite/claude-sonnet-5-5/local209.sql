WITH top AS (
  SELECT s.store_id, s.store_name, COUNT(*) AS total_orders
  FROM orders o
  JOIN stores s ON o.store_id = s.store_id
  GROUP BY s.store_id, s.store_name
  ORDER BY total_orders DESC
  LIMIT 1
),
delivered AS (
  SELECT DISTINCT delivery_order_id
  FROM deliveries
  WHERE delivery_status = 'DELIVERED'
    AND delivery_order_id IS NOT NULL
)
SELECT
  t.store_id,
  t.store_name,
  t.total_orders,
  COUNT(dl.delivery_order_id) AS delivered_orders,
  1.0 * COUNT(dl.delivery_order_id) / t.total_orders AS delivered_ratio
FROM top t
JOIN orders o ON o.store_id = t.store_id
LEFT JOIN delivered dl ON dl.delivery_order_id = o.delivery_order_id
GROUP BY t.store_id, t.store_name, t.total_orders