WITH session_users AS (
  SELECT DISTINCT user_pseudo_id
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20180702' AND '20180716'
    AND event_name = 'session_start'
),
first_quickplay AS (
  SELECT
    user_pseudo_id,
    event_name,
    MIN(PARSE_DATE('%Y%m%d', event_date)) AS first_date
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20180702' AND '20180716'
    AND event_name LIKE '%quickplay%'
    AND user_pseudo_id IN (SELECT user_pseudo_id FROM session_users)
  GROUP BY user_pseudo_id, event_name
),
activity AS (
  SELECT DISTINCT
    user_pseudo_id,
    PARSE_DATE('%Y%m%d', event_date) AS activity_date
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20180702' AND '20180730'
)
SELECT
  f.event_name,
  SAFE_DIVIDE(
    COUNT(DISTINCT IF(a.user_pseudo_id IS NOT NULL, f.user_pseudo_id, NULL)),
    COUNT(DISTINCT f.user_pseudo_id)
  ) AS retention_rate
FROM first_quickplay f
LEFT JOIN activity a
  ON a.user_pseudo_id = f.user_pseudo_id
  AND a.activity_date BETWEEN DATE_ADD(f.first_date, INTERVAL 8 DAY) AND DATE_ADD(f.first_date, INTERVAL 14 DAY)
GROUP BY f.event_name