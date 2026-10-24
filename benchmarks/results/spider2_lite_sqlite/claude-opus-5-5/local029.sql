WITH delivered AS (
  SELECT c.customer_unique_id, c.customer_city, c.customer_state, o.order_id
  FROM main.olist_orders o
  JOIN main.olist_customers c ON c.customer_id = o.customer_id
  WHERE o.order_status = 'delivered'
),
agg AS (
  SELECT d.customer_unique_id,
         COUNT(DISTINCT d.order_id) AS delivered_orders,
         AVG(p.payment_value) AS avg_payment_value,
         MAX(d.customer_city) AS customer_city,
         MAX(d.customer_state) AS customer_state
  FROM delivered d
  LEFT JOIN main.olist_order_payments p ON p.order_id = d.order_id
  GROUP BY d.customer_unique_id
)
SELECT customer_unique_id, delivered_orders, avg_payment_value, customer_city, customer_state
FROM agg
ORDER BY delivered_orders DESC
LIMIT 3