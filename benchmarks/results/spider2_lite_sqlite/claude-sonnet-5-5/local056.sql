WITH m AS (
  SELECT customer_id, strftime('%Y-%m', payment_date) AS ym, SUM(amount) AS total
  FROM payment
  GROUP BY customer_id, strftime('%Y-%m', payment_date)
),
d AS (
  SELECT customer_id, total - LAG(total) OVER (PARTITION BY customer_id ORDER BY ym) AS diff
  FROM m
)
SELECT c.first_name || ' ' || c.last_name AS full_name
FROM d
JOIN customer c ON c.customer_id = d.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name
HAVING AVG(d.diff) IS NOT NULL
ORDER BY AVG(d.diff) DESC
LIMIT 1