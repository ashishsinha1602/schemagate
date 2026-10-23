WITH DailyDeliveries AS (
  SELECT
    d.driver_id,
    STRFTIME('%Y-%m-%d', o.order_moment_delivered) AS delivery_date,
    COUNT(d.delivery_id) AS deliveries_count
  FROM main.deliveries AS d
  JOIN main.orders AS o
    ON d.delivery_order_id = o.delivery_order_id
  WHERE
    o.order_moment_delivered IS NOT NULL
  GROUP BY
    d.driver_id,
    delivery_date
)
SELECT
  dd.driver_id,
  AVG(dd.deliveries_count) AS average_daily_deliveries
FROM DailyDeliveries AS dd
GROUP BY
  dd.driver_id
ORDER BY
  average_daily_deliveries DESC
LIMIT 5