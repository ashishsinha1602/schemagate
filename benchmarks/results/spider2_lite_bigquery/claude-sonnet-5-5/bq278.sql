WITH combined AS (
  SELECT 'postal_code' AS region_level, state_name, count_qualified, percent_covered, percent_qualified, number_of_panels_total, kw_total, yearly_sunlight_kwh_total, carbon_offset_metric_tons, existing_installs_count
  FROM `bigquery-public-data.sunroof_solar.solar_potential_by_postal_code`
  UNION ALL
  SELECT 'census_tract' AS region_level, state_name, count_qualified, percent_covered, percent_qualified, number_of_panels_total, kw_total, yearly_sunlight_kwh_total, carbon_offset_metric_tons, existing_installs_count
  FROM `bigquery-public-data.sunroof_solar.solar_potential_by_censustract`
)
SELECT
  state_name,
  region_level,
  SUM(count_qualified) AS total_qualified_buildings,
  AVG(percent_covered) AS avg_percent_covered,
  AVG(percent_qualified) AS avg_percent_qualified,
  SUM(number_of_panels_total) AS total_panels,
  SUM(kw_total) AS total_kw,
  SUM(yearly_sunlight_kwh_total) AS total_yearly_sunlight_kwh,
  SUM(carbon_offset_metric_tons) AS total_carbon_offset_metric_tons,
  SUM(existing_installs_count) AS total_existing_installs,
  SUM(count_qualified) * (AVG(percent_covered) / 100) * (AVG(percent_qualified) / 100) - SUM(existing_installs_count) AS potential_installs_gap
FROM combined
GROUP BY state_name, region_level
ORDER BY state_name, region_level