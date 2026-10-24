WITH last_race AS (
  SELECT r.year, r.race_id
  FROM races r
  WHERE r.round = (SELECT MAX(r2.round) FROM races r2 WHERE r2.year = r.year)
),
driver_pts AS (
  SELECT lr.year, ds.driver_id, ds.points
  FROM driver_standings ds
  JOIN last_race lr ON lr.race_id = ds.race_id
),
constructor_pts AS (
  SELECT lr.year, cs.constructor_id, cs.points
  FROM constructor_standings cs
  JOIN last_race lr ON lr.race_id = cs.race_id
),
team_drivers AS (
  SELECT DISTINCT year, constructor_id, driver_id
  FROM team_driver_ranks
),
best_driver AS (
  SELECT td.year, td.constructor_id, MAX(dp.points) AS best_driver_points
  FROM team_drivers td
  JOIN driver_pts dp ON dp.year = td.year AND dp.driver_id = td.driver_id
  GROUP BY td.year, td.constructor_id
)
SELECT c.name AS constructor_name,
       bd.year,
       bd.best_driver_points + cp.points AS combined_points
FROM best_driver bd
JOIN constructor_pts cp ON cp.year = bd.year AND cp.constructor_id = bd.constructor_id
JOIN constructors c ON c.constructor_id = bd.constructor_id
ORDER BY combined_points DESC
LIMIT 3