WITH first_ev AS (
  SELECT session, MIN(stamp) AS first_stamp
  FROM activity_log
  WHERE path LIKE '%/detail%' OR path LIKE '%/complete%'
  GROUP BY session
),
cnt AS (
  SELECT f.session, f.first_stamp,
    (SELECT COUNT(*) FROM activity_log a
     WHERE a.session = f.session
       AND a.stamp < f.first_stamp
       AND a.search_type IS NOT NULL
       AND a.search_type <> '') AS c
  FROM first_ev f
)
SELECT c.session, a.path, a.search_type
FROM cnt c
JOIN activity_log a
  ON a.session = c.session
 AND a.stamp = c.first_stamp
 AND (a.path LIKE '%/detail%' OR a.path LIKE '%/complete%')
WHERE c.c = (SELECT MIN(c) FROM cnt)