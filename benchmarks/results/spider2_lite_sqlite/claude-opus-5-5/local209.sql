WITH store_orders AS (
  SELECT o.store_id, s.store_name, COUNT(*) AS total_orders
  FROM orders o
  JOIN stores s ON s.store_id = o.store_id
  GROUP BY o.store_id, s.store_name
),
top_store AS (
  SELECT store_id, store_name, total_orders
  FROM store_orders
  ORDER BY total_orders DESC
  LIMIT 1
),
delivered AS (
  SELECT DISTINCT delivery_order_id
  FROM deliveries
  WHERE delivery_status = 'DELIVERED'
    AND delivery_order_id IS NOT NULL
)
SELECT t.store_id,
       t.store_name,
       t.total_orders,
       CAST(SUM(CASE WHEN o.delivery_order_id IN (SELECT delivery_order_id FROM delivered)
                     THEN 1 ELSE 0 END) AS REAL) / t.total_orders AS delivered_ratio
FROM top_store t
JOIN orders o ON o.store_id = t.store_id
GROUP BY t.store_id, t.store_name, t.total_orders