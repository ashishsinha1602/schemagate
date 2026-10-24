WITH lp AS (
  SELECT race_id, driver_id, lap, position,
         LAG(position) OVER w AS prev_pos,
         LAG(lap) OVER w AS prev_lap
  FROM lap_positions
  WHERE race_id IN (SELECT race_id FROM races_ext WHERE is_pit_data_available = 1)
  WINDOW w AS (PARTITION BY race_id, driver_id ORDER BY lap)
),
cur AS (
  SELECT race_id, driver_id, lap, position, prev_pos
  FROM lp
  WHERE lap >= 1 AND prev_lap = lap - 1
),
pairs AS (
  SELECT a.race_id,
         a.lap,
         a.driver_id AS overtaking_driver_id,
         b.driver_id AS overtaken_driver_id,
         a.prev_pos AS prev_overtaking_pos,
         b.prev_pos AS prev_overtaken_pos
  FROM cur a
  JOIN cur b
    ON b.race_id = a.race_id
   AND b.lap = a.lap
   AND b.driver_id <> a.driver_id
   AND a.position < b.position
   AND b.prev_pos < a.prev_pos
),
ret AS (
  SELECT DISTINCT race_id, driver_id, lap FROM retirements
),
pit AS (
  SELECT DISTINCT race_id, driver_id, lap FROM pit_stops
),
avg_pit AS (
  SELECT race_id, AVG(milliseconds) AS avg_ms
  FROM pit_stops
  GROUP BY race_id
),
lt AS (
  SELECT race_id, driver_id, lap, MAX(running_milliseconds) AS running_ms
  FROM lap_times_ext
  WHERE race_id IN (SELECT race_id FROM races_ext WHERE is_pit_data_available = 1)
  GROUP BY race_id, driver_id, lap
),
labeled AS (
  SELECT
    CASE
      WHEN r.race_id IS NOT NULL THEN 'R'
      WHEN p1.race_id IS NOT NULL THEN 'P'
      WHEN p2.race_id IS NOT NULL
       AND ABS(la.running_ms - lb.running_ms) < ap.avg_ms THEN 'P'
      WHEN p.lap = 1
       AND ABS(p.prev_overtaking_pos - p.prev_overtaken_pos) <= 2 THEN 'S'
      ELSE 'T'
    END AS overtake_type
  FROM pairs p
  LEFT JOIN ret r
    ON r.race_id = p.race_id AND r.driver_id = p.overtaken_driver_id AND r.lap = p.lap
  LEFT JOIN pit p1
    ON p1.race_id = p.race_id AND p1.driver_id = p.overtaken_driver_id AND p1.lap = p.lap
  LEFT JOIN pit p2
    ON p2.race_id = p.race_id AND p2.driver_id = p.overtaken_driver_id AND p2.lap = p.lap - 1
  LEFT JOIN lt la
    ON la.race_id = p.race_id AND la.driver_id = p.overtaking_driver_id AND la.lap = p.lap - 1
  LEFT JOIN lt lb
    ON lb.race_id = p.race_id AND lb.driver_id = p.overtaken_driver_id AND lb.lap = p.lap - 1
  LEFT JOIN avg_pit ap
    ON ap.race_id = p.race_id
)
SELECT overtake_type, COUNT(*) AS overtake_count
FROM labeled
GROUP BY overtake_type
ORDER BY overtake_type