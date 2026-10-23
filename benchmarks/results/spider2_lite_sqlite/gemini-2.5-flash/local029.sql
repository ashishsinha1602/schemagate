SELECT
  c.customer_unique_id,
  AVG(op.payment_value) AS average_payment_value,
  c.customer_city,
  c.customer_state
FROM main.olist_customers AS c
JOIN main.olist_orders AS o
  ON c.customer_id = o.customer_id
JOIN main.olist_order_payments AS op
  ON o.order_id = op.order_id
WHERE
  o.order_status = 'delivered'
GROUP BY
  c.customer_unique_id,
  c.customer_city,
  c.customer_state
ORDER BY
  COUNT(DISTINCT o.order_id) DESC
LIMIT 3