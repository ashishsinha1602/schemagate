WITH cust AS (
  SELECT customer_id,
         MIN(payment_date) AS first_purchase,
         SUM(amount) AS ltv
  FROM payment
  GROUP BY customer_id
),
agg AS (
  SELECT c.customer_id,
         c.ltv,
         SUM(CASE WHEN (julianday(p.payment_date) - julianday(c.first_purchase)) * 24 < 7 * 24 THEN p.amount ELSE 0 END) AS sales_7,
         SUM(CASE WHEN (julianday(p.payment_date) - julianday(c.first_purchase)) * 24 < 30 * 24 THEN p.amount ELSE 0 END) AS sales_30
  FROM cust c
  JOIN payment p ON p.customer_id = c.customer_id
  WHERE c.ltv > 0
  GROUP BY c.customer_id, c.ltv
)
SELECT AVG(100.0 * sales_7 / ltv) AS avg_pct_first_7_days,
       AVG(100.0 * sales_30 / ltv) AS avg_pct_first_30_days,
       AVG(ltv) AS avg_ltv
FROM agg