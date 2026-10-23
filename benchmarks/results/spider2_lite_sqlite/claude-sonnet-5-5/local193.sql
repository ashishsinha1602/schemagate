WITH first_pay AS (
  SELECT customer_id, MIN(payment_date) AS first_date
  FROM payment
  GROUP BY customer_id
),
cust AS (
  SELECT p.customer_id,
         SUM(p.amount) AS ltv,
         SUM(CASE WHEN julianday(p.payment_date) - julianday(f.first_date) <= 7 THEN p.amount ELSE 0 END) AS s7,
         SUM(CASE WHEN julianday(p.payment_date) - julianday(f.first_date) <= 30 THEN p.amount ELSE 0 END) AS s30
  FROM payment p
  JOIN first_pay f ON f.customer_id = p.customer_id
  GROUP BY p.customer_id
  HAVING SUM(p.amount) > 0
)
SELECT AVG(s7 * 100.0 / ltv) AS avg_pct_first_7_days,
       AVG(s30 * 100.0 / ltv) AS avg_pct_first_30_days,
       AVG(ltv) AS avg_ltv
FROM cust