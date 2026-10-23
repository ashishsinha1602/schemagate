WITH EmployeeOrderStats AS (
  SELECT
    o.employeeid,
    COUNT(o.orderid) AS total_orders,
    SUM(CASE WHEN o.shippeddate >= o.requireddate THEN 1 ELSE 0 END) AS late_orders
  FROM main.orders AS o
  GROUP BY
    o.employeeid
)
SELECT
  eos.employeeid,
  eos.late_orders,
  CAST(eos.late_orders AS REAL) * 100 / eos.total_orders AS late_order_percentage
FROM EmployeeOrderStats AS eos
WHERE
  eos.total_orders > 50
ORDER BY
  late_order_percentage DESC
LIMIT 3