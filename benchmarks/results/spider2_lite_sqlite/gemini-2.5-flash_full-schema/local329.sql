WITH PageVisits AS (
  SELECT
    session,
    path,
    stamp
  FROM main.form_log
  UNION ALL
  SELECT
    session,
    path,
    stamp
  FROM main.activity_log
  UNION ALL
  SELECT
    session,
    url AS path,
    stamp
  FROM main.read_log
)
SELECT
  COUNT(DISTINCT t1.session)
FROM PageVisits AS t1
JOIN PageVisits AS t2
  ON t1.session = t2.session
WHERE
  t1.path = '/regist/input' AND t2.path = '/regist/confirm' AND t1.stamp < t2.stamp