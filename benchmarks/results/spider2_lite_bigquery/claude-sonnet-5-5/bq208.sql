WITH nearby AS (
  SELECT usaf, wban, name, lat, lon
  FROM `bigquery-public-data.noaa_gsod.stations`
  WHERE lat IS NOT NULL AND lon IS NOT NULL
    AND ST_DWITHIN(ST_GEOGPOINT(lon, lat), ST_GEOGPOINT(-73.764, 41.197), 20 * 1609.344)
)
SELECT
  n.usaf,
  n.wban,
  n.name,
  n.lat,
  n.lon,
  COUNT(g.temp) AS valid_temp_observations
FROM nearby n
JOIN `bigquery-public-data.noaa_gsod.gsod*` g
  ON g.stn = n.usaf AND g.wban = n.wban
WHERE _TABLE_SUFFIX BETWEEN '2011' AND '2020'
  AND g.temp IS NOT NULL
  AND g.temp != 9999.9
GROUP BY n.usaf, n.wban, n.name, n.lat, n.lon
ORDER BY valid_temp_observations DESC