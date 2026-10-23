WITH base AS (
  SELECT product_id, mth, qty,
         ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY mth) AS t
  FROM monthly_sales
  WHERE product_id IN (4160, 7790)
    AND mth >= '2016-01' AND mth < '2019-01'
),
cma AS (
  SELECT b.product_id, b.mth, b.t,
         b.qty * 1.0 / (
           ((SELECT AVG(b2.qty) FROM base b2 WHERE b2.product_id = b.product_id AND b2.t BETWEEN b.t - 5 AND b.t + 6)
          + (SELECT AVG(b3.qty) FROM base b3 WHERE b3.product_id = b.product_id AND b3.t BETWEEN b.t - 6 AND b.t + 5)) / 2.0
         ) AS ratio
  FROM base b
  WHERE b.t BETWEEN 7 AND 30
),
seas AS (
  SELECT product_id, CAST(SUBSTR(mth, 6, 2) AS INTEGER) AS m, AVG(ratio) AS si
  FROM cma
  GROUP BY product_id, CAST(SUBSTR(mth, 6, 2) AS INTEGER)
),
deseas AS (
  SELECT b.product_id, b.t, b.mth, s.si, b.qty * 1.0 / s.si AS y
  FROM base b
  JOIN seas s ON s.product_id = b.product_id AND s.m = CAST(SUBSTR(b.mth, 6, 2) AS INTEGER)
),
agg AS (
  SELECT product_id,
         COUNT(*) AS n,
         SUM(t) AS st,
         SUM(y) AS sy,
         SUM(t * y) AS sty,
         SUM(t * t) AS stt
  FROM deseas
  GROUP BY product_id
),
reg AS (
  SELECT product_id,
         (n * sty - st * sy) * 1.0 / (n * stt - st * st) AS slope,
         (sy - ((n * sty - st * sy) * 1.0 / (n * stt - st * st)) * st) / n AS intercept
  FROM agg
),
fc AS (
  SELECT d.product_id,
         SUM((r.intercept + r.slope * d.t) * d.si) AS annual_forecast
  FROM deseas d
  JOIN reg r ON r.product_id = d.product_id
  WHERE SUBSTR(d.mth, 1, 4) = '2018'
  GROUP BY d.product_id
)
SELECT AVG(annual_forecast) AS avg_forecast_annual_sales_2018
FROM fc