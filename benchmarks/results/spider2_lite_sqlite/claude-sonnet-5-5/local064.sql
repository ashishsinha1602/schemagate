WITH m AS (
  SELECT customer_id,
         strftime('%m', txn_date) AS mth,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount WHEN txn_type = 'withdrawal' THEN -txn_amount ELSE 0 END) AS bal
  FROM customer_transactions
  WHERE strftime('%Y', txn_date) = '2020'
    AND txn_type IN ('deposit', 'withdrawal')
  GROUP BY customer_id, strftime('%m', txn_date)
),
s AS (
  SELECT mth, SUM(CASE WHEN bal > 0 THEN 1 ELSE 0 END) AS pos_cnt, AVG(bal) AS avg_bal
  FROM m
  GROUP BY mth
)
SELECT (SELECT avg_bal FROM s ORDER BY pos_cnt DESC, mth LIMIT 1)
     - (SELECT avg_bal FROM s ORDER BY pos_cnt ASC, mth LIMIT 1) AS avg_balance_difference