WITH pv AS (
  SELECT
    user_pseudo_id,
    (SELECT ep.value.int_value FROM UNNEST(event_params) ep WHERE ep.key = 'ga_session_id') AS session_id,
    (SELECT ep.value.string_value FROM UNNEST(event_params) ep WHERE ep.key = 'page_title') AS page_title
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX = '20210102'
    AND event_name = 'page_view'
),
sessions AS (
  SELECT
    user_pseudo_id,
    session_id,
    LOGICAL_OR(page_title = 'Home') AS has_home,
    LOGICAL_OR(page_title = 'Checkout Confirmation') AS has_confirmation
  FROM pv
  WHERE session_id IS NOT NULL
  GROUP BY user_pseudo_id, session_id
)
SELECT
  SAFE_DIVIDE(COUNTIF(has_home AND has_confirmation), COUNTIF(has_home)) * 100 AS conversion_rate_percent
FROM sessions