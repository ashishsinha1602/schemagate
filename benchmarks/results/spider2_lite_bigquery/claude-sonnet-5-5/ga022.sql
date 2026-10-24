WITH ev AS (
  SELECT
    user_pseudo_id,
    event_name,
    DATE(TIMESTAMP_MICROS(event_timestamp), 'Asia/Shanghai') AS d
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20180831' AND '20181003'
),
cohort AS (
  SELECT DISTINCT user_pseudo_id
  FROM ev
  WHERE event_name = 'first_open'
    AND d BETWEEN DATE '2018-09-01' AND DATE '2018-09-07'
),
activity AS (
  SELECT DISTINCT
    e.user_pseudo_id,
    DIV(DATE_DIFF(e.d, DATE '2018-09-01', DAY), 7) AS week_idx
  FROM ev e
  JOIN cohort c USING (user_pseudo_id)
  WHERE e.d >= DATE '2018-09-08'
)
SELECT
  SAFE_DIVIDE(COUNT(DISTINCT IF(a.week_idx = 1, a.user_pseudo_id, NULL)), (SELECT COUNT(*) FROM cohort)) AS week_1_retention,
  SAFE_DIVIDE(COUNT(DISTINCT IF(a.week_idx = 2, a.user_pseudo_id, NULL)), (SELECT COUNT(*) FROM cohort)) AS week_2_retention,
  SAFE_DIVIDE(COUNT(DISTINCT IF(a.week_idx = 3, a.user_pseudo_id, NULL)), (SELECT COUNT(*) FROM cohort)) AS week_3_retention
FROM activity a