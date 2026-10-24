WITH first_hit AS (
  SELECT session, MIN(stamp) AS first_stamp
  FROM main.activity_log
  WHERE path LIKE '/detail%' OR path LIKE '/complete%'
  GROUP BY session
),
pre_events AS (
  SELECT a.session, a.path, a.search_type
  FROM main.activity_log a
  JOIN first_hit f ON a.session = f.session
  WHERE a.stamp < f.first_stamp
    AND a.search_type IS NOT NULL
    AND a.search_type <> ''
),
counts AS (
  SELECT session, COUNT(*) AS cnt
  FROM pre_events
  GROUP BY session
)
SELECT p.session, p.path, p.search_type
FROM pre_events p
JOIN counts c ON p.session = c.session
WHERE c.cnt = (SELECT MIN(cnt) FROM counts)
ORDER BY p.session