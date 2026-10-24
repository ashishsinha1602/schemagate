WITH h AS (
  SELECT
    fullVisitorId,
    visitId,
    hit.page.pagePath AS page,
    hit.time AS t,
    LEAD(hit.page.pagePath) OVER (PARTITION BY fullVisitorId, visitId ORDER BY hit.hitNumber) AS next_page,
    LEAD(hit.time) OVER (PARTITION BY fullVisitorId, visitId ORDER BY hit.hitNumber) AS next_time
  FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`, UNNEST(hits) AS hit
  WHERE _TABLE_SUFFIX BETWEEN '20170101' AND '20170131'
    AND trafficSource.campaign LIKE '%Data Share%'
    AND hit.type = 'PAGE'
)
SELECT
  next_page,
  COUNT(*) AS visits,
  MAX((next_time - t) / 1000) AS max_seconds_on_home
FROM h
WHERE page LIKE '/home%'
  AND next_page IS NOT NULL
GROUP BY next_page
ORDER BY visits DESC
LIMIT 1