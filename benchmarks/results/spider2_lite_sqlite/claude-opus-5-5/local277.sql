WITH s1 AS (
  SELECT product_id,
         mth,
         qty,
         CAST(substr(mth, 6, 2) AS INTEGER) AS mthno,
         ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY mth) AS ts
  FROM monthly_sales
  WHERE product_id IN (4160, 7790)
    AND mth >= '2016-01'
),
s2 AS (
  SELECT s1.*,
         CASE WHEN ts BETWEEN 7 AND 30 THEN
           (AVG(qty) OVER (PARTITION BY product_id ORDER BY ts ROWS BETWEEN 5 PRECEDING AND 6 FOLLOWING)
          + AVG(qty) OVER (PARTITION BY product_id ORDER BY ts ROWS BETWEEN 6 PRECEDING AND 5 FOLLOWING)) / 2.0
         END AS cma
  FROM s1
  WHERE ts <= 36
),
s3 AS (
  SELECT s2.*,
         AVG(qty * 1.0 / cma) OVER (PARTITION BY product_id, mthno) AS seas
  FROM s2
),
s4 AS (
  SELECT s3.*,
         qty * 1.0 / seas AS des
  FROM s3
),
reg AS (
  SELECT product_id,
         (COUNT(*) * SUM(ts * des) - SUM(ts) * SUM(des))
           / (COUNT(*) * SUM(ts * ts) * 1.0 - SUM(ts) * SUM(ts)) AS slope,
         AVG(des) AS mdes,
         AVG(ts * 1.0) AS mts
  FROM s4
  GROUP BY product_id
),
fc AS (
  SELECT s4.product_id,
         SUM((r.mdes - r.slope * r.mts + r.slope * s4.ts) * s4.seas) AS yr_forecast
  FROM s4
  JOIN reg r ON r.product_id = s4.product_id
  WHERE s4.ts BETWEEN 25 AND 36
  GROUP BY s4.product_id
)
SELECT AVG(yr_forecast) AS avg_forecast_2018
FROM fc