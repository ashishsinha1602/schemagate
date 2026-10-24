WITH pv AS (
  SELECT
    (SELECT ep.value.string_value FROM UNNEST(event_params) ep WHERE ep.key = 'page_location') AS page_location
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20201201' AND '20201231'
    AND event_name = 'page_view'
    AND event_dimensions.hostname = 'shop.googlemerchandisestore.com'
),
cleaned AS (
  SELECT
    REGEXP_REPLACE(
      COALESCE(REGEXP_EXTRACT(page_location, r'^https?://[^/?#]+(/[^?#]*)'), '/'),
      r'/{2,}', '/'
    ) AS page_path
  FROM pv
  WHERE page_location IS NOT NULL
)
SELECT page_path
FROM cleaned
GROUP BY page_path
ORDER BY COUNT(*) DESC
LIMIT 1 OFFSET 1