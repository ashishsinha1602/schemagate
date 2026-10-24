WITH daily AS (
  SELECT d.driver_id,
         o.order_created_year,
         o.order_created_month,
         o.order_created_day,
         COUNT(d.delivery_id) AS daily_deliveries
  FROM deliveries d
  JOIN orders o ON o.delivery_order_id = d.delivery_order_id
  WHERE d.driver_id IS NOT NULL
  GROUP BY d.driver_id, o.order_created_year, o.order_created_month, o.order_created_day
)
SELECT driver_id,
       AVG(daily_deliveries) AS avg_daily_deliveries
FROM daily
GROUP BY driver_id
ORDER BY avg_daily_deliveries DESC
LIMIT 5