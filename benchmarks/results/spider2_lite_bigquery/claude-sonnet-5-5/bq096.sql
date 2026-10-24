WITH daily AS (
  SELECT DATE(eventdate) AS d, COUNT(*) AS sightings
  FROM `bigquery-public-data.gbif.occurrences`
  WHERE species = 'Sterna paradisaea'
    AND decimallatitude > 40
    AND eventdate IS NOT NULL
    AND EXTRACT(MONTH FROM eventdate) > 1
  GROUP BY d
  HAVING COUNT(*) > 10
),
first_day AS (
  SELECT EXTRACT(YEAR FROM d) AS year, EXTRACT(MONTH FROM d) AS month, EXTRACT(DAY FROM d) AS day
  FROM daily
  QUALIFY ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM d) ORDER BY d) = 1
)
SELECT year
FROM first_day
ORDER BY month, day, year
LIMIT 1