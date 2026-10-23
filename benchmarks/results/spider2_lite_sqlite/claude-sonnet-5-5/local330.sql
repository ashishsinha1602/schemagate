WITH r AS (
  SELECT
    session,
    path,
    ROW_NUMBER() OVER (PARTITION BY session ORDER BY stamp ASC, rowid ASC) AS rn_first,
    ROW_NUMBER() OVER (PARTITION BY session ORDER BY stamp DESC, rowid DESC) AS rn_last
  FROM main.activity_log
)
SELECT path, COUNT(DISTINCT session) AS session_count
FROM r
WHERE rn_first = 1 OR rn_last = 1
GROUP BY path