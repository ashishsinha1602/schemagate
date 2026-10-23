WITH SessionFirstLastPage AS (
  SELECT DISTINCT
    session,
    FIRST_VALUE(path) OVER (PARTITION BY session ORDER BY stamp ASC) AS landing_page,
    FIRST_VALUE(path) OVER (PARTITION BY session ORDER BY stamp DESC) AS exit_page
  FROM main.activity_log
)
SELECT
  path,
  COUNT(DISTINCT session) AS unique_sessions_count
FROM (
  SELECT landing_page AS path, session FROM SessionFirstLastPage
  UNION ALL
  SELECT exit_page AS path, session FROM SessionFirstLastPage
) AS CombinedPages
GROUP BY path