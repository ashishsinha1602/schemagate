WITH trips AS (
  SELECT
    t.bike_number,
    ST_DISTANCE(
      ST_GEOGPOINT(s1.longitude, s1.latitude),
      ST_GEOGPOINT(s2.longitude, s2.latitude)
    ) AS dist_m
  FROM `bigquery-public-data.san_francisco.bikeshare_trips` AS t
  JOIN `bigquery-public-data.san_francisco.bikeshare_stations` AS s1
    ON t.start_station_id = s1.station_id
  JOIN `bigquery-public-data.san_francisco.bikeshare_stations` AS s2
    ON t.end_station_id = s2.station_id
)
SELECT
  bike_number,
  SUM(dist_m) AS total_distance_meters
FROM trips
GROUP BY bike_number
ORDER BY bike_number