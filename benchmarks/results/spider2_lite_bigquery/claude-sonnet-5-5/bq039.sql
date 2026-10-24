WITH t AS (
  SELECT
    y.pickup_location_id,
    y.dropoff_location_id,
    y.trip_distance,
    y.tip_amount,
    y.total_amount,
    TIMESTAMP_DIFF(y.dropoff_datetime, y.pickup_datetime, SECOND) AS trip_duration_seconds
  FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016` AS y
  WHERE y.pickup_datetime >= TIMESTAMP('2016-07-01')
    AND y.pickup_datetime < TIMESTAMP('2016-07-08')
    AND y.dropoff_datetime >= TIMESTAMP('2016-07-01')
    AND y.dropoff_datetime < TIMESTAMP('2016-07-08')
    AND y.dropoff_datetime > y.pickup_datetime
    AND y.passenger_count > 5
    AND y.trip_distance >= 10
    AND y.tip_amount >= 0
    AND y.tolls_amount >= 0
    AND y.mta_tax >= 0
    AND y.fare_amount >= 0
    AND y.total_amount >= 0
  ORDER BY y.total_amount DESC
  LIMIT 10
)
SELECT
  pz.zone_name AS pickup_zone,
  dz.zone_name AS dropoff_zone,
  t.trip_duration_seconds,
  SAFE_DIVIDE(CAST(t.trip_distance AS FLOAT64), t.trip_duration_seconds / 3600) AS driving_speed_mph,
  SAFE_DIVIDE(CAST(t.tip_amount AS FLOAT64), CAST(t.total_amount AS FLOAT64)) * 100 AS tip_rate_percent
FROM t
LEFT JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` AS pz
  ON t.pickup_location_id = pz.zone_id
LEFT JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` AS dz
  ON t.dropoff_location_id = dz.zone_id
ORDER BY t.total_amount DESC