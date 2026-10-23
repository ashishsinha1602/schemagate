WITH monthly AS (
  SELECT customer_id,
         strftime('%Y-%m-01', txn_date) AS month_start,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS net
  FROM customer_transactions
  WHERE txn_type IN ('deposit', 'withdrawal')
  GROUP BY customer_id, strftime('%Y-%m-01', txn_date)
),
bal AS (
  SELECT customer_id, month_start,
         SUM(net) OVER (PARTITION BY customer_id ORDER BY month_start ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS closing_balance
  FROM monthly
),
w AS (
  SELECT customer_id, month_start, closing_balance,
         COALESCE(LAG(closing_balance) OVER (PARTITION BY customer_id ORDER BY month_start), 0) AS prev_balance,
         ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY month_start DESC) AS rn
  FROM bal
),
g AS (
  SELECT customer_id,
         CASE WHEN prev_balance = 0 THEN closing_balance * 100.0
              ELSE (closing_balance - prev_balance) * 100.0 / prev_balance END AS growth_rate
  FROM w
  WHERE rn = 1
)
SELECT 100.0 * SUM(CASE WHEN growth_rate > 5 THEN 1 ELSE 0 END) / COUNT(*) AS pct_customers_growth_over_5
FROM g