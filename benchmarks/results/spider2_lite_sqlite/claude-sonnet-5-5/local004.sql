WITH order_pay AS (
  SELECT order_id, SUM(payment_value) AS total_payment
  FROM order_payments
  GROUP BY order_id
),
cust AS (
  SELECT c.customer_unique_id,
         COUNT(DISTINCT o.order_id) AS num_orders,
         SUM(op.total_payment) * 1.0 / COUNT(DISTINCT o.order_id) AS avg_payment_per_order,
         julianday(MAX(o.order_purchase_timestamp)) - julianday(MIN(o.order_purchase_timestamp)) AS span_days
  FROM orders o
  JOIN customers c ON c.customer_id = o.customer_id
  JOIN order_pay op ON op.order_id = o.order_id
  GROUP BY c.customer_unique_id
)
SELECT customer_unique_id,
       num_orders,
       avg_payment_per_order,
       CASE WHEN span_days < 7 THEN 1.0 ELSE span_days / 7.0 END AS customer_lifespan_weeks
FROM cust
ORDER BY avg_payment_per_order DESC
LIMIT 3