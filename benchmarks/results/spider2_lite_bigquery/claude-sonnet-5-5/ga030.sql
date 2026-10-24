WITH s AS (
  SELECT user_pseudo_id, PARSE_DATE('%Y%m%d', event_date) AS d
  FROM `firebase-public-project.analytics_153293282.events_*`
  WHERE event_name = 'session_start'
    AND _TABLE_SUFFIX BETWEEN '20180612' AND '20181003'
),
first_s AS (
  SELECT user_pseudo_id, MIN(d) AS fd
  FROM s
  GROUP BY user_pseudo_id
),
cohort AS (
  SELECT user_pseudo_id, DATE_TRUNC(fd, WEEK(MONDAY)) AS cw
  FROM first_s
  WHERE fd >= DATE '2018-07-02'
),
sizes AS (
  SELECT cw, COUNT(*) AS n
  FROM cohort
  GROUP BY cw
),
retained AS (
  SELECT c.cw, COUNT(DISTINCT c.user_pseudo_id) AS r
  FROM cohort c
  JOIN s ON s.user_pseudo_id = c.user_pseudo_id
  WHERE DATE_DIFF(DATE_TRUNC(s.d, WEEK(MONDAY)), c.cw, WEEK) = 4
  GROUP BY c.cw
)
SELECT FORMAT_DATE('%Y-%m-%d', sizes.cw) AS cohort_week
FROM sizes
LEFT JOIN retained USING (cw)
ORDER BY SAFE_DIVIDE(IFNULL(retained.r, 0), sizes.n) DESC
LIMIT 1