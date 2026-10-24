WITH yrs AS (
  SELECT CAST(SUBSTR(year, -4) AS INTEGER) AS y
  FROM Movie
  WHERE year IS NOT NULL
),
starts AS (
  SELECT DISTINCT y FROM yrs
)
SELECT s.y AS start_year,
       COUNT(*) AS total_count
FROM starts s
JOIN yrs m ON m.y >= s.y AND m.y < s.y + 10
GROUP BY s.y
ORDER BY total_count DESC
LIMIT 1