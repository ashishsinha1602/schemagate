WITH m AS (
  SELECT `by` AS user_id, DATE_TRUNC(DATE(`timestamp`), MONTH) AS mon
  FROM `bigquery-public-data.hacker_news.full`
  WHERE `by` IS NOT NULL
    AND DATE(`timestamp`) <= DATE '2024-09-10'
  GROUP BY 1, 2
),
u AS (
  SELECT user_id, MIN(mon) AS first_m, MAX(mon) AS last_m, COUNT(*) AS active_months
  FROM m
  GROUP BY user_id
)
SELECT user_id, DATE_DIFF(last_m, first_m, MONTH) AS month_number
FROM u
WHERE active_months < DATE_DIFF(last_m, first_m, MONTH) + 1
ORDER BY month_number DESC
LIMIT 1