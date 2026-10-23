WITH ov AS (
  SELECT c1.race_id, c1.driver_id AS o, c2.driver_id AS d, c1.lap,
         p1.position AS prev_o, p2.position AS prev_d
  FROM lap_positions c1
  JOIN lap_positions c2 ON c2.race_id = c1.race_id AND c2.lap = c1.lap AND c2.driver_id <> c1.driver_id
  JOIN lap_positions p1 ON p1.race_id = c1.race_id AND p1.driver_id = c1.driver_id AND p1.lap = c1.lap - 1
  JOIN lap_positions p2 ON p2.race_id = c2.race_id AND p2.driver_id = c2.driver_id AND p2.lap = c2.lap - 1
  WHERE c1.lap BETWEEN 1 AND 5
    AND p1.position > p2.position
    AND c1.position < c2.position
),
labeled AS (
  SELECT ov.*,
    CASE
      WHEN EXISTS (SELECT 1 FROM retirements r WHERE r.race_id = ov.race_id AND r.driver_id = ov.d AND r.lap = ov.lap) THEN 'R'
      WHEN EXISTS (SELECT 1 FROM pit_stops ps WHERE ps.race_id = ov.race_id AND ps.driver_id = ov.d AND ps.lap = ov.lap) THEN 'P'
      WHEN EXISTS (
        SELECT 1
        FROM pit_stops ps
        JOIN lap_times_ext lo ON lo.race_id = ov.race_id AND lo.driver_id = ov.o AND lo.lap = ov.lap
        JOIN lap_times_ext ld ON ld.race_id = ov.race_id AND ld.driver_id = ov.d AND ld.lap = ov.lap
        WHERE ps.race_id = ov.race_id AND ps.driver_id = ov.d AND ps.lap = ov.lap - 1
          AND ABS(ld.running_milliseconds - lo.running_milliseconds) < ps.milliseconds
      ) THEN 'P'
      WHEN ov.lap = 1 AND ABS(ov.prev_o - ov.prev_d) <= 2 THEN 'S'
      ELSE 'T'
    END AS label
  FROM ov
)
SELECT label, COUNT(*) AS overtakes
FROM labeled
GROUP BY label
ORDER BY label