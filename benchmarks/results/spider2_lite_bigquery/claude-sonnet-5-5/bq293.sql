WITH trips AS (
  SELECT
    z.zip_code,
    TIMESTAMP_TRUNC(t.pickup_datetime, HOUR) AS pickup_hour
  FROM `bigquery-public-data.new_york.tlc_yellow_trips_*` t
  JOIN `bigquery-public-data.geo_us_boundaries.zip_codes` z
    ON ST_CONTAINS(z.zip_code_geom, ST_GEOGPOINT(t.pickup_longitude, t.pickup_latitude))
  WHERE t._TABLE_SUFFIX = '2015'
    AND DATE(t.pickup_datetime) = DATE '2015-01-01'
    AND t.pickup_latitude IS NOT NULL
    AND t.pickup_longitude IS NOT NULL
    AND t.pickup_latitude BETWEEN -90 AND 90
    AND t.pickup_longitude BETWEEN -180 AND 180
    AND z.state_code = 'NY'
    AND z.county IN ('New York County', 'Kings County', 'Queens County', 'Bronx County', 'Richmond County')
),
zips AS (
  SELECT DISTINCT zip_code FROM trips
),
hours AS (
  SELECT DISTINCT pickup_hour FROM trips
),
grid AS (
  SELECT z.zip_code, h.pickup_hour
  FROM zips z
  CROSS JOIN hours h
),
counts AS (
  SELECT
    g.zip_code,
    g.pickup_hour,
    COUNT(t.zip_code) AS trip_count
  FROM grid g
  LEFT JOIN trips t
    ON t.zip_code = g.zip_code AND t.pickup_hour = g.pickup_hour
  GROUP BY g.zip_code, g.pickup_hour
)
SELECT
  zip_code,
  pickup_hour,
  trip_count,
  LAG(trip_count, 1) OVER w AS trips_1_hour_ago,
  LAG(trip_count, 24) OVER w AS trips_1_day_ago,
  LAG(trip_count, 168) OVER w AS trips_7_days_ago,
  LAG(trip_count, 336) OVER w AS trips_14_days_ago,
  AVG(trip_count) OVER (w ROWS BETWEEN 336 PRECEDING AND 1 PRECEDING) AS moving_avg_14_days,
  STDDEV(trip_count) OVER (w ROWS BETWEEN 336 PRECEDING AND 1 PRECEDING) AS moving_stddev_14_days,
  AVG(trip_count) OVER (w ROWS BETWEEN 504 PRECEDING AND 1 PRECEDING) AS moving_avg_21_days,
  STDDEV(trip_count) OVER (w ROWS BETWEEN 504 PRECEDING AND 1 PRECEDING) AS moving_stddev_21_days
FROM counts
WINDOW w AS (PARTITION BY zip_code ORDER BY pickup_hour)
ORDER BY trip_count DESC
LIMIT 5