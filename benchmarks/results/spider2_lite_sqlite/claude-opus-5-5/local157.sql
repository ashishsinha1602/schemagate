WITH converted AS (
  SELECT
    ticker,
    substr(market_date, 7, 4) || '-' || substr(market_date, 4, 2) || '-' || substr(market_date, 1, 2) AS dt,
    CASE
      WHEN volume = '-' THEN 0
      WHEN volume LIKE '%K' THEN CAST(REPLACE(SUBSTR(volume, 1, LENGTH(volume) - 1), ',', '') AS REAL) * 1000
      WHEN volume LIKE '%M' THEN CAST(REPLACE(SUBSTR(volume, 1, LENGTH(volume) - 1), ',', '') AS REAL) * 1000000
      ELSE CAST(REPLACE(volume, ',', '') AS REAL)
    END AS vol
  FROM main.bitcoin_prices
),
nonzero AS (
  SELECT
    ticker,
    dt,
    vol,
    LAG(vol) OVER (PARTITION BY ticker ORDER BY dt) AS prev_vol
  FROM converted
  WHERE vol > 0
)
SELECT
  ticker,
  dt AS market_date,
  vol AS volume,
  prev_vol AS previous_volume,
  ROUND((vol - prev_vol) * 100.0 / prev_vol, 2) AS volume_pct_change
FROM nonzero
WHERE dt BETWEEN '2021-08-01' AND '2021-08-10'
ORDER BY ticker, dt