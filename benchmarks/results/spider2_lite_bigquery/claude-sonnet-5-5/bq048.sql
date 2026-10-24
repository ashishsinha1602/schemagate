WITH c AS (
  SELECT DATE(created_date) AS d, complaint_type, COUNT(*) AS cnt
  FROM `bigquery-public-data.new_york.311_service_requests`
  WHERE created_date >= TIMESTAMP('2011-01-01') AND created_date < TIMESTAMP('2021-01-01')
    AND complaint_type IS NOT NULL
  GROUP BY d, complaint_type
),
tot AS (
  SELECT d, SUM(cnt) AS total
  FROM c
  GROUP BY d
),
ty AS (
  SELECT complaint_type
  FROM c
  GROUP BY complaint_type
  HAVING SUM(cnt) > 3000
),
w AS (
  SELECT date AS d, AVG(SAFE_CAST(wdsp AS FLOAT64)) AS ws
  FROM `bigquery-public-data.noaa_gsod.gsod*`
  WHERE _TABLE_SUFFIX BETWEEN '2011' AND '2020'
    AND stn = '744860'
    AND SAFE_CAST(wdsp AS FLOAT64) IS NOT NULL
    AND SAFE_CAST(wdsp AS FLOAT64) < 999.9
  GROUP BY date
),
cr AS (
  SELECT c.complaint_type,
         ROUND(CORR(SAFE_DIVIDE(c.cnt, tot.total), w.ws), 4) AS correlation
  FROM c
  JOIN ty ON c.complaint_type = ty.complaint_type
  JOIN tot ON c.d = tot.d
  JOIN w ON c.d = w.d
  GROUP BY c.complaint_type
)
SELECT * FROM (
  SELECT complaint_type, correlation FROM cr WHERE correlation IS NOT NULL ORDER BY correlation DESC LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT complaint_type, correlation FROM cr WHERE correlation IS NOT NULL ORDER BY correlation ASC LIMIT 1
)