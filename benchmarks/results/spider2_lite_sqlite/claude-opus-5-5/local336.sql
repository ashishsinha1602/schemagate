WITH lp AS MATERIALIZED (
  SELECT race_id, driver_id, lap, position
  FROM lap_positions
  WHERE lap BETWEEN 0 AND 5
),
d AS MATERIALIZED (
  SELECT c.race_id, c.driver_id, c.lap, c.position AS pos, p.position AS prev_pos
  FROM lp c
  JOIN lp p ON p.race_id = c.race_id AND p.driver_id = c.driver_id AND p.lap = c.lap - 1
  WHERE c.lap BETWEEN 1 AND 5
),
ov AS MATERIALIZED (
  SELECT a.race_id, a.lap, a.driver_id AS overtaking, b.driver_id AS overtaken,
         a.prev_pos AS prev_pos_a, b.prev_pos AS prev_pos_b
  FROM d a
  JOIN d b ON b.race_id = a.race_id AND b.lap = a.lap AND b.driver_id <> a.driver_id
  WHERE a.pos < b.pos
    AND a.prev_pos > b.prev_pos
),
ret AS MATERIALIZED (
  SELECT DISTINCT race_id, driver_id, lap FROM retirements WHERE lap BETWEEN 1 AND 5
),
pits AS MATERIALIZED (
  SELECT DISTINCT race_id, driver_id, lap FROM pit_stops WHERE lap BETWEEN 0 AND 5
),
lt AS MATERIALIZED (
  SELECT race_id, driver_id, lap, running_milliseconds
  FROM lap_times_ext WHERE lap BETWEEN 0 AND 4
),
avg_pit AS MATERIALIZED (
  SELECT AVG(milliseconds) AS ms FROM pit_stops
),
labeled AS (
  SELECT CASE
    WHEN EXISTS (SELECT 1 FROM ret r
                 WHERE r.race_id = o.race_id AND r.driver_id = o.overtaken AND r.lap = o.lap) THEN 'R'
    WHEN EXISTS (SELECT 1 FROM pits ps
                 WHERE ps.race_id = o.race_id AND ps.driver_id = o.overtaken AND ps.lap = o.lap) THEN 'P'
    WHEN EXISTS (SELECT 1 FROM pits ps
                 WHERE ps.race_id = o.race_id AND ps.driver_id = o.overtaken AND ps.lap = o.lap - 1)
         AND ABS((SELECT la.running_milliseconds FROM lt la
                  WHERE la.race_id = o.race_id AND la.driver_id = o.overtaking AND la.lap = o.lap - 1)
               - (SELECT lb.running_milliseconds FROM lt lb
                  WHERE lb.race_id = o.race_id AND lb.driver_id = o.overtaken AND lb.lap = o.lap - 1))
             < (SELECT ms FROM avg_pit) THEN 'P'
    WHEN o.lap = 1 AND ABS(o.prev_pos_a - o.prev_pos_b) <= 2 THEN 'S'
    ELSE 'T'
  END AS category
  FROM ov o
),
cats AS (
  SELECT 'R' AS category UNION ALL SELECT 'P' UNION ALL SELECT 'S' UNION ALL SELECT 'T'
)
SELECT c.category, COUNT(l.category) AS overtakes
FROM cats c
LEFT JOIN labeled l ON l.category = c.category
GROUP BY c.category