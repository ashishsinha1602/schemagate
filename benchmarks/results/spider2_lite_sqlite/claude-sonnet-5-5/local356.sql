WITH pit AS MATERIALIZED (
  SELECT DISTINCT race_id, driver_id, lap FROM pit_stops
  UNION
  SELECT DISTINCT race_id, driver_id, lap + 1 FROM pit_stops
),
ret AS MATERIALIZED (
  SELECT DISTINCT race_id, driver_id, lap FROM retirements WHERE lap IS NOT NULL
  UNION
  SELECT DISTINCT race_id, driver_id, lap + 1 FROM retirements WHERE lap IS NOT NULL
),
t AS MATERIALIZED (
  SELECT c.race_id, c.driver_id, c.lap, p.position AS prev_pos, c.position AS cur_pos
  FROM lap_positions c
  JOIN lap_positions p
    ON p.race_id = c.race_id AND p.driver_id = c.driver_id AND p.lap = c.lap - 1
  LEFT JOIN pit ON pit.race_id = c.race_id AND pit.driver_id = c.driver_id AND pit.lap = c.lap
  LEFT JOIN ret ON ret.race_id = c.race_id AND ret.driver_id = c.driver_id AND ret.lap = c.lap
  WHERE c.lap >= 2
    AND pit.race_id IS NULL
    AND ret.race_id IS NULL
),
ev AS (
  SELECT x.driver_id AS overtaken, y.driver_id AS overtaker
  FROM t x
  JOIN t y
    ON x.race_id = y.race_id AND x.lap = y.lap
  WHERE x.prev_pos < y.prev_pos AND x.cur_pos > y.cur_pos
),
cnt AS (
  SELECT overtaken AS driver_id, 1 AS was_overtaken, 0 AS did_overtake FROM ev
  UNION ALL
  SELECT overtaker, 0, 1 FROM ev
),
agg AS (
  SELECT driver_id, SUM(was_overtaken) AS times_overtaken, SUM(did_overtake) AS times_overtook
  FROM cnt
  GROUP BY driver_id
)
SELECT d.full_name
FROM agg a
JOIN drivers d ON d.driver_id = a.driver_id
WHERE a.times_overtaken > a.times_overtook