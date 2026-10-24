SELECT
  z.zip_code,
  a.total_pop AS total_population,
  ROUND(a.income_per_capita, 1) AS average_individual_income
FROM `bigquery-public-data.census_bureau_acs.zip_codes_2017_5yr` AS a
JOIN `bigquery-public-data.geo_us_boundaries.zip_codes` AS z
  ON a.geo_id = z.zip_code
WHERE z.state_code = 'WA'
  AND ST_DWITHIN(z.zip_code_geom, ST_GEOGPOINT(-122.191667, 47.685833), 5 * 1609.344)
ORDER BY average_individual_income DESC