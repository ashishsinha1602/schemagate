WITH ranked AS (
  SELECT session, path,
         ROW_NUMBER() OVER (PARTITION BY session ORDER BY stamp ASC) AS rn_first,
         ROW_NUMBER() OVER (PARTITION BY session ORDER BY stamp DESC) AS rn_last
  FROM main.activity_log
),
landing_exit AS (
  SELECT session, path FROM ranked WHERE rn_first = 1
  UNION
  SELECT session, path FROM ranked WHERE rn_last = 1
)
SELECT path, COUNT(DISTINCT session) AS total_sessions
FROM landing_exit
GROUP BY path
ORDER BY total_sessions DESC