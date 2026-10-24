SELECT employeeid, late_orders, late_pct
FROM (
  SELECT employeeid,
         COUNT(*) AS total_orders,
         SUM(CASE WHEN shippeddate >= requireddate THEN 1 ELSE 0 END) AS late_orders,
         100.0 * SUM(CASE WHEN shippeddate >= requireddate THEN 1 ELSE 0 END) / COUNT(*) AS late_pct
  FROM orders
  GROUP BY employeeid
  HAVING COUNT(*) > 50
) t
ORDER BY late_pct DESC
LIMIT 3