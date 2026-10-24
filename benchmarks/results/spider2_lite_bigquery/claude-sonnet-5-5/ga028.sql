WITH ev AS (
  SELECT user_pseudo_id, event_name, PARSE_DATE('%Y%m%d', event_date) AS d
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20180612' AND '20181002'
),
cohort AS (
  SELECT user_pseudo_id
  FROM ev
  WHERE event_name = 'session_start'
  GROUP BY user_pseudo_id
  HAVING DATE_TRUNC(MIN(d), WEEK(MONDAY)) = DATE '2018-07-02'
),
activity AS (
  SELECT DISTINCT
    e.user_pseudo_id,
    DATE_DIFF(DATE_TRUNC(e.d, WEEK(MONDAY)), DATE '2018-07-02', WEEK) AS week_number
  FROM ev e
  JOIN cohort c ON e.user_pseudo_id = c.user_pseudo_id
  WHERE e.d >= DATE '2018-07-02'
)
SELECT
  week_number,
  COUNT(DISTINCT user_pseudo_id) AS users
FROM activity
WHERE week_number BETWEEN 0 AND 4
GROUP BY week_number
ORDER BY week_number