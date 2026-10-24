WITH u AS (
  SELECT
    user_pseudo_id,
    MIN(DATE(TIMESTAMP_MICROS(user_first_touch_timestamp))) AS first_open_date,
    MIN(IF(event_name = 'app_remove', DATE(TIMESTAMP_MICROS(event_timestamp)), NULL)) AS uninstall_date,
    LOGICAL_OR(event_name = 'app_exception') AS crashed
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20180901' AND '20181003'
  GROUP BY user_pseudo_id
)
SELECT
  100 * SAFE_DIVIDE(COUNTIF(crashed), COUNT(*)) AS crash_percentage
FROM u
WHERE first_open_date BETWEEN DATE '2018-09-01' AND DATE '2018-09-30'
  AND uninstall_date IS NOT NULL
  AND DATE_DIFF(uninstall_date, first_open_date, DAY) BETWEEN 0 AND 7