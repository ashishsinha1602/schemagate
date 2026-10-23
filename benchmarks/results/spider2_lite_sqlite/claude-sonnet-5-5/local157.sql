WITH c AS (
  SELECT ticker,
         substr(market_date,7,4)||'-'||substr(market_date,4,2)||'-'||substr(market_date,1,2) AS d,
         CASE
           WHEN volume = '-' THEN 0
           WHEN volume LIKE '%K' THEN CAST(replace(substr(volume,1,length(volume)-1),',','') AS REAL) * 1000
           WHEN volume LIKE '%M' THEN CAST(replace(substr(volume,1,length(volume)-1),',','') AS REAL) * 1000000
           ELSE CAST(replace(volume,',','') AS REAL)
         END AS vol
  FROM bitcoin_prices
),
f AS (
  SELECT ticker, d, vol,
         LAG(vol) OVER (PARTITION BY ticker ORDER BY d) AS prev_vol
  FROM c
  WHERE d BETWEEN '2021-08-01' AND '2021-08-10' AND vol > 0
)
SELECT ticker, d AS market_date, vol AS volume, prev_vol AS previous_volume,
       (vol - prev_vol) * 100.0 / prev_vol AS pct_change
FROM f
ORDER BY ticker, d