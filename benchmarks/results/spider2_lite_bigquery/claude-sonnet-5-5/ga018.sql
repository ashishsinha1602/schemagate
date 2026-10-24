WITH pv AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
    event_timestamp,
    SPLIT((SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'), '/') AS segs
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX = '20210102'
    AND event_name = 'page_view'
),
classified AS (
  SELECT
    user_pseudo_id,
    session_id,
    event_timestamp,
    CASE
      WHEN ARRAY_LENGTH(segs) >= 5
        AND STRPOS(IFNULL(segs[SAFE_OFFSET(ARRAY_LENGTH(segs) - 1)], ''), '+') > 0
        AND (LOWER(REPLACE(IFNULL(segs[SAFE_OFFSET(3)], ''), '+', ' ')) IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables')
          OR LOWER(REPLACE(IFNULL(segs[SAFE_OFFSET(4)], ''), '+', ' ')) IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables'))
        THEN 'PDP'
      WHEN ARRAY_LENGTH(segs) >= 5
        AND STRPOS(IFNULL(segs[SAFE_OFFSET(3)], ''), '+') = 0
        AND STRPOS(IFNULL(segs[SAFE_OFFSET(4)], ''), '+') = 0
        AND (LOWER(IFNULL(segs[SAFE_OFFSET(3)], '')) IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables')
          OR LOWER(IFNULL(segs[SAFE_OFFSET(4)], '')) IN ('accessories','apparel','brands','campus collection','drinkware','electronics','google redesign','lifestyle','nest','new 2015 logo','notebooks journals','office','shop by brand','small goods','stationery','wearables'))
        THEN 'PLP'
      ELSE 'OTHER'
    END AS page_type
  FROM pv
),
plp AS (
  SELECT * FROM classified WHERE page_type = 'PLP'
),
pdp AS (
  SELECT * FROM classified WHERE page_type = 'PDP'
)
SELECT
  COUNTIF(EXISTS (
    SELECT 1 FROM pdp
    WHERE pdp.user_pseudo_id = plp.user_pseudo_id
      AND pdp.session_id = plp.session_id
      AND pdp.event_timestamp > plp.event_timestamp
  )) AS plp_views_leading_to_pdp,
  SAFE_DIVIDE(
    COUNTIF(EXISTS (
      SELECT 1 FROM pdp
      WHERE pdp.user_pseudo_id = plp.user_pseudo_id
        AND pdp.session_id = plp.session_id
        AND pdp.event_timestamp > plp.event_timestamp
    )),
    COUNT(*)
  ) * 100 AS plp_to_pdp_percentage
FROM plp