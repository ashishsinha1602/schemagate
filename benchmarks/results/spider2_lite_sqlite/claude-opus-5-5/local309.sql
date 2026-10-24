WITH driver_last_race AS (
  SELECT r.year, MAX(r.round) AS max_round
  FROM races r
  WHERE r.race_id IN (SELECT race_id FROM driver_standings)
  GROUP BY r.year
),
driver_totals AS (
  SELECT r.year, ds.driver_id, ds.points,
         RANK() OVER (PARTITION BY r.year ORDER BY ds.points DESC) AS rnk
  FROM driver_standings ds
  JOIN races r ON r.race_id = ds.race_id
  JOIN driver_last_race l ON l.year = r.year AND l.max_round = r.round
),
constructor_last_race AS (
  SELECT r.year, MAX(r.round) AS max_round
  FROM races r
  WHERE r.race_id IN (SELECT race_id FROM constructor_standings)
  GROUP BY r.year
),
constructor_totals AS (
  SELECT r.year, cs.constructor_id, cs.points,
         RANK() OVER (PARTITION BY r.year ORDER BY cs.points DESC) AS rnk
  FROM constructor_standings cs
  JOIN races r ON r.race_id = cs.race_id
  JOIN constructor_last_race l ON l.year = r.year AND l.max_round = r.round
),
top_drivers AS (
  SELECT dt.year,
         COALESCE(d.full_name, d.forename || ' ' || d.surname) AS driver_full_name,
         dt.points AS driver_points
  FROM driver_totals dt
  JOIN drivers d ON d.driver_id = dt.driver_id
  WHERE dt.rnk = 1
),
top_constructors AS (
  SELECT ct.year, c.name AS constructor_name, ct.points AS constructor_points
  FROM constructor_totals ct
  JOIN constructors c ON c.constructor_id = ct.constructor_id
  WHERE ct.rnk = 1
),
years AS (
  SELECT year FROM top_drivers
  UNION
  SELECT year FROM top_constructors
)
SELECT y.year,
       td.driver_full_name,
       td.driver_points,
       tc.constructor_name,
       tc.constructor_points
FROM years y
LEFT JOIN top_drivers td ON td.year = y.year
LEFT JOIN top_constructors tc ON tc.year = y.year
ORDER BY y.year