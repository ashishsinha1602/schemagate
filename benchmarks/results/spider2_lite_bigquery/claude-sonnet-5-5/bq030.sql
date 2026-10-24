SELECT
  country_name,
  SAFE_DIVIDE(cumulative_recovered, cumulative_confirmed) * 100 AS recovery_rate_percent
FROM `bigquery-public-data.covid19_open_data.covid19_open_data`
WHERE date = DATE '2020-05-10'
  AND aggregation_level = 0
  AND cumulative_confirmed > 50000
  AND cumulative_recovered IS NOT NULL
ORDER BY recovery_rate_percent DESC
LIMIT 3