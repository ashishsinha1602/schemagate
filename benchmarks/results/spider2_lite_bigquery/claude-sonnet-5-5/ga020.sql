WITH ev AS (
  SELECT
    user_pseudo_id,
    event_name,
    event_timestamp,
    DATE(TIMESTAMP_MICROS(event_timestamp)) AS d
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20180612' AND '20181003'
    AND (event_name LIKE '%quickplay' OR event_name = 'session_start')
),
first_q AS (
  SELECT user_pseudo_id, event_name, d AS first_d
  FROM (
    SELECT
      user_pseudo_id,
      event_name,
      d,
      ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY event_timestamp) AS rn
    FROM ev
    WHERE event_name LIKE '%quickplay'
  )
  WHERE rn = 1
    AND d BETWEEN DATE '2018-08-01' AND DATE '2018-08-15'
),
retained AS (
  SELECT
    f.user_pseudo_id,
    f.event_name,
    LOGICAL_OR(s.d IS NOT NULL) AS is_retained
  FROM first_q f
  LEFT JOIN ev s
    ON s.user_pseudo_id = f.user_pseudo_id
   AND s.event_name = 'session_start'
   AND DATE_DIFF(s.d, f.first_d, DAY) BETWEEN 8 AND 14
  GROUP BY f.user_pseudo_id, f.event_name
)
SELECT event_name
FROM retained
GROUP BY event_name
ORDER BY SAFE_DIVIDE(COUNTIF(is_retained), COUNT(*)) ASC
LIMIT 1