WITH RECURSIVE daily_net AS (
  SELECT customer_id,
         txn_date,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS net_amount
  FROM main.customer_transactions
  GROUP BY customer_id, txn_date
),
bounds AS (
  SELECT customer_id,
         MIN(txn_date) AS start_date,
         MAX(txn_date) AS end_date
  FROM main.customer_transactions
  GROUP BY customer_id
),
calendar AS (
  SELECT customer_id, date(start_date) AS d, date(end_date) AS end_date
  FROM bounds
  UNION ALL
  SELECT customer_id, date(d, '+1 day'), end_date
  FROM calendar
  WHERE d < end_date
),
balances AS (
  SELECT c.customer_id,
         c.d,
         SUM(COALESCE(n.net_amount, 0)) OVER (
           PARTITION BY c.customer_id
           ORDER BY c.d
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS running_balance
  FROM calendar c
  LEFT JOIN daily_net n
    ON n.customer_id = c.customer_id
   AND date(n.txn_date) = c.d
),
adjusted AS (
  SELECT customer_id,
         d,
         CASE WHEN running_balance < 0 THEN 0 ELSE running_balance END AS daily_balance
  FROM balances
),
monthly_max AS (
  SELECT customer_id,
         strftime('%Y-%m', d) AS month,
         MAX(daily_balance) AS max_daily_balance
  FROM adjusted
  GROUP BY customer_id, strftime('%Y-%m', d)
)
SELECT month,
       SUM(max_daily_balance) AS monthly_total
FROM monthly_max
GROUP BY month
ORDER BY month