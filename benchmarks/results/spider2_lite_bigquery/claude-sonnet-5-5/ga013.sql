WITH pv AS (
  SELECT
    event_timestamp,
    (SELECT ep.value.string_value FROM UNNEST(event_params) ep WHERE ep.key = 'page_location') AS page_location
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX = '20210102'
    AND event_date = '20210102'
    AND event_name = 'page_view'
    AND user_pseudo_id = '1402138.5184246691'
),
seg AS (
  SELECT
    event_timestamp,
    page_location,
    SPLIT(page_location, '/') AS parts
  FROM pv
),
cls AS (
  SELECT
    event_timestamp,
    page_location,
    ARRAY_LENGTH(parts) AS n,
    parts[SAFE_OFFSET(3)] AS s4,
    parts[SAFE_OFFSET(4)] AS s5,
    parts[SAFE_OFFSET(ARRAY_LENGTH(parts) - 1)] AS last_seg
  FROM seg
)
SELECT
  CASE
    WHEN n >= 5
      AND STRPOS(last_seg, '+') > 0
      AND (
        REPLACE(LOWER(s4), '+', ' ') IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables')
        OR REPLACE(LOWER(s5), '+', ' ') IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables')
      ) THEN 'PDP'
    WHEN n >= 5
      AND STRPOS(s4, '+') = 0
      AND STRPOS(s5, '+') = 0
      AND (
        LOWER(s4) IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables')
        OR LOWER(s5) IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables')
      ) THEN 'PLP'
    ELSE page_location
  END AS page_name
FROM cls
ORDER BY event_timestamp