WITH monthly AS (
  SELECT customer_id,
         substr(txn_date, 1, 7) AS month,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount
                  WHEN txn_type = 'withdrawal' THEN -txn_amount
                  ELSE 0 END) AS balance
  FROM customer_transactions
  WHERE substr(txn_date, 1, 4) = '2020'
  GROUP BY customer_id, substr(txn_date, 1, 7)
),
month_stats AS (
  SELECT month,
         SUM(CASE WHEN balance > 0 THEN 1 ELSE 0 END) AS positive_count,
         AVG(balance) AS avg_balance
  FROM monthly
  GROUP BY month
),
max_month AS (
  SELECT month, avg_balance FROM month_stats
  ORDER BY positive_count DESC, month LIMIT 1
),
min_month AS (
  SELECT month, avg_balance FROM month_stats
  ORDER BY positive_count ASC, month LIMIT 1
)
SELECT mx.month AS highest_positive_month,
       mx.avg_balance AS highest_month_avg_balance,
       mn.month AS lowest_positive_month,
       mn.avg_balance AS lowest_month_avg_balance,
       mx.avg_balance - mn.avg_balance AS avg_balance_difference
FROM max_month mx CROSS JOIN min_month mn