WITH y AS (
  SELECT CAST(SUBSTR(year, -4) AS INTEGER) AS yr
  FROM Movie
  WHERE year IS NOT NULL
)
SELECT d.yr AS start_year, COUNT(*) AS total_count
FROM (SELECT DISTINCT yr FROM y) d
JOIN y ON y.yr BETWEEN d.yr AND d.yr + 9
GROUP BY d.yr
ORDER BY total_count DESC
LIMIT 1