WITH counts AS (
  SELECT
    t.specialization,
    COUNT(DISTINCT n.npi) AS npi_count
  FROM `bigquery-public-data.nppes.npi_raw` AS n
  JOIN `bigquery-public-data.nppes.healthcare_provider_taxonomy_code_set_170` AS t
    ON n.healthcare_provider_taxonomy_code_1 = t.code
  WHERE UPPER(n.provider_business_practice_location_address_city_name) = 'MOUNTAIN VIEW'
    AND n.provider_business_practice_location_address_state_name = 'CA'
    AND t.specialization IS NOT NULL
    AND TRIM(t.specialization) != ''
  GROUP BY t.specialization
  ORDER BY npi_count DESC
  LIMIT 10
),
avg_c AS (
  SELECT AVG(npi_count) AS avg_count FROM counts
)
SELECT
  counts.specialization,
  counts.npi_count
FROM counts
CROSS JOIN avg_c
ORDER BY ABS(counts.npi_count - avg_c.avg_count)
LIMIT 1