WITH state_daily AS (
  SELECT
    date,
    state_name,
    confirmed_cases - LAG(confirmed_cases) OVER (PARTITION BY state_name ORDER BY date) AS new_cases
  FROM `bigquery-public-data.covid19_nyt.us_states`
),
state_top AS (
  SELECT
    date,
    state_name,
    ROW_NUMBER() OVER (PARTITION BY date ORDER BY new_cases DESC, state_name) AS rn
  FROM state_daily
  WHERE date BETWEEN '2020-03-01' AND '2020-05-31'
    AND new_cases IS NOT NULL
),
state_rank AS (
  SELECT
    state_name,
    COUNT(*) AS days_in_top5,
    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, state_name) AS rnk
  FROM state_top
  WHERE rn <= 5
  GROUP BY state_name
),
fourth AS (
  SELECT state_name FROM state_rank WHERE rnk = 4
),
county_daily AS (
  SELECT
    date,
    county,
    state_name,
    confirmed_cases - LAG(confirmed_cases) OVER (PARTITION BY state_name, county ORDER BY date) AS new_cases
  FROM `bigquery-public-data.covid19_nyt.us_counties`
  WHERE state_name IN (SELECT state_name FROM fourth)
),
county_top AS (
  SELECT
    date,
    county,
    ROW_NUMBER() OVER (PARTITION BY date ORDER BY new_cases DESC, county) AS rn
  FROM county_daily
  WHERE date BETWEEN '2020-03-01' AND '2020-05-31'
    AND new_cases IS NOT NULL
)
SELECT
  county,
  COUNT(*) AS days_in_top5
FROM county_top
WHERE rn <= 5
GROUP BY county
ORDER BY days_in_top5 DESC, county
LIMIT 5