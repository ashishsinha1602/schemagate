WITH UniqueYears AS (
  SELECT DISTINCT CAST(year AS INTEGER) AS start_year
  FROM main.Movie
  WHERE year IS NOT NULL AND year GLOB '[0-9][0-9][0-9][0-9]'
)
SELECT
  uy.start_year,
  COUNT(m.MID) AS movie_count
FROM UniqueYears AS uy
JOIN main.Movie AS m
  ON CAST(m.year AS INTEGER) >= uy.start_year
  AND CAST(m.year AS INTEGER) < uy.start_year + 10
WHERE m.year IS NOT NULL AND m.year GLOB '[0-9][0-9][0-9][0-9]'
GROUP BY
  uy.start_year
ORDER BY
  movie_count DESC,
  uy.start_year ASC
LIMIT 1