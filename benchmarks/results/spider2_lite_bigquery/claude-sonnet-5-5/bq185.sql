SELECT AVG(TIMESTAMP_DIFF(t.dropoff_datetime, t.pickup_datetime, SECOND) / 60.0) AS avg_trip_duration_minutes
FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_*` t
JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` pz
  ON t.pickup_location_id = pz.zone_id AND pz.borough = 'Brooklyn'
JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` dz
  ON t.dropoff_location_id = dz.zone_id AND dz.borough = 'Brooklyn'
WHERE t._TABLE_SUFFIX = '2016'
  AND t.pickup_datetime >= TIMESTAMP('2016-02-01')
  AND t.pickup_datetime < TIMESTAMP('2016-02-08')
  AND t.dropoff_datetime > t.pickup_datetime
  AND t.passenger_count > 3
  AND t.trip_distance >= 10