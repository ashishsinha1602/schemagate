SELECT FORMAT_DATE('%Y-%m-%d', `date`) AS date
FROM `bigquery-public-data.noaa_gsod.gsod*`
WHERE _TABLE_SUFFIX = '2009'
  AND stn = '723758'
  AND mo = '10'
  AND temp != 9999.9
ORDER BY temp DESC
LIMIT 3