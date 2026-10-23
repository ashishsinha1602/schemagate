WITH DriverSeasonRaces AS (
  SELECT
    r.year,
    d.driver_id,
    d.full_name,
    r.round,
    res.constructor_id
  FROM main.results AS res
  JOIN main.races AS r
    ON res.race_id = r.race_id
  JOIN main.drivers AS d
    ON res.driver_id = d.driver_id
  WHERE
    r.year BETWEEN 1950 AND 1959
), DriverSeasonSummary AS (
  SELECT
    dsr.year,
    dsr.driver_id,
    dsr.full_name,
    MIN(dsr.round) AS first_round,
    MAX(dsr.round) AS last_round,
    COUNT(DISTINCT dsr.round) AS distinct_rounds_count
  FROM DriverSeasonRaces AS dsr
  GROUP BY
    dsr.year,
    dsr.driver_id,
    dsr.full_name
  HAVING
    COUNT(DISTINCT dsr.round) >= 2
), FirstRaceConstructor AS (
  SELECT
    dsr.year,
    dsr.driver_id,
    dsr.constructor_id
  FROM DriverSeasonRaces AS dsr
  JOIN DriverSeasonSummary AS dss
    ON dsr.year = dss.year
    AND dsr.driver_id = dss.driver_id
    AND dsr.round = dss.first_round
), LastRaceConstructor AS (
  SELECT
    dsr.year,
    dsr.driver_id,
    dsr.constructor_id
  FROM DriverSeasonRaces AS dsr
  JOIN DriverSeasonSummary AS dss
    ON dsr.year = dss.year
    AND dsr.driver_id = dss.driver_id
    AND dsr.round = dss.last_round
)
SELECT DISTINCT
  dss.full_name
FROM DriverSeasonSummary AS dss
JOIN FirstRaceConstructor AS frc
  ON dss.year = frc.year
  AND dss.driver_id = frc.driver_id
JOIN LastRaceConstructor AS lrc
  ON dss.year = lrc.year
  AND dss.driver_id = lrc.driver_id
WHERE
  frc.constructor_id = lrc.constructor_id