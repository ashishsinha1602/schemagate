WITH DriverPointsPerYear AS (
  SELECT
    r.year,
    res.driver_id,
    SUM(res.points) AS driver_total_points
  FROM main.results AS res
  JOIN main.races AS r
    ON res.race_id = r.race_id
  GROUP BY
    r.year,
    res.driver_id
), MaxDriverPointsPerYear AS (
  SELECT
    year,
    MAX(driver_total_points) AS max_driver_points
  FROM DriverPointsPerYear
  GROUP BY
    year
), ConstructorPointsPerYear AS (
  SELECT
    r.year,
    res.constructor_id,
    SUM(res.points) AS constructor_total_points
  FROM main.results AS res
  JOIN main.races AS r
    ON res.race_id = r.race_id
  GROUP BY
    r.year,
    res.constructor_id
), MaxConstructorPointsPerYear AS (
  SELECT
    year,
    MAX(constructor_total_points) AS max_constructor_points
  FROM ConstructorPointsPerYear
  GROUP BY
    year
)
SELECT
  mdpy.year
FROM MaxDriverPointsPerYear AS mdpy
JOIN MaxConstructorPointsPerYear AS mcpy
  ON mdpy.year = mcpy.year
ORDER BY
  (mdpy.max_driver_points + mcpy.max_constructor_points) ASC
LIMIT 3