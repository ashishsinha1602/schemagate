WITH CustomerOrderCounts AS (
  SELECT
    oc.customer_unique_id,
    oc.customer_city,
    oc.customer_state,
    COUNT(DISTINCT oo.order_id) AS delivered_order_count,
    SUM(oop.payment_value) AS total_payment_value,
    COUNT(oop.payment_value) AS payment_count
  FROM main.olist_customers AS oc
  JOIN main.olist_orders AS oo
    ON oc.customer_id = oo.customer_id
  JOIN main.olist_order_payments AS oop
    ON oo.order_id = oop.order_id
  WHERE
    oo.order_status = 'delivered'
  GROUP BY
    oc.customer_unique_id,
    oc.customer_city,
    oc.customer_state
)
SELECT
  customer_unique_id,
  CAST(total_payment_value AS REAL) / payment_count AS average_payment_value,
  customer_city,
  customer_state
FROM CustomerOrderCounts
ORDER BY
  delivered_order_count DESC
LIMIT 3