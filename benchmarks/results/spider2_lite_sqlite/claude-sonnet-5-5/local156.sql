WITH base AS (
  SELECT m.region,
         strftime('%Y', t.txn_date) AS yr,
         SUM(t.quantity * p.price) / SUM(t.quantity) AS avg_price
  FROM bitcoin_transactions t
  JOIN bitcoin_members m ON m.member_id = t.member_id
  JOIN bitcoin_prices p ON p.ticker = t.ticker AND p.market_date = t.txn_date
  WHERE t.ticker = 'BTC' AND t.txn_type = 'BUY'
  GROUP BY m.region, strftime('%Y', t.txn_date)
),
x AS (
  SELECT region, yr, avg_price,
         LAG(avg_price) OVER (PARTITION BY region ORDER BY yr) AS prev_price,
         MIN(yr) OVER (PARTITION BY region) AS first_yr
  FROM base
)
SELECT region,
       yr AS year,
       avg_price,
       RANK() OVER (PARTITION BY yr ORDER BY avg_price DESC) AS price_rank,
       (avg_price - prev_price) * 100.0 / prev_price AS pct_change
FROM x
WHERE yr > first_yr
ORDER BY yr, price_rank