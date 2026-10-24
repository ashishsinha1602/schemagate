WITH monthly AS (
  SELECT customer_id,
         strftime('%Y-%m', payment_date) AS ym,
         SUM(amount) AS total_amount
  FROM payment
  GROUP BY customer_id, strftime('%Y-%m', payment_date)
),
changes AS (
  SELECT customer_id,
         total_amount - LAG(total_amount) OVER (PARTITION BY customer_id ORDER BY ym) AS diff
  FROM monthly
),
avg_changes AS (
  SELECT customer_id, AVG(diff) AS avg_change
  FROM changes
  WHERE diff IS NOT NULL
  GROUP BY customer_id
)
SELECT c.first_name || ' ' || c.last_name AS full_name
FROM avg_changes a
JOIN customer c ON c.customer_id = a.customer_id
ORDER BY a.avg_change DESC
LIMIT 1