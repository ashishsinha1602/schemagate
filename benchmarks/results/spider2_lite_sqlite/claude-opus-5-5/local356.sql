WITH lp AS MATERIALIZED (
  SELECT race_id, driver_id, lap, position,
         LAG(position) OVER (PARTITION BY race_id, driver_id ORDER BY lap) AS prev_pos,
         LAG(lap) OVER (PARTITION BY race_id, driver_id ORDER BY lap) AS prev_lap
  FROM lap_positions
  WHERE position IS NOT NULL
),
pits AS MATERIALIZED (
  SELECT DISTINCT race_id, driver_id, lap FROM pit_stops
),
ret AS MATERIALIZED (
  SELECT race_id, driver_id, MIN(lap) AS rlap
  FROM retirements
  WHERE lap IS NOT NULL
  GROUP BY race_id, driver_id
),
v AS MATERIALIZED (
  SELECT l.race_id, l.driver_id, l.lap, l.position, l.prev_pos
  FROM lp l
  LEFT JOIN pits p0 ON p0.race_id = l.race_id AND p0.driver_id = l.driver_id AND p0.lap = l.lap
  LEFT JOIN pits p1 ON p1.race_id = l.race_id AND p1.driver_id = l.driver_id AND p1.lap = l.lap - 1
  LEFT JOIN ret r ON r.race_id = l.race_id AND r.driver_id = l.driver_id
  WHERE l.lap > 1
    AND l.prev_lap = l.lap - 1
    AND p0.race_id IS NULL
    AND p1.race_id IS NULL
    AND (r.rlap IS NULL OR r.rlap > l.lap)
),
overtakes AS (
  SELECT a.driver_id AS overtaker, b.driver_id AS overtaken
  FROM v a
  JOIN v b ON b.race_id = a.race_id AND b.lap = a.lap AND b.driver_id <> a.driver_id
  WHERE a.prev_pos > b.prev_pos
    AND a.position < b.position
),
counts AS (
  SELECT driver_id, SUM(made) AS made, SUM(suffered) AS suffered
  FROM (
    SELECT overtaker AS driver_id, 1 AS made, 0 AS suffered FROM overtakes
    UNION ALL
    SELECT overtaken AS driver_id, 0 AS made, 1 AS suffered FROM overtakes
  ) x
  GROUP BY driver_id
)
SELECT d.full_name
FROM counts c
JOIN drivers d ON d.driver_id = c.driver_id
WHERE c.suffered > c.made
ORDER BY d.full_name