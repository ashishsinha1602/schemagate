WITH monthly AS (
  SELECT customer_id,
         date(txn_date, 'start of month') AS month_start,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount
                  WHEN txn_type = 'withdrawal' THEN -txn_amount
                  ELSE 0 END) AS net_amount
  FROM customer_transactions
  WHERE txn_type IN ('deposit', 'withdrawal')
  GROUP BY customer_id, date(txn_date, 'start of month')
),
balances AS (
  SELECT customer_id,
         month_start,
         SUM(net_amount) OVER (PARTITION BY customer_id ORDER BY month_start
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS closing_balance
  FROM monthly
),
with_prev AS (
  SELECT customer_id,
         month_start,
         closing_balance,
         LAG(closing_balance) OVER (PARTITION BY customer_id ORDER BY month_start) AS prev_balance,
         ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY month_start DESC) AS rn
  FROM balances
),
latest AS (
  SELECT customer_id,
         CASE WHEN prev_balance IS NULL THEN NULL
              WHEN prev_balance = 0 THEN closing_balance * 100.0
              ELSE (closing_balance - prev_balance) * 100.0 / prev_balance
         END AS growth_rate
  FROM with_prev
  WHERE rn = 1
)
SELECT 100.0 * SUM(CASE WHEN growth_rate > 5 THEN 1 ELSE 0 END) / COUNT(*) AS pct_customers_growth_over_5
FROM latest