WITH txn AS (
  SELECT
    t.member_id,
    t.ticker,
    t.quantity,
    CASE WHEN substr(t.txn_date, 5, 1) = '-' THEN t.txn_date
         ELSE substr(t.txn_date, 7, 4) || '-' || substr(t.txn_date, 4, 2) || '-' || substr(t.txn_date, 1, 2)
    END AS norm_date
  FROM bitcoin_transactions t
  WHERE t.ticker = 'BTC' AND t.txn_type = 'BUY'
),
prices AS (
  SELECT
    p.ticker,
    p.price,
    CASE WHEN substr(p.market_date, 5, 1) = '-' THEN p.market_date
         ELSE substr(p.market_date, 7, 4) || '-' || substr(p.market_date, 4, 2) || '-' || substr(p.market_date, 1, 2)
    END AS norm_date
  FROM bitcoin_prices p
  WHERE p.ticker = 'BTC'
),
yearly AS (
  SELECT
    m.region,
    CAST(substr(x.norm_date, 1, 4) AS INTEGER) AS txn_year,
    SUM(x.quantity * pr.price) AS total_spent,
    SUM(x.quantity) AS total_qty,
    SUM(x.quantity * pr.price) / SUM(x.quantity) AS avg_price
  FROM txn x
  JOIN prices pr ON pr.ticker = x.ticker AND pr.norm_date = x.norm_date
  JOIN bitcoin_members m ON m.member_id = x.member_id
  GROUP BY m.region, CAST(substr(x.norm_date, 1, 4) AS INTEGER)
),
with_lag AS (
  SELECT
    region,
    txn_year,
    avg_price,
    LAG(avg_price) OVER (PARTITION BY region ORDER BY txn_year) AS prev_avg_price,
    MIN(txn_year) OVER (PARTITION BY region) AS first_year
  FROM yearly
)
SELECT
  region,
  txn_year,
  avg_price,
  RANK() OVER (PARTITION BY txn_year ORDER BY avg_price DESC) AS price_rank,
  CASE WHEN prev_avg_price IS NULL OR prev_avg_price = 0 THEN NULL
       ELSE 100.0 * (avg_price - prev_avg_price) / prev_avg_price
  END AS pct_change
FROM with_lag
WHERE txn_year > first_year
ORDER BY txn_year, price_rank