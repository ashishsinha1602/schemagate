WITH monthly AS (
  SELECT customer_id,
         strftime('%Y-%m-01', txn_date) AS month_start,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS monthly_change
  FROM customer_transactions
  GROUP BY customer_id, strftime('%Y-%m-01', txn_date)
),
bounds AS (
  SELECT MIN(month_start) AS mn, MAX(month_start) AS mx FROM monthly
),
months(m) AS (
  SELECT mn FROM bounds
  UNION ALL
  SELECT date(months.m, '+1 month') FROM months, bounds WHERE months.m < bounds.mx
),
customers AS (
  SELECT DISTINCT customer_id FROM customer_transactions
)
SELECT c.customer_id,
       months.m AS month_start,
       COALESCE(mo.monthly_change, 0) AS monthly_change,
       SUM(COALESCE(mo.monthly_change, 0)) OVER (PARTITION BY c.customer_id ORDER BY months.m) AS closing_balance
FROM customers c
CROSS JOIN months
LEFT JOIN monthly mo ON mo.customer_id = c.customer_id AND mo.month_start = months.m
ORDER BY c.customer_id, months.m