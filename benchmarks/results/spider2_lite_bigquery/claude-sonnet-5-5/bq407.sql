SELECT
  s.county_name,
  s.state,
  c.median_age,
  c.total_pop,
  SAFE_DIVIDE(s.confirmed_cases, c.total_pop) * 100000 AS confirmed_cases_per_100k,
  SAFE_DIVIDE(s.deaths, c.total_pop) * 100000 AS deaths_per_100k,
  SAFE_DIVIDE(s.deaths, s.confirmed_cases) * 100 AS case_fatality_rate_pct
FROM `bigquery-public-data.covid19_usafacts.summary` AS s
JOIN `bigquery-public-data.census_bureau_acs.county_2020_5yr` AS c
  ON s.county_fips_code = c.geo_id
WHERE s.date = DATE '2020-08-27'
  AND c.total_pop > 50000
  AND s.confirmed_cases > 0
ORDER BY case_fatality_rate_pct DESC
LIMIT 3