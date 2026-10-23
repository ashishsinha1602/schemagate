WITH FirstConversionTime AS (
  SELECT
    session,
    MIN(stamp) AS first_conversion_stamp
  FROM
    main.activity_log
  WHERE
    path IN ('/detail', '/complete')
  GROUP BY
    session
),
PreConversionEvents AS (
  SELECT
    al.session,
    al.stamp,
    al.path,
    al.search_type
  FROM
    main.activity_log AS al
  INNER JOIN
    FirstConversionTime AS fct
    ON al.session = fct.session
  WHERE
    al.stamp < fct.first_conversion_stamp
    AND al.search_type IS NOT NULL
    AND al.search_type != ''
),
SessionEventCounts AS (
  SELECT
    fct.session,
    COUNT(pce.session) AS event_count
  FROM
    FirstConversionTime AS fct
  LEFT JOIN
    PreConversionEvents AS pce
    ON fct.session = pce.session
  GROUP BY
    fct.session
),
MinEventCount AS (
  SELECT
    MIN(event_count) AS min_count
  FROM
    SessionEventCounts
)
SELECT
  pce.session,
  pce.path,
  pce.search_type
FROM
  PreConversionEvents AS pce
INNER JOIN
  SessionEventCounts AS sec
  ON pce.session = sec.session
INNER JOIN
  MinEventCount AS mec
  ON sec.event_count = mec.min_count
ORDER BY
  pce.session, pce.stamp