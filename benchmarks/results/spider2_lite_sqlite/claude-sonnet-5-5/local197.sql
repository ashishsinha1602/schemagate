WITH top_customers AS (
  SELECT customer_id, SUM(amount) AS total_paid
  FROM payment
  GROUP BY customer_id
  ORDER BY total_paid DESC
  LIMIT 10
),
monthly AS (
  SELECT p.customer_id, strftime('%Y-%m', p.payment_date) AS pay_month, SUM(p.amount) AS month_amt
  FROM payment p
  JOIN top_customers t ON t.customer_id = p.customer_id
  GROUP BY p.customer_id, strftime('%Y-%m', p.payment_date)
),
diffs AS (
  SELECT customer_id, pay_month,
         month_amt - LAG(month_amt) OVER (PARTITION BY customer_id ORDER BY pay_month) AS diff
  FROM monthly
)
SELECT c.customer_id, c.first_name, c.last_name, d.pay_month, ROUND(d.diff, 2) AS max_month_over_month_difference
FROM diffs d
JOIN customer c ON c.customer_id = d.customer_id
WHERE d.diff IS NOT NULL
ORDER BY ABS(d.diff) DESC
LIMIT 1