WITH order_pay AS (
  SELECT order_id, SUM(payment_value) AS pay
  FROM olist_order_payments
  GROUP BY order_id
),
city_stats AS (
  SELECT c.customer_city,
         SUM(op.pay) AS total_payment,
         COUNT(DISTINCT o.order_id) AS order_count
  FROM olist_orders o
  JOIN olist_customers c ON c.customer_id = o.customer_id
  JOIN order_pay op ON op.order_id = o.order_id
  WHERE o.order_status = 'delivered'
  GROUP BY c.customer_city
),
bottom5 AS (
  SELECT * FROM city_stats
  ORDER BY total_payment ASC
  LIMIT 5
)
SELECT AVG(total_payment) AS avg_total_payment,
       AVG(order_count) AS avg_delivered_order_count
FROM bottom5