WITH
  session_paths AS (
    SELECT
      session,
      path,
      stamp,
      ROW_NUMBER() OVER (PARTITION BY session ORDER BY stamp) AS rn
    FROM main.activity_log
  ),
  consecutive_details AS (
    SELECT
      s1.session,
      s2.rn AS second_detail_rn
    FROM session_paths AS s1
    JOIN session_paths AS s2
      ON s1.session = s2.session
      AND s1.rn + 1 = s2.rn
    WHERE
      s1.path = '/detail' AND s2.path = '/detail'
  )
SELECT
  sp3.path,
  COUNT(*) AS visit_count
FROM consecutive_details AS cd
JOIN session_paths AS sp3
  ON cd.session = sp3.session
  AND cd.second_detail_rn + 1 = sp3.rn
GROUP BY
  sp3.path
ORDER BY
  visit_count DESC
LIMIT 3