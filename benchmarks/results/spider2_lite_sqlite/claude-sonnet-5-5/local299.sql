WITH RECURSIVE bounds AS (
  SELECT customer_id, MIN(txn_date) AS mn, MAX(txn_date) AS mx
  FROM customer_transactions
  GROUP BY customer_id
),
cal AS (
  SELECT customer_id, mn AS d, mx FROM bounds
  UNION ALL
  SELECT customer_id, date(d, '+1 day'), mx FROM cal WHERE d < mx
),
daily AS (
  SELECT customer_id, txn_date,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS amt
  FROM customer_transactions
  GROUP BY customer_id, txn_date
),
bal AS (
  SELECT c.customer_id, c.d,
         SUM(COALESCE(dl.amt, 0)) OVER (PARTITION BY c.customer_id ORDER BY c.d ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS balance,
         ROW_NUMBER() OVER (PARTITION BY c.customer_id ORDER BY c.d) AS rn
  FROM cal c
  LEFT JOIN daily dl ON dl.customer_id = c.customer_id AND dl.txn_date = c.d
),
roll AS (
  SELECT customer_id, d, rn,
         AVG(balance) OVER (PARTITION BY customer_id ORDER BY d ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS avg30
  FROM bal
),
monthly AS (
  SELECT r.customer_id,
         strftime('%Y-%m', r.d) AS month,
         MAX(MAX(r.avg30, 0)) AS max_avg
  FROM roll r
  WHERE r.rn >= 30
  GROUP BY r.customer_id, strftime('%Y-%m', r.d)
)
SELECT m.month, SUM(m.max_avg) AS total_max_30day_avg_balance
FROM monthly m
JOIN bounds b ON b.customer_id = m.customer_id
WHERE m.month > strftime('%Y-%m', b.mn)
GROUP BY m.month
ORDER BY m.month