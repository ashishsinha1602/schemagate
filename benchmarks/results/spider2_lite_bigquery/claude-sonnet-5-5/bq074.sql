WITH u15 AS (
  SELECT geo_id, unemployed_pop AS unemp_2015
  FROM `bigquery-public-data.census_bureau_acs.county_2015_5yr`
),
u18 AS (
  SELECT geo_id, unemployed_pop AS unemp_2018
  FROM `bigquery-public-data.census_bureau_acs.county_2018_1yr`
),
d AS (
  SELECT
    FIPS,
    SUM(IF(Date = DATE '2015-12-01', Public_Total, NULL)) AS dual_2015,
    SUM(IF(Date = DATE '2018-12-01', Public_Total, NULL)) AS dual_2018
  FROM `bigquery-public-data.sdoh_cms_dual_eligible_enrollment.dual_eligible_enrollment_by_county_and_program`
  WHERE Date IN (DATE '2015-12-01', DATE '2018-12-01')
  GROUP BY FIPS
)
SELECT COUNT(DISTINCT u15.geo_id) AS county_count
FROM u15
JOIN u18 ON u15.geo_id = u18.geo_id
JOIN d ON d.FIPS = u15.geo_id
WHERE u18.unemp_2018 > u15.unemp_2015
  AND d.dual_2018 < d.dual_2015