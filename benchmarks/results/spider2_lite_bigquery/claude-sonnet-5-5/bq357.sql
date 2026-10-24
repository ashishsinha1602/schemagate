SELECT
  latitude,
  longitude,
  DATE(timestamp) AS date
FROM `bigquery-public-data.noaa_icoads.icoads_core_*`
WHERE _TABLE_SUFFIX BETWEEN '2005' AND '2015'
  AND wind_speed IS NOT NULL
GROUP BY latitude, longitude, date
ORDER BY AVG(wind_speed) DESC
LIMIT 5