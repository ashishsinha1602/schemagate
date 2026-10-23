WITH FirstTargetEvent AS (
  SELECT
    session,
    MIN(stamp) AS first_event_stamp
  FROM main.activity_log
  WHERE
    path IN ('/detail', '/complete')
  GROUP BY
    session
), PreTargetEvents AS (
  SELECT
    al.session,
    al.stamp,
    al.path,
    al.search_type
  FROM main.activity_log AS al
  JOIN FirstTargetEvent AS fte
    ON al.session = fte.session
  WHERE
    al.stamp < fte.first_event_stamp
    AND al.search_type IS NOT NULL
    AND al.search_type != ''
), SessionCounts AS (
  SELECT
    session,
    COUNT(*) AS event_count
  FROM PreTargetEvents
  GROUP BY
    session
)
SELECT
  pte.session,
  pte.path,
  pte.search_type
FROM PreTargetEvents AS pte
JOIN SessionCounts AS sc
  ON pte.session = sc.session
WHERE
  sc.event_count = (
    SELECT
      MIN(event_count)
    FROM SessionCounts
  )
ORDER BY
  pte.session,
  pte.stamp