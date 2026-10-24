WITH y14 AS (
  SELECT *
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_representation`
  WHERE LOWER(workforce) = 'overall' AND report_year = 2014
),
y24 AS (
  SELECT *
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_representation`
  WHERE LOWER(workforce) = 'overall' AND report_year = 2024
)
SELECT
  SAFE_DIVIDE(y24.race_asian - y14.race_asian, y14.race_asian) AS asian_growth_rate,
  SAFE_DIVIDE(y24.race_black - y14.race_black, y14.race_black) AS black_growth_rate,
  SAFE_DIVIDE(y24.race_hispanic_latinx - y14.race_hispanic_latinx, y14.race_hispanic_latinx) AS latinx_growth_rate,
  SAFE_DIVIDE(y24.race_native_american - y14.race_native_american, y14.race_native_american) AS native_american_growth_rate,
  SAFE_DIVIDE(y24.race_white - y14.race_white, y14.race_white) AS white_growth_rate,
  SAFE_DIVIDE(y24.gender_us_women - y14.gender_us_women, y14.gender_us_women) AS us_women_growth_rate,
  SAFE_DIVIDE(y24.gender_us_men - y14.gender_us_men, y14.gender_us_men) AS us_men_growth_rate,
  SAFE_DIVIDE(y24.gender_global_women - y14.gender_global_women, y14.gender_global_women) AS global_women_growth_rate,
  SAFE_DIVIDE(y24.gender_global_men - y14.gender_global_men, y14.gender_global_men) AS global_men_growth_rate
FROM y14
CROSS JOIN y24