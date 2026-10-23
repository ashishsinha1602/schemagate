WITH s AS (
  SELECT session, stamp, path,
         LAG(path, 1) OVER (PARTITION BY session ORDER BY stamp) AS prev1,
         LAG(path, 2) OVER (PARTITION BY session ORDER BY stamp) AS prev2
  FROM activity_log
  WHERE path IS NOT NULL
)
SELECT path AS third_page, COUNT(*) AS visit_count
FROM s
WHERE prev1 = '/detail' AND prev2 = '/detail'
GROUP BY path
ORDER BY visit_count DESC
LIMIT 3