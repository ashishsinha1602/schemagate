WITH stats AS (
  SELECT employeeid,
         COUNT(*) AS total_orders,
         SUM(CASE WHEN shippeddate >= requireddate THEN 1 ELSE 0 END) AS late_orders
  FROM orders
  GROUP BY employeeid
  HAVING COUNT(*) > 50
)
SELECT employeeid,
       late_orders,
       100.0 * late_orders / total_orders AS late_percentage
FROM stats
ORDER BY late_percentage DESC
LIMIT 3