WITH monthly AS (
  SELECT s.hub_id,
         SUM(CASE WHEN o.order_created_month = 2 THEN 1 ELSE 0 END) AS feb_orders,
         SUM(CASE WHEN o.order_created_month = 3 THEN 1 ELSE 0 END) AS mar_orders
  FROM orders o
  JOIN stores s ON o.store_id = s.store_id
  WHERE o.order_status = 'FINISHED'
  GROUP BY s.hub_id
)
SELECT h.hub_id, h.hub_name, m.feb_orders, m.mar_orders,
       ROUND((m.mar_orders - m.feb_orders) * 100.0 / m.feb_orders, 2) AS pct_increase
FROM monthly m
JOIN hubs h ON h.hub_id = m.hub_id
WHERE m.feb_orders > 0
  AND m.mar_orders > m.feb_orders * 1.2
ORDER BY pct_increase DESC