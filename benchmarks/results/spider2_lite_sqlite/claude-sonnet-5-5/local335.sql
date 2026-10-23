WITH final AS (
  SELECT r.year, ds.driver_id, ds.points,
         ROW_NUMBER() OVER (PARTITION BY r.year, ds.driver_id ORDER BY r.round DESC) AS rn
  FROM driver_standings ds
  JOIN races r ON r.race_id = ds.race_id
  WHERE r.year >= 2001
),
scorers AS (
  SELECT year, driver_id, points,
         MIN(points) OVER (PARTITION BY year) AS min_points
  FROM final
  WHERE rn = 1 AND points > 0
),
lowest AS (
  SELECT DISTINCT year, driver_id
  FROM scorers
  WHERE points = min_points
),
team_seasons AS (
  SELECT DISTINCT l.year, d.constructor_id
  FROM lowest l
  JOIN drives d ON d.year = l.year AND d.driver_id = l.driver_id
)
SELECT c.name, COUNT(*) AS seasons
FROM team_seasons t
JOIN constructors c ON c.constructor_id = t.constructor_id
GROUP BY c.constructor_id, c.name
ORDER BY seasons DESC, c.name
LIMIT 5