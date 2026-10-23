WITH c AS (
  SELECT s.hub_id,
         SUM(CASE WHEN o.order_created_month = 2 THEN 1 ELSE 0 END) AS feb_orders,
         SUM(CASE WHEN o.order_created_month = 3 THEN 1 ELSE 0 END) AS mar_orders
  FROM orders o
  JOIN stores s ON s.store_id = o.store_id
  WHERE o.order_status = 'FINISHED'
    AND o.order_created_month IN (2, 3)
  GROUP BY s.hub_id
)
SELECT h.hub_id,
       h.hub_name,
       c.feb_orders,
       c.mar_orders,
       (c.mar_orders - c.feb_orders) * 100.0 / c.feb_orders AS pct_increase
FROM c
JOIN hubs h ON h.hub_id = c.hub_id
WHERE c.feb_orders > 0
  AND c.mar_orders > c.feb_orders * 1.2
ORDER BY pct_increase DESC