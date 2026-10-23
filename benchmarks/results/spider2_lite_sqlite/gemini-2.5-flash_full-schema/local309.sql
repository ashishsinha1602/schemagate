WITH DriverPoints AS (
  SELECT
    r.year,
    d.full_name AS driver_full_name,
    SUM(ds.points) AS total_driver_points
  FROM main.driver_standings AS ds
  JOIN main.races AS r
    ON ds.race_id = r.race_id
  JOIN main.drivers AS d
    ON ds.driver_id = d.driver_id
  GROUP BY
    r.year,
    d.driver_id,
    d.full_name
), TopDriverPerYear AS (
  SELECT
    dp.year,
    dp.driver_full_name,
    dp.total_driver_points,
    RANK() OVER (PARTITION BY dp.year ORDER BY dp.total_driver_points DESC) AS rn
  FROM DriverPoints AS dp
), ConstructorPoints AS (
  SELECT
    r.year,
    c.name AS constructor_name,
    SUM(cs.points) AS total_constructor_points
  FROM main.constructor_standings AS cs
  JOIN main.races AS r
    ON cs.race_id = r.race_id
  JOIN main.constructors AS c
    ON cs.constructor_id = c.constructor_id
  GROUP BY
    r.year,
    c.constructor_id,
    c.name
), TopConstructorPerYear AS (
  SELECT
    cp.year,
    cp.constructor_name,
    cp.total_constructor_points,
    RANK() OVER (PARTITION BY cp.year ORDER BY cp.total_constructor_points DESC) AS rn
  FROM ConstructorPoints AS cp
)
SELECT
  td.year,
  td.driver_full_name,
  td.total_driver_points,
  tc.constructor_name,
  tc.total_constructor_points
FROM TopDriverPerYear AS td
JOIN TopConstructorPerYear AS tc
  ON td.year = tc.year
WHERE
  td.rn = 1 AND tc.rn = 1
ORDER BY
  td.year