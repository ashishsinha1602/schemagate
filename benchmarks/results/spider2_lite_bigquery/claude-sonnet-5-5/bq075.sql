SELECT
  'Google hiring' AS source,
  report_year,
  workforce,
  race_asian,
  race_black,
  race_hispanic_latinx,
  race_white,
  gender_us_women,
  gender_us_men
FROM `bigquery-public-data.google_dei.dar_non_intersectional_hiring`
WHERE report_year = 2021
  AND workforce = 'overall'
UNION ALL
SELECT
  'Google representation' AS source,
  report_year,
  workforce,
  race_asian,
  race_black,
  race_hispanic_latinx,
  race_white,
  gender_us_women,
  gender_us_men
FROM `bigquery-public-data.google_dei.dar_non_intersectional_representation`
WHERE report_year = 2021
  AND workforce = 'overall'