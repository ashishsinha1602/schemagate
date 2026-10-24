WITH last_race AS (
  SELECT r.year, r.race_id
  FROM races r
  WHERE r.year >= 2001
    AND r.round = (
      SELECT MAX(r2.round)
      FROM races r2
      JOIN driver_standings ds2 ON ds2.race_id = r2.race_id
      WHERE r2.year = r.year
    )
),
driver_pts AS (
  SELECT lr.year, ds.driver_id, ds.points
  FROM last_race lr
  JOIN driver_standings ds ON ds.race_id = lr.race_id
  WHERE ds.points > 0
),
min_pts AS (
  SELECT year, MIN(points) AS min_points
  FROM driver_pts
  GROUP BY year
),
lowest AS (
  SELECT dp.year, dp.driver_id
  FROM driver_pts dp
  JOIN min_pts m ON m.year = dp.year AND dp.points = m.min_points
)
SELECT c.constructor_id, c.name, COUNT(DISTINCT l.year) AS seasons
FROM lowest l
JOIN drives d ON d.year = l.year AND d.driver_id = l.driver_id
JOIN constructors c ON c.constructor_id = d.constructor_id
GROUP BY c.constructor_id, c.name
ORDER BY seasons DESC
LIMIT 5