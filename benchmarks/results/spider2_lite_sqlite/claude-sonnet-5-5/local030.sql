WITH city_totals AS (
  SELECT c.customer_city AS city,
         SUM(p.payment_value) AS total_payment,
         COUNT(DISTINCT o.order_id) AS delivered_orders
  FROM olist_orders o
  JOIN olist_customers c ON c.customer_id = o.customer_id
  JOIN olist_order_payments p ON p.order_id = o.order_id
  WHERE o.order_status = 'delivered'
  GROUP BY c.customer_city
),
lowest5 AS (
  SELECT city, total_payment, delivered_orders
  FROM city_totals
  ORDER BY total_payment ASC
  LIMIT 5
)
SELECT AVG(total_payment) AS avg_total_payment,
       AVG(delivered_orders) AS avg_delivered_order_count
FROM lowest5