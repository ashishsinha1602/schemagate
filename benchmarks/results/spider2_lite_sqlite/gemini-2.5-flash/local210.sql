WITH MonthlyFinishedOrders AS (
  SELECT
    h.hub_id,
    h.hub_name,
    o.order_created_month,
    COUNT(o.order_id) AS finished_orders_count
  FROM main.orders AS o
  JOIN main.stores AS s
    ON o.store_id = s.store_id
  JOIN main.hubs AS h
    ON s.hub_id = h.hub_id
  WHERE
    o.order_status = 'finished' AND o.order_created_month IN (2, 3)
  GROUP BY
    h.hub_id,
    h.hub_name,
    o.order_created_month
), HubMonthlyComparison AS (
  SELECT
    hub_id,
    hub_name,
    SUM(CASE WHEN order_created_month = 2 THEN finished_orders_count ELSE 0 END) AS february_orders,
    SUM(CASE WHEN order_created_month = 3 THEN finished_orders_count ELSE 0 END) AS march_orders
  FROM MonthlyFinishedOrders
  GROUP BY
    hub_id,
    hub_name
)
SELECT
  hub_name
FROM HubMonthlyComparison
WHERE
  february_orders > 0 AND (CAST(march_orders AS REAL) / february_orders) > 1.2