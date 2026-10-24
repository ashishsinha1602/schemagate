WITH g AS (
  SELECT race_asian, race_black, race_hispanic_latinx, race_white
  FROM `bigquery-public-data.google_dei.dar_non_intersectional_hiring`
  WHERE report_year = 2021 AND LOWER(workforce) = 'overall'
),
b AS (
  SELECT
    AVG(percent_asian) AS asian,
    AVG(percent_black_or_african_american) AS black,
    AVG(percent_hispanic_or_latino) AS hispanic_latinx,
    AVG(percent_white) AS white
  FROM `bigquery-public-data.google_dei.full_csv-latest-data-is-2023`
  WHERE year = 2021
    AND (industry IN ('Internet publishing and broadcasting and web search portals', 'Software publishers', 'Data processing, hosting, and related services')
      OR industry_group = 'Computer systems design and related services')
),
x AS (
  SELECT 'asian' AS race, g.race_asian AS google_pct, b.asian AS bls_pct FROM g CROSS JOIN b
  UNION ALL
  SELECT 'black', g.race_black, b.black FROM g CROSS JOIN b
  UNION ALL
  SELECT 'hispanic_latinx', g.race_hispanic_latinx, b.hispanic_latinx FROM g CROSS JOIN b
  UNION ALL
  SELECT 'white', g.race_white, b.white FROM g CROSS JOIN b
)
SELECT race, ABS(google_pct - bls_pct) AS percentage_difference
FROM x
ORDER BY percentage_difference DESC
LIMIT 3