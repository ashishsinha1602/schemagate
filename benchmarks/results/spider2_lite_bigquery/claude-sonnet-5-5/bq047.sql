WITH weather AS (
  SELECT date, AVG(temp) AS temp
  FROM `bigquery-public-data.noaa_gsod.gsod*`
  WHERE _TABLE_SUFFIX BETWEEN '2008' AND '2017'
    AND stn IN ('725030', '744860')
    AND temp IS NOT NULL
    AND temp != 9999.9
  GROUP BY date
),
daily_type AS (
  SELECT DATE(created_date) AS d, complaint_type, COUNT(*) AS cnt
  FROM `bigquery-public-data.new_york.311_service_requests`
  WHERE DATE(created_date) BETWEEN DATE '2008-01-01' AND DATE '2017-12-31'
    AND complaint_type IS NOT NULL
  GROUP BY d, complaint_type
),
daily_total AS (
  SELECT d, SUM(cnt) AS total_cnt
  FROM daily_type
  GROUP BY d
),
joined AS (
  SELECT t.complaint_type, t.d, t.cnt, w.temp,
         SAFE_DIVIDE(t.cnt, dt.total_cnt) * 100 AS pct
  FROM daily_type t
  JOIN daily_total dt ON t.d = dt.d
  JOIN weather w ON t.d = w.date
),
stats AS (
  SELECT complaint_type,
         SUM(cnt) AS total_complaints,
         COUNT(DISTINCT d) AS total_days,
         ROUND(CORR(temp, cnt), 4) AS corr_count,
         ROUND(CORR(temp, pct), 4) AS corr_pct
  FROM joined
  GROUP BY complaint_type
)
SELECT complaint_type, total_complaints, total_days, corr_count, corr_pct
FROM stats
WHERE total_complaints > 5000
  AND (ABS(corr_count) > 0.5 OR ABS(corr_pct) > 0.5)
ORDER BY complaint_type