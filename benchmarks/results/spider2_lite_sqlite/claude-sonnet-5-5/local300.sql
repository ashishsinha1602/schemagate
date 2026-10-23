WITH RECURSIVE net AS (
  SELECT customer_id, txn_date,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS amt
  FROM customer_transactions
  GROUP BY customer_id, txn_date
),
bounds AS (
  SELECT customer_id, MIN(txn_date) AS mn, MAX(txn_date) AS mx
  FROM customer_transactions
  GROUP BY customer_id
),
days AS (
  SELECT customer_id, mn AS d, mx FROM bounds
  UNION ALL
  SELECT customer_id, date(d, '+1 day'), mx FROM days WHERE d < mx
),
bal AS (
  SELECT days.customer_id, days.d,
         SUM(COALESCE(net.amt, 0)) OVER (PARTITION BY days.customer_id ORDER BY days.d) AS b
  FROM days
  LEFT JOIN net ON net.customer_id = days.customer_id AND net.txn_date = days.d
),
monthly AS (
  SELECT customer_id, strftime('%Y-%m', d) AS m, MAX(MAX(b, 0)) AS mb
  FROM bal
  GROUP BY customer_id, strftime('%Y-%m', d)
)
SELECT m AS month, SUM(mb) AS total_max_daily_balance
FROM monthly
GROUP BY m
ORDER BY m