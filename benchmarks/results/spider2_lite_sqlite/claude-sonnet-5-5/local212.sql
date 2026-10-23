WITH daily AS (
  SELECT d.driver_id,
         o.order_created_year,
         o.order_created_month,
         o.order_created_day,
         COUNT(DISTINCT d.delivery_id) AS deliveries_count
  FROM deliveries d
  JOIN orders o ON o.delivery_order_id = d.delivery_order_id
  WHERE d.driver_id IS NOT NULL
  GROUP BY d.driver_id, o.order_created_year, o.order_created_month, o.order_created_day
)
SELECT dr.driver_id,
       dr.driver_modal,
       dr.driver_type,
       AVG(daily.deliveries_count) AS avg_daily_deliveries
FROM daily
JOIN drivers dr ON dr.driver_id = daily.driver_id
GROUP BY dr.driver_id, dr.driver_modal, dr.driver_type
ORDER BY avg_daily_deliveries DESC
LIMIT 5