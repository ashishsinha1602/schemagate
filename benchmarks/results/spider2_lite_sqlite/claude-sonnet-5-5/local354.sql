WITH s AS (
  SELECT driver_id, year, MIN(first_round) AS mf, MAX(last_round) AS ml
  FROM drives
  WHERE year BETWEEN 1950 AND 1959
  GROUP BY driver_id, year
  HAVING MAX(last_round) > MIN(first_round)
)
SELECT DISTINCT d.driver_id, d.forename, d.surname
FROM s
JOIN drives a ON a.driver_id = s.driver_id AND a.year = s.year AND a.first_round = s.mf
JOIN drives b ON b.driver_id = s.driver_id AND b.year = s.year AND b.last_round = s.ml AND b.constructor_id = a.constructor_id
JOIN drivers d ON d.driver_id = s.driver_id
ORDER BY d.surname, d.forename