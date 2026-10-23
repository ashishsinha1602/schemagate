WITH daily_volumes AS (
  SELECT
    ticker,
    market_date,
    CASE
      WHEN volume LIKE '%K' THEN CAST(REPLACE(volume, 'K', '') AS REAL) * 1000
      WHEN volume LIKE '%M' THEN CAST(REPLACE(volume, 'M', '') AS REAL) * 1000000
      WHEN volume = '-' THEN 0
      ELSE CAST(volume AS REAL)
    END AS current_volume
  FROM main.bitcoin_prices
  WHERE market_date BETWEEN '2021-08-01' AND '2021-08-10'
),
all_volumes_with_prev_non_zero AS (
  SELECT
    dv.ticker,
    dv.market_date,
    dv.current_volume,
    (SELECT dv2.current_volume
     FROM daily_volumes dv2
     WHERE dv2.ticker = dv.ticker
       AND dv2.market_date < dv.market_date
       AND dv2.current_volume > 0
     ORDER BY dv2.market_date DESC
     LIMIT 1) AS previous_non_zero_volume
  FROM daily_volumes dv
)
SELECT
  ticker,
  market_date,
  CASE
    WHEN previous_non_zero_volume IS NULL THEN NULL
    ELSE ((current_volume - previous_non_zero_volume) / previous_non_zero_volume) * 100
  END AS daily_percentage_change_volume
FROM all_volumes_with_prev_non_zero
ORDER BY ticker, market_date