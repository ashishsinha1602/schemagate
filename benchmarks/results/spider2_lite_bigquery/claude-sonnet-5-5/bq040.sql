WITH zones AS (
  SELECT zone_id, borough
  FROM `bigquery-public-data.new_york_taxi_trips.taxi_zone_geom`
  WHERE borough NOT IN ('EWR', 'Staten Island')
),
base AS (
  SELECT
    z.borough AS pickup_borough,
    t.tip_amount,
    SAFE_DIVIDE(t.tip_amount, t.total_amount) * 100 AS tip_rate
  FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2016` t
  JOIN zones z
    ON t.pickup_location_id = z.zone_id
  WHERE t.pickup_datetime >= TIMESTAMP('2016-01-01')
    AND t.pickup_datetime < TIMESTAMP('2016-01-08')
    AND t.dropoff_datetime > t.pickup_datetime
    AND t.passenger_count > 0
    AND t.trip_distance >= 0
    AND t.tip_amount >= 0
    AND t.tolls_amount >= 0
    AND t.mta_tax >= 0
    AND t.fare_amount >= 0
    AND t.total_amount >= 0
),
categorized AS (
  SELECT
    pickup_borough,
    CASE
      WHEN tip_amount = 0 THEN 'no tip'
      WHEN tip_rate <= 5 THEN 'Less than 5%'
      WHEN tip_rate <= 10 THEN '5% to 10%'
      WHEN tip_rate <= 15 THEN '10% to 15%'
      WHEN tip_rate <= 20 THEN '15% to 20%'
      WHEN tip_rate <= 25 THEN '20% to 25%'
      WHEN tip_rate > 25 THEN 'More than 25%'
    END AS tip_category
  FROM base
)
SELECT
  pickup_borough,
  tip_category,
  COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY pickup_borough) AS proportion
FROM categorized
WHERE tip_category IS NOT NULL
GROUP BY pickup_borough, tip_category
ORDER BY pickup_borough, tip_category