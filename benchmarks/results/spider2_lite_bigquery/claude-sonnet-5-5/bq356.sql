WITH valid AS (
  SELECT stn, wban, COUNT(DISTINCT date) AS valid_days
  FROM `bigquery-public-data.noaa_gsod.gsod*`
  WHERE _TABLE_SUFFIX = '2019'
    AND temp != 9999.9
    AND max != 9999.9
    AND min != 9999.9
    AND temp IS NOT NULL
    AND max IS NOT NULL
    AND min IS NOT NULL
  GROUP BY stn, wban
)
SELECT COUNT(*) AS station_count
FROM valid v
JOIN (
  SELECT DISTINCT usaf, wban
  FROM `bigquery-public-data.noaa_gsod.stations`
  WHERE `begin` <= '20000101'
    AND `end` >= '20190630'
) s
  ON v.stn = s.usaf AND v.wban = s.wban
WHERE v.valid_days >= 0.9 * 365