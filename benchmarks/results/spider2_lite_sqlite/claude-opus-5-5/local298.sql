WITH monthly_net AS (
  SELECT customer_id,
         strftime('%Y-%m', txn_date) AS month,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS net
  FROM customer_transactions
  GROUP BY customer_id, strftime('%Y-%m', txn_date)
),
months AS (
  SELECT DISTINCT month FROM monthly_net
),
customers AS (
  SELECT DISTINCT customer_id FROM customer_transactions
),
grid AS (
  SELECT c.customer_id, m.month, COALESCE(n.net, 0) AS net
  FROM customers c
  CROSS JOIN months m
  LEFT JOIN monthly_net n
    ON n.customer_id = c.customer_id AND n.month = m.month
),
balances AS (
  SELECT customer_id, month,
         SUM(net) OVER (PARTITION BY customer_id ORDER BY month
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS balance
  FROM grid
),
monthly_total AS (
  SELECT month,
         SUM(CASE WHEN balance < 0 THEN 0 ELSE balance END) AS total_balance
  FROM balances
  GROUP BY month
),
with_prev AS (
  SELECT month,
         LAG(total_balance) OVER (ORDER BY month) AS previous_month_total_balance
  FROM monthly_total
)
SELECT month, previous_month_total_balance
FROM with_prev
WHERE previous_month_total_balance IS NOT NULL
ORDER BY month