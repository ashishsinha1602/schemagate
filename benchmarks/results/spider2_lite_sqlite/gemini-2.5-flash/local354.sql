WITH driver_races_in_50s AS (
  SELECT
    ds.driver_id,
    r.year,
    r.round,
    r.race_id
  FROM main.driver_standings AS ds
  JOIN main.races AS r
    ON ds.race_id = r.race_id
  WHERE
    r.year BETWEEN 1950 AND 1959
), driver_season_summary AS (
  SELECT
    driver_id,
    year,
    MIN(round) AS first_round_participated,
    MAX(round) AS last_round_participated,
    COUNT(DISTINCT round) AS distinct_rounds_count
  FROM driver_races_in_50s
  GROUP BY
    driver_id,
    year
  HAVING
    COUNT(DISTINCT round) >= 2
), driver_season_constructors AS (
  SELECT
    dss.driver_id,
    dss.year,
    dss.first_round_participated,
    dss.last_round_participated,
    d1.constructor_id AS first_race_constructor_id,
    d2.constructor_id AS last_race_constructor_id
  FROM driver_season_summary AS dss
  JOIN main.drives AS d1
    ON dss.driver_id = d1.driver_id
    AND dss.year = d1.year
    AND dss.first_round_participated BETWEEN d1.first_round AND d1.last_round
  JOIN main.drives AS d2
    ON dss.driver_id = d2.driver_id
    AND dss.year = d2.year
    AND dss.last_round_participated BETWEEN d2.first_round AND d2.last_round
  WHERE
    d1.constructor_id = d2.constructor_id
)
SELECT DISTINCT
  d.full_name
FROM driver_season_constructors AS dsc
JOIN main.drivers AS d
  ON dsc.driver_id = d.driver_id