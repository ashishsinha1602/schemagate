WITH routes AS (
  SELECT
    start_station_id,
    end_station_id,
    COUNT(*) AS trips,
    AVG(tripduration) AS avg_bike
  FROM `bigquery-public-data.new_york.citibike_trips`
  WHERE starttime >= TIMESTAMP('2016-01-01') AND starttime < TIMESTAMP('2017-01-01')
  GROUP BY start_station_id, end_station_id
  ORDER BY trips DESC
  LIMIT 20
),
routes_geo AS (
  SELECT
    s.name AS start_station_name,
    ROUND(s.latitude, 3) AS slat,
    ROUND(s.longitude, 3) AS slon,
    ROUND(e.latitude, 3) AS elat,
    ROUND(e.longitude, 3) AS elon,
    r.avg_bike
  FROM routes r
  JOIN `bigquery-public-data.new_york.citibike_stations` s
    ON SAFE_CAST(s.station_id AS INT64) = r.start_station_id
  JOIN `bigquery-public-data.new_york.citibike_stations` e
    ON SAFE_CAST(e.station_id AS INT64) = r.end_station_id
),
taxi AS (
  SELECT
    ROUND(pickup_latitude, 3) AS plat,
    ROUND(pickup_longitude, 3) AS plon,
    ROUND(dropoff_latitude, 3) AS dlat,
    ROUND(dropoff_longitude, 3) AS dlon,
    AVG(TIMESTAMP_DIFF(dropoff_datetime, pickup_datetime, SECOND)) AS avg_taxi
  FROM `bigquery-public-data.new_york.tlc_yellow_trips_*`
  WHERE _TABLE_SUFFIX = '2016'
    AND dropoff_datetime > pickup_datetime
    AND ROUND(pickup_latitude, 3) IN (SELECT slat FROM routes_geo)
    AND ROUND(pickup_longitude, 3) IN (SELECT slon FROM routes_geo)
    AND ROUND(dropoff_latitude, 3) IN (SELECT elat FROM routes_geo)
    AND ROUND(dropoff_longitude, 3) IN (SELECT elon FROM routes_geo)
  GROUP BY plat, plon, dlat, dlon
)
SELECT r.start_station_name
FROM routes_geo r
JOIN taxi t
  ON r.slat = t.plat AND r.slon = t.plon AND r.elat = t.dlat AND r.elon = t.dlon
WHERE r.avg_bike < t.avg_taxi
ORDER BY r.avg_bike DESC
LIMIT 1