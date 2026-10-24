WITH kings_tracts AS (
  SELECT geo_id
  FROM `bigquery-public-data.geo_census_tracts.census_tracts_new_york`
  WHERE state_fips_code = '36' AND county_fips_code = '047'
),
donations AS (
  SELECT SUBSTR(zip_code, 1, 5) AS zip5, transaction_amt
  FROM `bigquery-public-data.fec.committee_contributions_*`
  WHERE _TABLE_SUFFIX = '2020'
    AND state = 'NY'
    AND transaction_amt IS NOT NULL
)
SELECT
  t.geo_id AS census_tract_geoid,
  AVG(d.transaction_amt) AS avg_donation_amount,
  a.median_income AS median_income
FROM kings_tracts t
JOIN `bigquery-public-data.census_bureau_acs.censustract_2018_5yr` a
  ON a.geo_id = t.geo_id
JOIN `bigquery-public-data.hud_zipcode_crosswalk.zipcode_to_census_tracts` z
  ON z.census_tract_geoid = t.geo_id
JOIN donations d
  ON d.zip5 = z.zip_code
GROUP BY t.geo_id, a.median_income