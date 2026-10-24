WITH sessions AS (
  SELECT
    user_pseudo_id,
    PARSE_DATE('%Y%m%d', event_date) AS d,
    DATE(TIMESTAMP_MICROS(user_first_touch_timestamp)) AS ft
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE event_name = 'session_start'
    AND _TABLE_SUFFIX BETWEEN '20180709' AND '20181002'
),
cohort AS (
  SELECT
    user_pseudo_id,
    DATE_TRUNC(MIN(d), WEEK(MONDAY)) AS cohort_week
  FROM sessions
  WHERE d = ft
  GROUP BY user_pseudo_id
),
activity AS (
  SELECT DISTINCT
    user_pseudo_id,
    DATE_TRUNC(d, WEEK(MONDAY)) AS wk
  FROM sessions
)
SELECT
  c.cohort_week,
  100 * SAFE_DIVIDE(
    COUNT(DISTINCT IF(a.wk = DATE_ADD(c.cohort_week, INTERVAL 2 WEEK), c.user_pseudo_id, NULL)),
    COUNT(DISTINCT c.user_pseudo_id)
  ) AS week_2_retention_rate
FROM cohort c
LEFT JOIN activity a
  ON a.user_pseudo_id = c.user_pseudo_id
WHERE c.cohort_week BETWEEN DATE '2018-07-09' AND DATE '2018-09-17'
GROUP BY c.cohort_week
ORDER BY c.cohort_week