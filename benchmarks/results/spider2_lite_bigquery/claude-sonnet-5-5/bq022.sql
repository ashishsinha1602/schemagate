WITH t AS (
  SELECT
    trip_seconds / 60.0 AS duration_min,
    fare,
    NTILE(6) OVER (ORDER BY trip_seconds) AS quantile_group
  FROM `bigquery-public-data.chicago_taxi_trips.taxi_trips`
  WHERE trip_seconds IS NOT NULL
    AND trip_seconds >= 0
    AND trip_seconds <= 3600
)
SELECT
  quantile_group,
  ROUND(MIN(duration_min)) AS min_duration_minutes,
  ROUND(MAX(duration_min)) AS max_duration_minutes,
  COUNT(*) AS total_trips,
  AVG(fare) AS avg_fare
FROM t
GROUP BY quantile_group
ORDER BY quantile_group