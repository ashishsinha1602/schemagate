WITH h AS (
  SELECT
    country_name,
    country_code,
    MAX(IF(year = 2018, value, NULL)) AS v18,
    MAX(IF(year = 2017, value, NULL)) AS v17
  FROM `bigquery-public-data.world_bank_health_population.health_nutrition_population`
  WHERE indicator_code = 'SH.XPD.CHEX.PP.CD'
    AND year IN (2017, 2018)
  GROUP BY country_name, country_code
)
SELECT COUNT(DISTINCT h.country_code) AS num_countries
FROM h
JOIN `bigquery-public-data.world_bank_global_population.population_by_country` p
  ON p.country = h.country_name
JOIN `bigquery-public-data.world_bank_health_population.country_summary` cs
  ON cs.country_code = h.country_code
WHERE cs.region IS NOT NULL
  AND cs.region != ''
  AND SAFE_DIVIDE(p.year_2018 - p.year_2017, p.year_2017) > 0.01
  AND SAFE_DIVIDE(h.v18 - h.v17, h.v17) > 0.01