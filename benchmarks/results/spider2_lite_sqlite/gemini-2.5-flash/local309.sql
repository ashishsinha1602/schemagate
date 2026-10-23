WITH DriverPoints AS (
  SELECT
    r.year,
    ds.driver_id,
    SUM(ds.points) AS total_driver_points
  FROM main.driver_standings AS ds
  JOIN main.races AS r
    ON ds.race_id = r.race_id
  GROUP BY
    r.year,
    ds.driver_id
), RankedDrivers AS (
  SELECT
    dp.year,
    dp.driver_id,
    dp.total_driver_points,
    RANK() OVER (PARTITION BY dp.year ORDER BY dp.total_driver_points DESC) AS rn
  FROM DriverPoints AS dp
), ConstructorPoints AS (
  SELECT
    r.year,
    cs.constructor_id,
    SUM(cs.points) AS total_constructor_points
  FROM main.constructor_standings AS cs
  JOIN main.races AS r
    ON cs.race_id = r.race_id
  GROUP BY
    r.year,
    cs.constructor_id
), RankedConstructors AS (
  SELECT
    cp.year,
    cp.constructor_id,
    cp.total_constructor_points,
    RANK() OVER (PARTITION BY cp.year ORDER BY cp.total_constructor_points DESC) AS rn
  FROM ConstructorPoints AS cp
)
SELECT
  rd.year,
  d.full_name AS top_driver_full_name,
  rd.total_driver_points,
  c.name AS top_constructor_name,
  rc.total_constructor_points
FROM RankedDrivers AS rd
JOIN main.drivers AS d
  ON rd.driver_id = d.driver_id
JOIN RankedConstructors AS rc
  ON rd.year = rc.year
JOIN main.constructors AS c
  ON rc.constructor_id = c.constructor_id
WHERE
  rd.rn = 1 AND rc.rn = 1
ORDER BY
  rd.year