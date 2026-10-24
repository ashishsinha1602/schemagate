WITH pv AS (
  SELECT
    SPLIT((SELECT ep.value.string_value FROM UNNEST(event_params) ep WHERE ep.key = 'page_location'), '/') AS parts
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX = '20210102'
    AND event_name = 'page_view'
)
SELECT
  100 * SAFE_DIVIDE(
    COUNTIF(
      ARRAY_LENGTH(parts) >= 5
      AND STRPOS(parts[OFFSET(ARRAY_LENGTH(parts) - 1)], '+') > 0
      AND (
        REGEXP_CONTAINS(REPLACE(LOWER(parts[SAFE_OFFSET(3)]), '+', ' '), r'accessories|apparel|brands|campus collection|drinkware|electronics|google redesign|lifestyle|nest|new 2015 logo|notebooks journals|office|shop by brand|small goods|stationery|wearables')
        OR REGEXP_CONTAINS(REPLACE(LOWER(parts[SAFE_OFFSET(4)]), '+', ' '), r'accessories|apparel|brands|campus collection|drinkware|electronics|google redesign|lifestyle|nest|new 2015 logo|notebooks journals|office|shop by brand|small goods|stationery|wearables')
      )
    ),
    COUNT(*)
  ) AS pdp_percentage
FROM pv