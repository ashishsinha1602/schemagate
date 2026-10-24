WITH cases AS (
  SELECT
    CASE country_or_region
      WHEN 'US' THEN 'USA'
      WHEN 'France' THEN 'FRA'
      WHEN 'China' THEN 'CHN'
      WHEN 'Italy' THEN 'ITA'
      WHEN 'Spain' THEN 'ESP'
      WHEN 'Germany' THEN 'DEU'
      WHEN 'Iran' THEN 'IRN'
    END AS country_code,
    country_or_region AS country,
    SUM(SAFE_CAST(_4_20_20 AS INT64)) AS total_confirmed_cases
  FROM `bigquery-public-data.covid19_jhu_csse.confirmed_cases`
  WHERE country_or_region IN ('US', 'France', 'China', 'Italy', 'Spain', 'Germany', 'Iran')
  GROUP BY country_code, country
),
pop AS (
  SELECT country_code, SUM(year_2020) AS population_2020
  FROM `bigquery-public-data.world_bank_global_population.population_by_country`
  WHERE country_code IN ('USA', 'FRA', 'CHN', 'ITA', 'ESP', 'DEU', 'IRN')
  GROUP BY country_code
)
SELECT
  c.country,
  c.total_confirmed_cases,
  SAFE_DIVIDE(c.total_confirmed_cases, p.population_2020) * 100000 AS cases_per_100k
FROM cases c
JOIN pop p ON c.country_code = p.country_code