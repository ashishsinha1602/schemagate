WITH appearances AS (
  SELECT r.driver_id, ra.year, ra.round, r.constructor_id,
         LAG(ra.round) OVER (PARTITION BY r.driver_id, ra.year ORDER BY ra.round) AS prev_round,
         LAG(r.constructor_id) OVER (PARTITION BY r.driver_id, ra.year ORDER BY ra.round) AS prev_constructor
  FROM results r
  JOIN races ra ON ra.race_id = r.race_id
),
gaps AS (
  SELECT driver_id, year,
         prev_round + 1 AS first_missed,
         round - 1 AS last_missed
  FROM appearances
  WHERE prev_round IS NOT NULL
    AND round - prev_round > 1
    AND round - prev_round - 1 < 3
    AND constructor_id <> prev_constructor
)
SELECT AVG(first_missed) AS avg_first_round_missed,
       AVG(last_missed) AS avg_last_round_missed
FROM gaps