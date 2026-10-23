WITH last_race AS (
  SELECT year, race_id
  FROM (
    SELECT year, race_id, ROW_NUMBER() OVER (PARTITION BY year ORDER BY round DESC) AS rn
    FROM races
  )
  WHERE rn = 1
),
top_driver AS (
  SELECT year, driver_name, points
  FROM (
    SELECT lr.year,
           COALESCE(d.full_name, d.forename || ' ' || d.surname) AS driver_name,
           ds.points,
           ROW_NUMBER() OVER (PARTITION BY lr.year ORDER BY ds.points DESC, ds.position) AS rn
    FROM driver_standings ds
    JOIN last_race lr ON lr.race_id = ds.race_id
    JOIN drivers d ON d.driver_id = ds.driver_id
  )
  WHERE rn = 1
),
top_constructor AS (
  SELECT year, constructor_name, points
  FROM (
    SELECT lr.year,
           c.name AS constructor_name,
           cs.points,
           ROW_NUMBER() OVER (PARTITION BY lr.year ORDER BY cs.points DESC, cs.position) AS rn
    FROM constructor_standings cs
    JOIN last_race lr ON lr.race_id = cs.race_id
    JOIN constructors c ON c.constructor_id = cs.constructor_id
  )
  WHERE rn = 1
)
SELECT td.year,
       td.driver_name,
       td.points AS driver_points,
       tc.constructor_name,
       tc.points AS constructor_points
FROM top_driver td
LEFT JOIN top_constructor tc ON tc.year = td.year
ORDER BY td.year