WITH same_station AS (
  SELECT
    start_station_id AS station_id,
    TIMESTAMP_SECONDS(DIV(UNIX_SECONDS(starttime), 120) * 120) AS start_bucket,
    TIMESTAMP_SECONDS(DIV(UNIX_SECONDS(stoptime), 120) * 120) AS stop_bucket,
    COUNT(*) AS cnt
  FROM `bigquery-public-data.new_york.citibike_trips`
  WHERE start_station_id = end_station_id
  GROUP BY 1, 2, 3
),
grp AS (
  SELECT station_id, SUM(cnt) AS group_trips
  FROM same_station
  WHERE cnt > 1
  GROUP BY station_id
),
tot AS (
  SELECT
    end_station_id AS station_id,
    ANY_VALUE(end_station_name) AS station_name,
    COUNT(*) AS total_trips
  FROM `bigquery-public-data.new_york.citibike_trips`
  GROUP BY end_station_id
)
SELECT
  tot.station_id,
  tot.station_name,
  SAFE_DIVIDE(grp.group_trips, tot.total_trips) AS group_ride_proportion
FROM grp
JOIN tot ON tot.station_id = grp.station_id
ORDER BY group_ride_proportion DESC
LIMIT 10