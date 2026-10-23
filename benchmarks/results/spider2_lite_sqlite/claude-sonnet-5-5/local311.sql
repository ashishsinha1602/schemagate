WITH dp AS (
  SELECT r.year AS year, ds.driver_id AS driver_id, MAX(ds.points) AS pts
  FROM driver_standings ds
  JOIN races r ON r.race_id = ds.race_id
  GROUP BY r.year, ds.driver_id
),
cp AS (
  SELECT r.year AS year, cs.constructor_id AS constructor_id, MAX(cs.points) AS pts
  FROM constructor_standings cs
  JOIN races r ON r.race_id = cs.race_id
  GROUP BY r.year, cs.constructor_id
),
best AS (
  SELECT t.year AS year, t.constructor_id AS constructor_id, MAX(dp.pts) AS best_driver_points
  FROM team_driver_ranks t
  JOIN dp ON dp.year = t.year AND dp.driver_id = t.driver_id
  GROUP BY t.year, t.constructor_id
)
SELECT c.name, b.year, b.best_driver_points, cp.pts AS team_points, b.best_driver_points + cp.pts AS combined_points
FROM best b
JOIN cp ON cp.year = b.year AND cp.constructor_id = b.constructor_id
JOIN constructors c ON c.constructor_id = b.constructor_id
ORDER BY combined_points DESC
LIMIT 3