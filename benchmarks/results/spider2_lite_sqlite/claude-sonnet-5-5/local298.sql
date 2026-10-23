WITH tx AS (
  SELECT customer_id,
         strftime('%Y-%m-01', txn_date) AS month,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS net
  FROM customer_transactions
  GROUP BY customer_id, strftime('%Y-%m-01', txn_date)
),
months AS (
  SELECT DISTINCT month FROM tx
),
custs AS (
  SELECT DISTINCT customer_id FROM tx
),
grid AS (
  SELECT c.customer_id, m.month, COALESCE(t.net, 0) AS net
  FROM custs c
  CROSS JOIN months m
  LEFT JOIN tx t ON t.customer_id = c.customer_id AND t.month = m.month
),
bal AS (
  SELECT customer_id, month,
         SUM(net) OVER (PARTITION BY customer_id ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS balance
  FROM grid
),
tot AS (
  SELECT month, SUM(CASE WHEN balance < 0 THEN 0 ELSE balance END) AS total_balance
  FROM bal
  GROUP BY month
),
lagged AS (
  SELECT month,
         LAG(total_balance) OVER (ORDER BY month) AS previous_total_balance,
         ROW_NUMBER() OVER (ORDER BY month) AS rn
  FROM tot
)
SELECT month, previous_total_balance
FROM lagged
WHERE rn > 1
ORDER BY month