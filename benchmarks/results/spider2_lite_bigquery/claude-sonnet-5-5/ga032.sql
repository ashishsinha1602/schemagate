WITH pv AS (
  SELECT
    event_timestamp,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location') AS url,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_title') AS title
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX = '20210128'
    AND event_name = 'page_view'
    AND user_pseudo_id = '1362228.4966015575'
),
parts AS (
  SELECT
    event_timestamp,
    title,
    SPLIT(SPLIT(url, '?')[OFFSET(0)], '/') AS p
  FROM pv
),
segs AS (
  SELECT
    event_timestamp,
    title,
    ARRAY_LENGTH(p) AS n,
    LOWER(REPLACE(IFNULL(p[SAFE_OFFSET(3)], ''), '+', ' ')) AS s4,
    LOWER(REPLACE(IFNULL(p[SAFE_OFFSET(4)], ''), '+', ' ')) AS s5,
    IFNULL(p[SAFE_OFFSET(ARRAY_LENGTH(p) - 1)], '') AS last_seg
  FROM parts
),
cls AS (
  SELECT
    event_timestamp,
    title,
    n,
    last_seg,
    (s4 IN UNNEST(['accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables'])
     OR s5 IN UNNEST(['accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables'])) AS has_cat
  FROM segs
),
pages AS (
  SELECT
    event_timestamp,
    CASE
      WHEN n >= 5 AND has_cat AND STRPOS(last_seg, '+') > 0 THEN 'PDP'
      WHEN n >= 5 AND has_cat AND STRPOS(last_seg, '+') = 0 THEN 'PLP'
      ELSE title
    END AS page
  FROM cls
),
dedup AS (
  SELECT
    event_timestamp,
    page,
    LAG(page) OVER (ORDER BY event_timestamp) AS prev_page
  FROM pages
)
SELECT STRING_AGG(page, '>>' ORDER BY event_timestamp) AS navigation_flow
FROM dedup
WHERE prev_page IS NULL OR page IS DISTINCT FROM prev_page