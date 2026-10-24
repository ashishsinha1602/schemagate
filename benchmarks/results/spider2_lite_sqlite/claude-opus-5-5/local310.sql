WITH driver_year AS (
  SELECT ra.year, r.driver_id, SUM(r.points) AS pts
  FROM results r
  JOIN races ra ON ra.race_id = r.race_id
  GROUP BY ra.year, r.driver_id
),
constructor_year AS (
  SELECT ra.year, r.constructor_id, SUM(r.points) AS pts
  FROM results r
  JOIN races ra ON ra.race_id = r.race_id
  GROUP BY ra.year, r.constructor_id
),
max_driver AS (
  SELECT year, MAX(pts) AS max_pts
  FROM driver_year
  GROUP BY year
),
max_constructor AS (
  SELECT year, MAX(pts) AS max_pts
  FROM constructor_year
  GROUP BY year
)
SELECT d.year
FROM max_driver d
JOIN max_constructor c ON c.year = d.year
ORDER BY d.max_pts + c.max_pts ASC
LIMIT 3