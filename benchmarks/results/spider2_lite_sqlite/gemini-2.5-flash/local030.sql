WITH DeliveredOrderPayments AS (
  SELECT
    c.customer_city,
    SUM(op.payment_value) AS total_payment_value,
    COUNT(DISTINCT o.order_id) AS delivered_order_count
  FROM main.olist_orders AS o
  JOIN main.olist_order_payments AS op
    ON o.order_id = op.order_id
  JOIN main.olist_customers AS c
    ON o.customer_id = c.customer_id
  WHERE
    o.order_status = 'delivered'
  GROUP BY
    c.customer_city
), Top5LowestPaymentCities AS (
  SELECT
    customer_city,
    total_payment_value,
    delivered_order_count
  FROM DeliveredOrderPayments
  ORDER BY
    total_payment_value ASC
  LIMIT 5
)
SELECT
  AVG(total_payment_value) AS average_total_payment_of_lowest_cities,
  AVG(delivered_order_count) AS average_delivered_order_count_of_lowest_cities
FROM Top5LowestPaymentCities