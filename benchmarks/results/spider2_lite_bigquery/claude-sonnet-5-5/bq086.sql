WITH covid AS (
  SELECT country_code, country_name, cumulative_confirmed
  FROM `bigquery-public-data.covid19_open_data.covid19_open_data`
  WHERE date = DATE '2020-06-30'
    AND aggregation_level = 0
)
SELECT
  c.country_name AS country,
  p.year_2018 AS population_2018,
  c.cumulative_confirmed AS cumulative_confirmed,
  SAFE_DIVIDE(c.cumulative_confirmed, p.year_2018) * 100 AS percent_population_confirmed
FROM covid AS c
JOIN `bigquery-public-data.world_bank_wdi.country_summary` AS s
  ON s.two_alpha_code = c.country_code
JOIN `bigquery-public-data.world_bank_global_population.population_by_country` AS p
  ON p.country_code = s.country_code