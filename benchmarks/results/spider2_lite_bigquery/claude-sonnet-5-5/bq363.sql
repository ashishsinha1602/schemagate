WITH t AS (
  SELECT DIV(trip_seconds, 60) AS minutes, fare
  FROM `bigquery-public-data.chicago_taxi_trips.taxi_trips`
  WHERE trip_seconds IS NOT NULL
    AND DIV(trip_seconds, 60) BETWEEN 1 AND 50
),
d AS (
  SELECT minutes, NTILE(10) OVER (ORDER BY minutes) AS q
  FROM (SELECT DISTINCT minutes FROM t)
),
r AS (
  SELECT q, MIN(minutes) AS min_m, MAX(minutes) AS max_m
  FROM d
  GROUP BY q
)
SELECT
  CONCAT(FORMAT('%02d', r.min_m), 'm to ', FORMAT('%02d', r.max_m), 'm') AS time_range,
  COUNT(*) AS total_trips,
  ROUND(AVG(t.fare), 2) AS avg_fare
FROM t
JOIN d ON t.minutes = d.minutes
JOIN r ON d.q = r.q
GROUP BY r.q, r.min_m, r.max_m
ORDER BY r.min_m