WITH d AS (
  SELECT c.customer_unique_id,
         COUNT(DISTINCT o.order_id) AS delivered_orders,
         AVG(p.payment_value) AS avg_payment_value,
         MAX(c.customer_city) AS customer_city,
         MAX(c.customer_state) AS customer_state
  FROM olist_customers c
  JOIN olist_orders o ON o.customer_id = c.customer_id
  LEFT JOIN olist_order_payments p ON p.order_id = o.order_id
  WHERE o.order_status = 'delivered'
  GROUP BY c.customer_unique_id
)
SELECT customer_unique_id, delivered_orders, avg_payment_value, customer_city, customer_state
FROM d
ORDER BY delivered_orders DESC, customer_unique_id
LIMIT 3