WITH yearly AS (
  SELECT
    _TABLE_SUFFIX AS yr,
    state_fips_code,
    COUNT(*) AS cnt
  FROM `bigquery-public-data.noaa_historic_severe_storms.storms_*`
  WHERE _TABLE_SUFFIX BETWEEN '1980' AND '1995'
  GROUP BY yr, state_fips_code
),
ranked AS (
  SELECT
    yr,
    state_fips_code,
    cnt,
    ROW_NUMBER() OVER (PARTITION BY yr ORDER BY cnt DESC) AS rn
  FROM yearly
),
state_map AS (
  SELECT
    state_fips_code,
    MAX(state_abbreviation) AS state_abbreviation
  FROM `bigquery-public-data.noaa_historic_severe_storms.tornado_paths`
  GROUP BY state_fips_code
)
SELECT
  m.state_abbreviation
FROM ranked r
JOIN state_map m
  ON r.state_fips_code = m.state_fips_code
WHERE r.rn <= 1000
GROUP BY m.state_abbreviation
ORDER BY SUM(r.cnt) DESC
LIMIT 5