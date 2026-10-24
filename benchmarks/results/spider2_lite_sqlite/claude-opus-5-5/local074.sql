WITH months AS (
  SELECT DISTINCT substr(txn_date, 1, 7) AS month
  FROM customer_transactions
),
customers AS (
  SELECT DISTINCT customer_id
  FROM customer_transactions
),
monthly AS (
  SELECT customer_id,
         substr(txn_date, 1, 7) AS month,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS monthly_change
  FROM customer_transactions
  GROUP BY customer_id, substr(txn_date, 1, 7)
),
grid AS (
  SELECT c.customer_id,
         m.month,
         COALESCE(mo.monthly_change, 0) AS monthly_change
  FROM customers c
  CROSS JOIN months m
  LEFT JOIN monthly mo
    ON mo.customer_id = c.customer_id
   AND mo.month = m.month
)
SELECT customer_id,
       month,
       monthly_change,
       SUM(monthly_change) OVER (
         PARTITION BY customer_id
         ORDER BY month
         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS closing_balance
FROM grid
ORDER BY customer_id, month