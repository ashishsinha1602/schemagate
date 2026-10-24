WITH e AS (
  SELECT
    b.borough_name,
    TO_JSON_STRING(STRUCT(s.station_name, s.line, s.station_lat, s.station_lon)) AS station_key,
    (s.entry IS TRUE AND s.ada_compliant IS TRUE) AS ok
  FROM `bigquery-public-data.new_york_subway.station_entrances` s
  JOIN `bigquery-public-data.new_york_subway.geo_nyc_borough_boundaries` b
    ON ST_CONTAINS(b.borough_geom, s.station_geom)
)
SELECT
  borough_name,
  COUNT(DISTINCT station_key) AS total_stations,
  COUNT(DISTINCT IF(ok, station_key, NULL)) AS stations_with_ada_entry,
  SAFE_DIVIDE(COUNT(DISTINCT IF(ok, station_key, NULL)), COUNT(DISTINCT station_key)) * 100 AS percentage
FROM e
GROUP BY borough_name
ORDER BY percentage DESC