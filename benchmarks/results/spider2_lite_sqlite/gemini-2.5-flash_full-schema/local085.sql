WITH EmployeeOrderStats AS (
  SELECT
    o.employeeid,
    SUM(CASE WHEN o.shippeddate >= o.requireddate THEN 1 ELSE 0 END) AS late_orders_count,
    COUNT(o.orderid) AS total_orders_count
  FROM main.orders AS o
  GROUP BY
    o.employeeid
)
SELECT
  eos.employeeid,
  eos.late_orders_count,
  CAST(eos.late_orders_count AS REAL) * 100.0 / eos.total_orders_count AS late_order_percentage
FROM EmployeeOrderStats AS eos
WHERE
  eos.total_orders_count > 50
ORDER BY
  late_order_percentage DESC
LIMIT 3