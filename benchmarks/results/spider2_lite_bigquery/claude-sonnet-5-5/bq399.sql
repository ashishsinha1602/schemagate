WITH avg_cbr AS (
  SELECT
    cs.region,
    h.country_name,
    AVG(h.value) AS avg_birth_rate
  FROM `bigquery-public-data.world_bank_health_population.health_nutrition_population` AS h
  JOIN `bigquery-public-data.world_bank_health_population.country_summary` AS cs
    ON h.country_code = cs.country_code
  WHERE h.indicator_code = 'SP.DYN.CBRT.IN'
    AND h.year BETWEEN 1980 AND 1989
    AND cs.income_group = 'High income'
    AND cs.region IS NOT NULL
    AND cs.region != ''
  GROUP BY cs.region, h.country_name
)
SELECT
  region,
  country_name,
  avg_birth_rate
FROM avg_cbr
QUALIFY ROW_NUMBER() OVER (PARTITION BY region ORDER BY avg_birth_rate DESC) = 1
ORDER BY region