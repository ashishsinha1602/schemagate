WITH RECURSIVE bounds AS (
  SELECT customer_id, MIN(txn_date) AS s, MAX(txn_date) AS e
  FROM customer_transactions
  GROUP BY customer_id
),
days(customer_id, d, e) AS (
  SELECT customer_id, date(s), date(e) FROM bounds
  UNION ALL
  SELECT customer_id, date(d, '+1 day'), e FROM days WHERE d < e
),
net AS (
  SELECT customer_id, date(txn_date) AS txn_date,
         SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE -txn_amount END) AS amt
  FROM customer_transactions
  GROUP BY customer_id, date(txn_date)
),
bal AS (
  SELECT d.customer_id, d.d,
         SUM(COALESCE(n.amt, 0)) OVER (PARTITION BY d.customer_id ORDER BY d.d
                                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS balance
  FROM days d
  LEFT JOIN net n ON n.customer_id = d.customer_id AND n.txn_date = d.d
),
roll_raw AS (
  SELECT customer_id, d,
         ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY d) AS rn,
         AVG(balance) OVER (PARTITION BY customer_id ORDER BY d
                            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS avg30
  FROM bal
),
roll AS (
  SELECT customer_id, d,
         CASE WHEN avg30 < 0 THEN 0 ELSE avg30 END AS ra
  FROM roll_raw
  WHERE rn >= 30
),
first_month AS (
  SELECT customer_id, strftime('%Y-%m', s) AS fm FROM bounds
),
monthly_max AS (
  SELECT r.customer_id, strftime('%Y-%m', r.d) AS month, MAX(r.ra) AS max_avg
  FROM roll r
  GROUP BY r.customer_id, strftime('%Y-%m', r.d)
)
SELECT m.month, SUM(m.max_avg) AS total_max_30day_avg_balance
FROM monthly_max m
JOIN first_month f ON f.customer_id = m.customer_id
WHERE m.month <> f.fm
GROUP BY m.month
ORDER BY m.month