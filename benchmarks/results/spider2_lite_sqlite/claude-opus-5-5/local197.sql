WITH top_customers AS (
  SELECT customer_id, SUM(amount) AS total_paid
  FROM payment
  GROUP BY customer_id
  ORDER BY total_paid DESC
  LIMIT 10
),
monthly AS (
  SELECT p.customer_id,
         strftime('%Y-%m', p.payment_date) AS month,
         SUM(p.amount) AS month_total
  FROM payment p
  JOIN top_customers t ON t.customer_id = p.customer_id
  GROUP BY p.customer_id, strftime('%Y-%m', p.payment_date)
),
lagged AS (
  SELECT customer_id,
         month,
         month_total,
         LAG(month) OVER (PARTITION BY customer_id ORDER BY month) AS prev_month,
         LAG(month_total) OVER (PARTITION BY customer_id ORDER BY month) AS prev_total
  FROM monthly
)
SELECT l.customer_id,
       c.first_name,
       c.last_name,
       l.prev_month AS from_month,
       l.month AS to_month,
       ROUND(ABS(l.month_total - l.prev_total), 2) AS max_month_over_month_difference
FROM lagged l
JOIN customer c ON c.customer_id = l.customer_id
WHERE l.prev_month IS NOT NULL
  AND date(l.prev_month || '-01', '+1 month') = date(l.month || '-01')
ORDER BY ABS(l.month_total - l.prev_total) DESC
LIMIT 1