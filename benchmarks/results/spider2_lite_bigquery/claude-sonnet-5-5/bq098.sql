WITH y AS (
  SELECT
    pickup_location_id,
    IF(total_amount = 0, 0, (tip_amount * 100) / total_amount) AS tip_rate
  FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_*`
  WHERE _TABLE_SUFFIX = '2016'
    AND data_file_year = 2016
    AND data_file_month = 1
    AND pickup_datetime >= TIMESTAMP('2016-01-01 00:00:00')
    AND pickup_datetime < TIMESTAMP('2016-01-08 00:00:00')
    AND dropoff_datetime >= TIMESTAMP('2016-01-01 00:00:00')
    AND dropoff_datetime < TIMESTAMP('2016-01-08 00:00:00')
    AND dropoff_datetime > pickup_datetime
    AND passenger_count > 0
    AND trip_distance >= 0
    AND tip_amount >= 0
    AND tolls_amount >= 0
    AND mta_tax >= 0
    AND fare_amount >= 0
    AND total_amount >= 0
),
agg AS (
  SELECT
    pickup_location_id,
    COUNTIF(tip_rate = 0) AS no_tip_trips,
    COUNT(*) AS total_trips
  FROM y
  GROUP BY pickup_location_id
)
SELECT
  z.borough AS pickup_borough,
  100 * SAFE_DIVIDE(SUM(a.no_tip_trips), SUM(a.total_trips)) AS no_tip_percentage
FROM agg a
JOIN `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom` z
  ON a.pickup_location_id = z.zone_id
GROUP BY pickup_borough